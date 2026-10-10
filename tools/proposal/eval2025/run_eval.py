"""2025년 평가 구간의 시간별 예측을 다시 만든다.

팀 저장소 tools/hourly/train.py 의 평가 부분만 그대로 따라 한다(같은 분할, 같은 시드, 같은 모델).
배포용 재학습과 MLflow 등록은 하지 않는다. 결과는 out/<plant_id>.csv 와 out/<plant_id>.json 에 쓴다.

    python run_eval.py                # 33곳을 네 개씩 나눠 돌린다
    python run_eval.py --plant <id>   # 한 곳
"""
import os
os.environ.setdefault("TF_ENABLE_ONEDNN_OPTS", "0")
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")
os.environ["SOLAR_MODEL_CONTRACT"] = "solar_hourly_24_jma_day2_v1"
import argparse
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
OUT = HERE / "out"
os.environ["SOLAR_STATE_DIR"] = str(HERE / "state")


def one(pid):
    import numpy as np
    import pandas as pd
    import tensorflow as tf
    tf.config.threading.set_intra_op_parallelism_threads(2)
    tf.config.threading.set_inter_op_parallelism_threads(1)
    sys.path.insert(0, str(ROOT / "project"))
    from serving_app.hourly.model import features, build_model

    entry = next(p for p in json.loads((ROOT / "datasets/hourly/screening.json").read_text())["included"]
                 if p["plant_id"] == pid)
    capacity = entry["capacity_kw"]
    frame = pd.read_csv(ROOT / entry["hourly_file"])
    frame["timestamp"] = pd.to_datetime(frame.timestamp)
    frame = frame.set_index("timestamp")
    groups = {str(day.date()): g.reset_index().assign(timestamp=lambda d: d.timestamp.map(lambda t: t.isoformat())).to_dict("records")
              for day, g in frame.groupby(frame.index.normalize())}
    dates, xx, yy, forecasts = [], [], [], []
    for day, rows in groups.items():
        previous = str((pd.Timestamp(day) - pd.Timedelta(days=1)).date())
        if previous not in groups or len(rows) != 24 or len(groups[previous]) != 24:
            continue
        dates.append(day)
        xx.append(features(groups[previous], rows, capacity))
        yy.append([r["generation_kwh"] for r in rows])
        forecasts.append(rows)
    x, y, dates = np.asarray(xx), np.asarray(yy), np.array(dates)
    tr = np.flatnonzero(dates < "2024-07-01")
    va = np.flatnonzero((dates >= "2024-07-01") & (dates < "2025-01-01"))
    te = np.flatnonzero((dates >= "2025-01-01") & (dates < "2026-01-01"))
    radiation = x[:, :, 1] * 1000
    coef = float(np.sum(radiation[tr] * y[tr]) / np.sum(radiation[tr] ** 2))
    normalized_coef = coef * 1000 / capacity

    def fit(indices, epochs, validation=None):
        tf.keras.backend.clear_session()
        tf.keras.utils.set_random_seed(42)
        m = build_model(normalized_coef)
        callbacks = [tf.keras.callbacks.EarlyStopping(monitor="val_loss", patience=5, restore_best_weights=True)] if validation is not None else []
        history = m.fit(x[indices], (y[indices] / capacity)[:, :, None],
                        validation_data=(x[validation], (y[validation] / capacity)[:, :, None]) if validation is not None else None,
                        epochs=epochs, batch_size=64, shuffle=False, verbose=0, callbacks=callbacks).history
        return m, history

    model, history = fit(tr, 25, va)
    epochs = int(np.argmin(history["val_loss"]) + 1)
    model, _ = fit(np.r_[tr, va], epochs)
    pred = np.clip(model(x[te], training=False).numpy().reshape(-1, 24) * capacity, 0, capacity)
    pred[radiation[te] <= 1] = 0
    lag = x[te, :, 0] * capacity
    reference = np.clip(radiation[te] * coef, 0, capacity)
    reference[radiation[te] <= 1] = 0
    OUT.mkdir(exist_ok=True)
    pd.DataFrame(dict(timestamp=[r["timestamp"] for i in te for r in forecasts[i]], actual_kwh=y[te].ravel(),
                      predicted_kwh=pred.ravel(), lag24_kwh=lag.ravel(), reference_kwh=reference.ravel(),
                      radiation=radiation[te].ravel())).to_csv(OUT / f"{pid}.csv", index=False)
    e = pred - y[te]
    (OUT / f"{pid}.json").write_text(json.dumps(dict(
        plant_id=pid, name=entry["name"], capacity_kw=capacity, epochs=epochs, n_days=int(len(te)),
        rmse_kwh=float(np.sqrt(np.mean(e ** 2))), mae_kwh=float(np.mean(abs(e))),
        bias_pct=float(100 * e.sum() / y[te].sum())), ensure_ascii=False))
    print("DONE", pid, epochs, float(np.sqrt(np.mean(e ** 2))), flush=True)


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--plant")
    a.add_argument("--workers", type=int, default=4)
    args = a.parse_args()
    if args.plant:
        return one(args.plant)
    ids = [p["plant_id"] for p in json.loads((ROOT / "datasets/hourly/screening.json").read_text())["included"]]
    OUT.mkdir(exist_ok=True)

    def run(pid):
        if (OUT / f"{pid}.json").exists():
            return pid, 0
        with (OUT / f"{pid}.log").open("w") as log:
            return pid, subprocess.run([sys.executable, "-X", "utf8", "-B", __file__, "--plant", pid],
                                       stdout=log, stderr=subprocess.STDOUT).returncode

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for fut in as_completed([pool.submit(run, pid) for pid in ids]):
            print("PROCESS", fut.result(), flush=True)


if __name__ == "__main__":
    main()
