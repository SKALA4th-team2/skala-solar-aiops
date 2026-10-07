"""s8b: s8 의 실습 LSTM 결과(씨앗 42·43·44)를 모아 표로 만든다. ASOS 묶음의 값과 맞는지도 본다."""
import json, numpy as np, pandas as pd
from t2_common import *
pd.set_option("display.width", 250); pd.set_option("display.float_format", lambda v: f"{v:.2f}")
rows = []
for kind in ("lag", "proxy"):
    for var in ("none", "stop43", "stop50"):
        m = json.load(open(HERE / "lstm" / f"{kind}_{var}.json"))
        for r in m["runs"]:
            rows.append(dict(파일={"lag": "현실 조건", "proxy": "상한(예측 시점에 받을 수 없는 값 사용)"}[kind], 학습제외={"none": "없음", "stop43": "ASOS Stop 43일", "stop50": "정지 50일"}[var],
                             학습표본=m["n_train_used"], 뺀표본=m["n_excluded"], 씨앗=r["seed"], 시험RMSE=r["rmse_all"], 이벤트16일_제외=r["rmse_excl_event_targets"], 닿는표본_제외=r["rmse_excl_touched"],
                             치우침=r["bias_pred_minus_actual"], 이벤트일_평균오차=r["event_day_mean_err"], 학습초=r["fit_seconds"]))
T = pd.DataFrame(rows); print(T.to_string(index=False)); T.to_csv(HERE / "s8_lstm_exclusion_runs.csv", index=False, encoding="utf-8-sig")
g = T.groupby(["파일", "학습제외"], sort=False).agg(학습표본=("학습표본", "first"), 뺀표본=("뺀표본", "first"), RMSE평균=("시험RMSE", "mean"), RMSE최소=("시험RMSE", "min"), RMSE최대=("시험RMSE", "max"),
                                             이벤트16일_제외_평균=("이벤트16일_제외", "mean"), 닿는표본_제외_평균=("닿는표본_제외", "mean"), 치우침_평균=("치우침", "mean"), 이벤트일_평균오차=("이벤트일_평균오차", "mean"))
print("\n씨앗 3개 요약"); print(g.to_string()); g.to_csv(HERE / "s8_lstm_exclusion_summary.csv", encoding="utf-8-sig")
# ASOS 묶음의 값과 대조
a = pd.read_csv(ASOS / "hadong_build" / "train_check" / "lag_gsr_pred.csv"); b = pd.read_csv(HERE / "lstm" / "lag_none_pred.csv")
print("\nASOS 묶음 예측 파일과의 차이(제외 없음, 현실 조건): 최대 절댓값 차", float(np.abs(a[["pred_s42", "pred_s43", "pred_s44"]].values - b[["pred_s42", "pred_s43", "pred_s44"]].values).max()))
a = pd.read_csv(ASOS / "hadong_build" / "train_check" / "proxy_gsr_pred.csv"); b = pd.read_csv(HERE / "lstm" / "proxy_none_pred.csv")
print("ASOS 묶음 예측 파일과의 차이(제외 없음, 상한): 최대 절댓값 차", float(np.abs(a[["pred_s42", "pred_s43", "pred_s44"]].values - b[["pred_s42", "pred_s43", "pred_s44"]].values).max()))
# 21건 창 RMSE (상한): 45, 50 을 넘는 창의 비율과 그 창의 끝 날짜
ev = pd.read_csv(HERE / "equipment_events_final.csv", encoding="utf-8-sig", parse_dates=["date"])
for kind in ("lag", "proxy"):
    for var in ("none", "stop50"):
        p = pd.read_csv(HERE / "lstm" / f"{kind}_{var}_pred.csv", parse_dates=["date"]).set_index("date"); isev = p.index.isin(ev.date)
        out = []
        for s in (42, 43, 44):
            e2 = (p[f"pred_s{s}"] - p.actual) ** 2; r = np.sqrt(e2.rolling(21).mean()).dropna()
            rx = np.sqrt(e2.where(~isev).rolling(21, min_periods=15).mean()).dropna()
            out.append((r.median(), r.quantile(.95), r.max(), str(r.idxmax().date()), (r > 45).mean() * 100, (r > 50).mean() * 100, rx.max(), str(rx.idxmax().date()), (rx > 45).mean() * 100, (rx > 50).mean() * 100,
                        int(((r > 45) & (r.index >= "2024-07-10") & (r.index <= "2024-08-08")).sum()), int((r > 45).sum())))
        o = pd.DataFrame(out, columns=["중앙", "95%", "최대", "최대_끝날짜", ">45 %", ">50 %", "16일뺀_최대", "16일뺀_끝날짜", "16일뺀>45 %", "16일뺀>50 %", ">45 창 중 2024-07-10~08-08", ">45 창 수"])
        print(f"\n21건 창 RMSE [{kind}, 학습제외 {var}] 씨앗 42·43·44"); print(o.to_string(index=False))
