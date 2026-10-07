"""저장소의 학습 코드로 직접 학습해 MLflow 에 남은 모델을, 서버를 거치지 않고 평가한다.

서버의 /predict 가 빈칸 때문에 응답하지 못해도, train_and_register.py 가 학습한 모델은 MLflow 실행 기록에 남는다
(게이트를 통과하지 못해 등록되지 않았을 뿐이다). 그 모델과 같은 스케일러, 같은 창·분할 함수(data/features.py)로
시험 구간을 다시 예측해 RMSE, 합계 오차율, 치우침을 잰다. 코드와 자료는 바꾸지 않는다.

잰 값은 "우리가 직접 학습한 모델의 오프라인 평가"다. 서버가 응답한 값이 아니다.

실행 (검증용 사본의 project/ 에서. 그 사본에서 예보 업로드 파일로 train_and_register.py 를 돌린 뒤):
    python <저장소>/tools/proposal/offline_model_eval.py --out <저장소>/docs/proposal/evidence
"""
import argparse
import datetime as dt
import json
import os
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
sys.path.insert(0, os.getcwd())

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from common import DATASETS, baselines_for_targets, bias_pct, practice_split, rmse, total_error_pct  # noqa: E402

p = argparse.ArgumentParser()
p.add_argument("--out", type=Path, required=True)
p.add_argument("--csv", type=Path, default=DATASETS / "hadong_upload_forecast_jma.csv")
a = p.parse_args()

import mlflow  # noqa: E402
import mlflow.tensorflow  # noqa: E402
from mlflow.tracking import MlflowClient  # noqa: E402

from data.features import SEQ_LEN, HAICScaler, build_sequences, load_rows, train_test_split  # noqa: E402
from serving_app.routers.predict import SIMULATED_VOLUME  # noqa: E402
from serving_app.train_and_register import SCALER_PATH  # noqa: E402

c = MlflowClient()
runs = [r for e in c.search_experiments() for r in c.search_runs([e.experiment_id], order_by=["attributes.start_time DESC"])]
run = next(r for r in runs if r.data.params.get("mode") == "scratch" and r.data.metrics.get("rmse", 0) > 10)   # 태양광 파일로 학습한 실행
logged = [m for m in mlflow.search_logged_models(output_format="list") if m.source_run_id == run.info.run_id]
model = mlflow.tensorflow.load_model(f"models:/{logged[0].model_id}")

rows = load_rows(str(a.csv))
scaler = HAICScaler.load(SCALER_PATH)
fit_now = HAICScaler().fit(rows)
scaler_matches = all(abs(getattr(scaler, k) - getattr(fit_now, k)) < 1e-12 for k in ("close_min", "close_max", "volume_min", "volume_max"))

X, y = build_sequences(rows, scaler)
_, _, X_test, y_test = train_test_split(X, y)
y_test = np.array(y_test, dtype=float)
pred = np.array([scaler.inverse_close(v) for v in model.predict(np.array(X_test, dtype="float32"), verbose=0).flatten()])

dates = pd.to_datetime([r["Date"] for r in rows])
close = np.array([r["Close"] for r in rows], dtype=float)
vol = np.array([r["Volume"] for r in rows], dtype=float)
_, _, test_idx = practice_split(len(rows))
base = baselines_for_targets(close, vol, test_idx)


def summary(y_true, y_hat):
    return {"rmse_kwh": round(rmse(y_true, y_hat), 4), "total_error_pct": round(total_error_pct(y_true, y_hat), 2),
            "bias_pct": round(bias_pct(y_true, y_hat), 2)}


result = {
    "evaluated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
    "what": "저장소의 학습 코드로 직접 학습한 모델의 오프라인 평가. 서버가 응답한 값이 아니다",
    "run": {"run_id": run.info.run_id[:8], "logged_rmse": round(run.data.metrics["rmse"], 4), "params": dict(run.data.params),
            "registered": False, "why_not_registered": "현재 코드의 게이트가 RMSE 4.00 이하라서"},
    "scaler_equals_fit_on_this_file": scaler_matches,
    "test": {"n": int(len(y_test)), "start": str(dates[test_idx[0]].date()), "end": str(dates[test_idx[-1]].date()),
             "mean_actual_kwh": round(float(y_test.mean()), 2)},
    "model": summary(y_test, pred),
    "model_prediction_range_kwh": [round(float(pred.min()), 2), round(float(pred.max()), 2)],
    "model_negative_predictions": int((pred < 0).sum()),
    "baselines": {k: summary(y_test, v) for k, v in base.items()},
}

# 달마다
month = pd.Series(dates[test_idx].strftime("%Y-%m"))
result["by_month"] = []
for mth in month.unique():
    m = (month == mth).values
    result["by_month"].append({"month": mth, "n": int(m.sum()), **summary(y_test[m], pred[m]),
                               "rule_c_rmse_kwh": round(rmse(y_test[m], base["규칙C"][m]), 2)})

# 시연 장면의 배치: 2025-06-21 ~ 07-31 의 41행으로 대상 07-11 ~ 07-31 의 21건을 예측한다
start = int(np.where(dates == pd.Timestamp("2025-06-21"))[0][0])
sl = slice(start, start + SEQ_LEN + 21)
batch = {}
for label, factor, volume_mode in (("주입 없음, 실제 예보를 넣음", 1.0, "real"), ("발전량 × 0.86, 실제 예보를 넣음", 0.86, "real"),
                                    ("주입 없음, 현재 코드처럼 둘째 값을 1,200,000 으로 고정", 1.0, "fixed")):
    cc = close[sl] * factor
    vv = vol[sl] if volume_mode == "real" else np.full(SEQ_LEN + 21, float(SIMULATED_VOLUME))
    pts = [scaler.transform_point(c_, v_) for c_, v_ in zip(cc, vv)]
    xb = np.array([pts[i:i + SEQ_LEN] for i in range(21)], dtype="float32")
    yb = cc[SEQ_LEN:]
    pb = np.array([scaler.inverse_close(v) for v in model.predict(xb, verbose=0).flatten()])
    batch[label] = {"n": 21, **summary(yb, pb), "rmse_vs_test_rmse": round(rmse(yb, pb) / result["model"]["rmse_kwh"], 2),
                    "prediction_range_kwh": [round(float(pb.min()), 1), round(float(pb.max()), 1)]}
result["demo_batch_2025-06-21"] = {"rows": [str(dates[sl][0].date()), str(dates[sl][-1].date())],
                                    "targets": [str(dates[start + SEQ_LEN].date()), str(dates[sl][-1].date())],
                                    "note": "이 모델의 학습 정답일은 2025-06-08 까지라, 이 배치는 학습에 쓰이지 않은 날이다", "cases": batch}

a.out.mkdir(parents=True, exist_ok=True)
(a.out / "offline_model_eval.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

t = [f"실행 {result['run']['run_id']} (MLflow 에 기록된 rmse {result['run']['logged_rmse']}, 등록되지 않음)",
     f"스케일러가 이 파일 전체로 맞춘 값과 같은가: {scaler_matches}",
     f"시험 구간 {result['test']['start']} ~ {result['test']['end']}, {result['test']['n']}일, 하루 평균 발전량 {result['test']['mean_actual_kwh']}kWh", "",
     "예측                RMSE(kWh)   합계 오차율   치우침"]
m_ = result["model"]
t.append(f"직접 학습한 LSTM     {m_['rmse_kwh']:>8.2f}    {m_['total_error_pct']:>6.1f}%    {m_['bias_pct']:>+6.1f}%")
for k, v in result["baselines"].items():
    t.append(f"{k:<16}  {v['rmse_kwh']:>8.2f}    {v['total_error_pct']:>6.1f}%    {v['bias_pct']:>+6.1f}%")
t += ["", f"모델 예측의 범위 {result['model_prediction_range_kwh'][0]} ~ {result['model_prediction_range_kwh'][1]}kWh, 0 아래로 내려간 예측 {result['model_negative_predictions']}건",
      "", "달            일수   모델 RMSE   모델 치우침   규칙C RMSE"]
for r in result["by_month"]:
    t.append(f"{r['month']}     {r['n']:>3d}    {r['rmse_kwh']:>7.2f}     {r['bias_pct']:>+6.1f}%      {r['rule_c_rmse_kwh']:>7.2f}")
t += ["", f"시연 배치 {result['demo_batch_2025-06-21']['rows'][0]} ~ {result['demo_batch_2025-06-21']['rows'][1]}, 대상 21일"]
for label, v in batch.items():
    t.append(f"  {label}: RMSE {v['rmse_kwh']:.1f}kWh (시험 RMSE 의 {v['rmse_vs_test_rmse']}배), 치우침 {v['bias_pct']:+.1f}%, 예측 범위 {v['prediction_range_kwh'][0]} ~ {v['prediction_range_kwh'][1]}kWh")
(a.out / "offline_model_eval.txt").write_text("\n".join(t) + "\n", encoding="utf-8")
print("\n".join(t))
