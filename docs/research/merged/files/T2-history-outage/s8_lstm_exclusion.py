"""s8: 실습 LSTM 으로, 학습에서 정지 표본을 빼는 목록(없음 / ASOS Stop 43일 / 정지 50일)에 따라 시험 구간 RMSE 가 달라지는지 잰다.

실습 코드(project/data/features.py, project/serving_app/lstm_model.py, scripts/train_baseline_v1.py)를 읽어 같은 절차를 여기에 옮겨 적었다.
실습 모듈은 import 하지 않는다(저장소에 __pycache__ 나 mlflow.db 변경이 생기지 않게).
  행 읽기 -> 최소·최대 스케일러(전체 행) -> 최근 20행 창과 다음 행 정답 -> 앞 80% 학습 / 뒤 20% 시험 -> LSTM(32,32,16)+Dense(16)+Dense(1), Adam 1e-3, mse, 100 epoch
다른 점은 학습 표본에서 '창이나 정답일에 목록의 날이 걸린 표본'을 빼는 것뿐이다. 시험 표본은 그대로 둔다.
실행: python s8_lstm_exclusion.py <lag|proxy> <none|stop43|stop50> <seed> [<seed> ...]
proxy 파일은 정답일과 그 전날의 실제 관측 일사량이 입력에 들어간다(예측 시점에는 받을 수 없는 값. 상한).
"""
import csv, json, os, sys, time
sys.dont_write_bytecode = True
import numpy as np
import tensorflow as tf
from tensorflow import keras
tf.config.threading.set_intra_op_parallelism_threads(1)
tf.config.threading.set_inter_op_parallelism_threads(1)

S = "(작업 폴더)"
HERE = S + "/merged/T2-history-outage"
FILES = {"lag": S + "/asos/hadong_upload.csv", "proxy": S + "/asos/hadong_upload_forecast_proxy.csv"}
SEQ_LEN, EPOCHS = 20, 100


def load_rows(path):
    with open(path, encoding="utf-8") as f:
        return [{"Date": r["Date"], "Close": float(r["Close"]), "Volume": float(r["Volume"]), "Stop": int(r["Stop"])} for r in csv.DictReader(f)]


def build_model():
    m = keras.Sequential([keras.layers.Input(shape=(SEQ_LEN, 2)), keras.layers.LSTM(32, return_sequences=True), keras.layers.LSTM(32, return_sequences=True),
                          keras.layers.LSTM(16), keras.layers.Dense(16, activation="relu"), keras.layers.Dense(1)])
    m.compile(optimizer=keras.optimizers.Adam(learning_rate=1e-3), loss="mse")
    return m


def main():
    kind, variant, seeds = sys.argv[1], sys.argv[2], [int(s) for s in sys.argv[3:]]
    rows = load_rows(FILES[kind])
    dates = [r["Date"] for r in rows]
    c = np.array([r["Close"] for r in rows]); v = np.array([r["Volume"] for r in rows])
    cmin, cmax, vmin, vmax = c.min(), c.max(), v.min(), v.max()
    pts = np.column_stack([(c - cmin) / (cmax - cmin), (v - vmin) / (vmax - vmin)])
    n = len(rows) - SEQ_LEN
    X = np.stack([pts[i:i + SEQ_LEN] for i in range(n)]).astype("float32")
    y = c[SEQ_LEN:]
    split = int(n * 0.8)
    ev = {}
    with open(HERE + "/equipment_events_final.csv", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            ev[r["date"]] = r
    if variant == "none":
        flag = np.zeros(len(rows), bool)
    elif variant == "stop43":
        flag = np.array([r["Stop"] == 1 for r in rows])
    elif variant == "stop50":
        flag = np.array([(d in ev) and ev[d]["stop_50"] == "1" for d in dates])
    else:
        raise SystemExit("variant?")
    touched = np.array([flag[i:i + SEQ_LEN + 1].any() for i in range(n)])
    keep = ~touched[:split]
    Xtr, ytr = X[:split][keep], ((y[:split] - cmin) / (cmax - cmin))[keep].astype("float32")
    Xte, yte = X[split:], y[split:]
    tdates = dates[SEQ_LEN + split:]
    is_ev = np.array([d in ev for d in tdates])
    win_ev = np.array([any((dd in ev) for dd in dates[split + i: split + i + SEQ_LEN + 1]) for i in range(len(tdates))])
    meta = {"kind": kind, "variant": variant, "rows": len(rows), "n_train_all": int(split), "n_train_used": int(keep.sum()), "n_excluded": int((~keep).sum()), "n_test": int(len(yte)),
            "test_first": tdates[0], "test_last": tdates[-1], "flag_days": int(flag.sum()), "test_event_days": int(is_ev.sum()), "test_touched": int(win_ev.sum()), "runs": []}
    print(json.dumps({k: w for k, w in meta.items() if k != "runs"}, ensure_ascii=False), flush=True)
    rm = lambda e: float(np.sqrt(np.mean(e ** 2)))
    preds = {}
    for seed in seeds:
        keras.utils.set_random_seed(seed)
        t0 = time.time(); m = build_model(); m.fit(Xtr, ytr, epochs=EPOCHS, verbose=0); sec = time.time() - t0
        p = m.predict(Xte, verbose=0).flatten().astype(float) * (cmax - cmin) + cmin
        e = p - yte
        run = {"seed": seed, "rmse_all": rm(e), "rmse_excl_event_targets": rm(e[~is_ev]), "rmse_excl_touched": rm(e[~win_ev]), "bias_pred_minus_actual": float(e.mean()),
               "event_day_mean_err": float(e[is_ev].mean()), "fit_seconds": round(sec, 1)}
        meta["runs"].append(run); preds[seed] = p
        print(json.dumps(run, ensure_ascii=False), flush=True)
    os.makedirs(HERE + "/lstm", exist_ok=True)
    tag = f"{kind}_{variant}"
    json.dump(meta, open(f"{HERE}/lstm/{tag}.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    with open(f"{HERE}/lstm/{tag}_pred.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f); w.writerow(["date", "actual"] + [f"pred_s{s}" for s in seeds])
        for i, d in enumerate(tdates):
            w.writerow([d, f"{yte[i]:.3f}"] + [f"{preds[s][i]:.3f}" for s in seeds])


if __name__ == "__main__":
    main()
