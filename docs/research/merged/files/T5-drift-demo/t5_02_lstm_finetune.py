"""T5 대조 2: 일사량 예보를 두 번째 입력으로 쓴 실습 LSTM 에 수준 변화를 주입한 뒤, 실습 코드의 재학습(fine_tune)을 그대로 따라 했을 때 무엇이 달라지는가.

- 자료: merged/gap1/hadong_upload_forecast_jma.csv (Date, Close=그날 발전량 kWh, Volume=다음 날에 대한 하루 전 일사량 예보 MJ/m2). 읽기만 한다.
- 모델과 절차는 /Users/psm/workspace/skala-aiops/project 의 serving_app/lstm_model.py, data/features.py, serving_app/train_and_register.py 를 읽어 옮겨 적었다(import 하지 않음).
    build_model: LSTM 32 -> 32 -> 16, Dense 16(relu), Dense 1, Adam 1e-3, mse.  BASE_EPOCHS 100.
    fine_tune  : 41행 -> 창 21개 -> 앞 16개로 학습(Adam 1e-4, 10 epoch), 뒤 5개로 게이트 RMSE.
- 학습: 대상일 2023-11-07 ~ 2025-02-28 (보완 조사 2 의 구간 B 와 같음). 스케일러는 학습에 쓰인 행으로만 맞춘다.
- 주입: 시작일 s 부터 발전량에 배율을 곱한다(예보는 그대로). 시작일은 2025-03-08 부터 7일 간격.
- 배치: 행 s ~ s+40 (41행, 모두 변화 뒤). 대상 21일 = s+20 ~ s+40. 재학습 뒤 평가 = 그다음 21일(s+41 ~ s+61).
- 예측 시점은 대상일 전날 저녁을 전제로 한다(하루 전 예보의 하루 합계는 전날 09시 KST 실행분까지로 정해진다는 보완 조사 2 의 확인에 기댄다).
사용: python t5_02_lstm_finetune.py <seed>
"""
import os
import sys
import time
from pathlib import Path

os.environ["TF_CPP_MIN_LOG_LEVEL"] = "2"
import numpy as np
import pandas as pd
import tensorflow as tf
from tensorflow import keras

SEED = int(sys.argv[1])
tf.config.threading.set_intra_op_parallelism_threads(2)
tf.config.threading.set_inter_op_parallelism_threads(1)
keras.utils.set_random_seed(SEED)
HERE = Path(__file__).resolve().parent
S = HERE.parents[1]
SEQ = 20
FACTORS = (1.0, 0.86, 0.70)
FT = {"실습 설정(1e-4, 10 epoch)": (1e-4, 10), "강한 설정(1e-3, 50 epoch)": (1e-3, 50)}

df = pd.read_csv(S / "merged" / "gap1" / "hadong_upload_forecast_jma.csv", parse_dates=["Date"])
dates = df.Date.values.astype("datetime64[D]")
close0 = df.Close.values.astype(float)
vol = df.Volume.values.astype(float)
N = len(df)
assert (np.diff(dates).astype(int) == 1).all()
# 날짜 정렬 확인: Volume[d] 가 d+1 일의 하루 전 예보인가
pr = pd.read_csv(S / "solar" / "d2r" / "wx_prevruns_daily.csv", parse_dates=["date"]).set_index("date")["shortwave_radiation_previous_day1"]
nxt = pr.reindex(pd.to_datetime(dates) + pd.Timedelta(days=1)).values
print(f"[seed {SEED}] 행 {N} ({dates[0]} ~ {dates[-1]}) | Volume[d] 와 d+1 일의 하루 전 예보의 최대 차이 {np.nanmax(np.abs(nxt - vol)):.6f} MJ/m2, 같은 날(d) 예보와의 최대 차이 {np.nanmax(np.abs(pr.reindex(pd.to_datetime(dates)).values - vol)):.3f}")


def idx(d):
    return int(np.where(dates == np.datetime64(d))[0][0])


def build_model():
    m = keras.Sequential([
        keras.layers.Input(shape=(SEQ, 2)),
        keras.layers.LSTM(32, return_sequences=True),
        keras.layers.LSTM(32, return_sequences=True),
        keras.layers.LSTM(16),
        keras.layers.Dense(16, activation="relu"),
        keras.layers.Dense(1),
    ])
    m.compile(optimizer=keras.optimizers.Adam(learning_rate=1e-3), loss="mse")
    return m


t_lo, t_hi = idx("2023-11-07"), idx("2025-02-28")
rows_tr = slice(t_lo - SEQ, t_hi + 1)
cmin, cmax = close0[rows_tr].min(), close0[rows_tr].max()
vmin, vmax = vol[rows_tr].min(), vol[rows_tr].max()


def sc_c(x):
    return (x - cmin) / (cmax - cmin)


def windows(close, targets):
    X = np.stack([np.column_stack([sc_c(close[t - SEQ:t]), (vol[t - SEQ:t] - vmin) / (vmax - vmin)]) for t in targets]).astype("float32")
    return X, close[np.array(targets)]


def pred(model, X):
    return model(X, training=False).numpy().ravel() * (cmax - cmin) + cmin


def rmse(a, b):
    return float(np.sqrt(np.mean((np.asarray(a) - np.asarray(b)) ** 2)))


T_tr = list(range(t_lo, t_hi + 1))
Xtr, ytr = windows(close0, T_tr)
t0 = time.time()
base = build_model()
base.fit(Xtr, sc_c(ytr).astype("float32"), epochs=100, verbose=0)
train_rmse = rmse(pred(base, Xtr), ytr)
print(f"[seed {SEED}] 학습 표본 {len(T_tr)}개(대상일 {dates[t_lo]} ~ {dates[t_hi]}), 학습 RMSE {train_rmse:.2f}kWh, 학습 구간 치우침 {float(np.mean(pred(base, Xtr) - ytr)):+.2f}kWh, 학습 시간 {time.time() - t0:.0f}초 | 스케일러 Close {cmin:.3f}~{cmax:.3f}, Volume {vmin:.3f}~{vmax:.3f}")
W0 = base.get_weights()
ft_model = build_model()

starts = []
s = idx("2025-03-08")
while s + 61 <= N - 1:
    starts.append(s); s += 7
print(f"[seed {SEED}] 주입 시작일 {len(starts)}개 ({dates[starts[0]]} ~ {dates[starts[-1]]})")

out = []
for f in FACTORS:
    for s in starts:
        c = close0.copy(); c[s:] *= f
        Tb = list(range(s + 20, s + 41)); Tn = list(range(s + 41, s + 62))
        Xb, yb = windows(c, Tb); Xn, yn = windows(c, Tn)
        pb = pred(base, Xb); pn = pred(base, Xn)
        k = float(np.clip(yb.sum() / pb.sum(), 0.5, 1.5))
        r = dict(seed=SEED, factor=f, start=str(dates[s]), train_rmse=train_rmse,
                 batch_rmse=rmse(pb, yb), batch_bias=float(np.mean(pb - yb)), batch_bias_pct=float((pb.sum() - yb.sum()) / yb.sum() * 100),
                 gate5_before=rmse(pb[16:], yb[16:]),
                 next_rmse_frozen=rmse(pn, yn), next_bias_frozen=float(np.mean(pn - yn)), next_bias_pct_frozen=float((pn.sum() - yn.sum()) / yn.sum() * 100),
                 level_k=k, next_rmse_level=rmse(pn * k, yn), next_bias_level=float(np.mean(pn * k - yn)), next_bias_pct_level=float(((pn * k).sum() - yn.sum()) / yn.sum() * 100))
        for nm, (lr, ep) in FT.items():
            ft_model.set_weights(W0)
            ft_model.compile(optimizer=keras.optimizers.Adam(learning_rate=lr), loss="mse")
            ft_model.fit(Xb[:16], sc_c(yb[:16]).astype("float32"), epochs=ep, verbose=0)
            qb = pred(ft_model, Xb); qn = pred(ft_model, Xn)
            tag = "ft" if nm.startswith("실습") else "ftx"
            r.update({f"gate5_{tag}": rmse(qb[16:], yb[16:]), f"next_rmse_{tag}": rmse(qn, yn), f"next_bias_{tag}": float(np.mean(qn - yn)),
                      f"next_bias_pct_{tag}": float((qn.sum() - yn.sum()) / yn.sum() * 100), f"next_absdiff_{tag}": float(np.mean(np.abs(qn - pn)))})
        out.append(r)
    print(f"[seed {SEED}] 배율 {f} 끝, 누적 {time.time() - t0:.0f}초", flush=True)
pd.DataFrame(out).to_csv(HERE / f"t5_02_ft_seed{SEED}.csv", index=False)
print(f"[seed {SEED}] 저장 t5_02_ft_seed{SEED}.csv, 전체 {time.time() - t0:.0f}초")
