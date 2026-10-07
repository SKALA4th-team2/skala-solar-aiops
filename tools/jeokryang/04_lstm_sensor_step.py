"""적량면 센서의 수준이 바뀐 사건(2024년 2월 초)을 실습 LSTM 과 같은 구조로 재현한다.

입력은 최근 20일의 (발전량, 그 다음 날의 관측 일사량)이다. 날씨 칸의 마지막이 대상일의 관측이므로
"그날 날씨로 그날 발전량을 맞히는" 모델이다. 하루 전 예측 모델이 아니다.
구조와 학습 설정은 project/ 의 실습 코드와 같게 했다(LSTM 32-32-16, Dense 16, Dense 1, 100 epoch, 학습률 1e-3).
재학습도 실습과 같다(최근 41행으로 만든 21문제 가운데 앞 16개로 이어서 학습, 학습률 1e-4, 10 epoch, 뒤 5개로 게이트).
project/ 의 모듈은 import 하지 않는다.

실행 (저장소 루트에서, tensorflow 가 있는 파이썬으로. 몇 분 걸린다):
    python tools/jeokryang/04_lstm_sensor_step.py
"""
import json
import os

os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"

import numpy as np
import pandas as pd
from tensorflow import keras

from common import OUT, bias_pct, load_joined, rmse

SEQ = 20
STEP = pd.Timestamp("2024-02-01")          # 센서 수준이 바뀐 날로 본 날짜 (02_compare_with_gwangyang.py 의 결과)
a = load_joined()["2022-01-01":"2024-07-31"].copy()
print("기간", a.index.min().date(), "~", a.index.max().date(), "| 적량 빈 날", int(a.jr_gsr.isna().sum()), "| 광양 빈 날", int(a.gy_gsr.isna().sum()), "| 정지 표시일", int(a.stop_day.sum()))
print("적량이 비어서 앞뒤 값으로 메운 날:", [d.strftime("%Y-%m-%d") for d in a.index[a.jr_gsr.isna()]])
a["jr"] = a.jr_gsr.interpolate(limit=5).ffill().bfill()      # 빈 날은 앞뒤 값으로 메운다
a["gy"] = a.gy_gsr.interpolate(limit=5).ffill().bfill()


def build(col):
    close = a.gen_kwh.values.astype("float32")
    vol = a[col].shift(-1).values.astype("float32")          # d 행에 d+1 일의 날씨를 둔다
    n = len(a) - 1
    return close[:n], vol[:n], a.index[:n]


def windows(close, vol, dates, cmin, cmax, vmin, vmax):
    c = (close - cmin) / (cmax - cmin)
    v = (vol - vmin) / (vmax - vmin)
    x = np.stack([np.stack([c[i:i + SEQ], v[i:i + SEQ]], axis=1) for i in range(len(c) - SEQ)])
    return x.astype("float32"), close[SEQ:], dates[SEQ:]


def new_model():
    m = keras.Sequential([
        keras.layers.Input(shape=(SEQ, 2)),
        keras.layers.LSTM(32, return_sequences=True),
        keras.layers.LSTM(32, return_sequences=True),
        keras.layers.LSTM(16),
        keras.layers.Dense(16, activation="relu"),
        keras.layers.Dense(1),
    ])
    m.compile(optimizer=keras.optimizers.Adam(1e-3), loss="mse")
    return m


day = pd.Timedelta(days=1)
rows = []
inject = []
for col, label in (("jr", "적량 센서"), ("gy", "광양 관측(대조)")):
    close, vol, dates = build(col)
    train_end = STEP - 22 * day
    in_train = dates <= train_end
    cmin, cmax = close[in_train].min(), close[in_train].max()          # 스케일은 학습 구간으로만 맞춘다
    vmin, vmax = vol[in_train].min(), vol[in_train].max()
    x, y, t = windows(close, vol, dates, cmin, cmax, vmin, vmax)
    seg = {
        "학습": t <= train_end,
        "정상 배치(계단 전 21일)": (t >= STEP - 21 * day) & (t < STEP),
        "드리프트 배치 1(계단 뒤 1~21일)": (t >= STEP) & (t < STEP + 21 * day),
        "드리프트 배치 2(22~42일)": (t >= STEP + 21 * day) & (t < STEP + 42 * day),
        "그 뒤 90일": (t >= STEP + 42 * day) & (t < STEP + 132 * day),
    }
    xtr, ytr = x[seg["학습"]], y[seg["학습"]]
    k = int(len(xtr) * 0.8)
    for seed in (42, 43, 44):
        keras.utils.set_random_seed(seed)
        m = new_model()
        m.fit(xtr[:k], (ytr[:k] - cmin) / (cmax - cmin), epochs=100, verbose=0)

        def pred(model, xx):
            return model.predict(xx, verbose=0).flatten() * (cmax - cmin) + cmin

        row = {"입력": label, "씨앗": seed, "학습 표본": int(k), "학습 때 시험 RMSE": rmse(ytr[k:], pred(m, xtr[k:]))}
        for name in list(seg)[1:]:
            p = pred(m, x[seg[name]])
            row[name + " RMSE"] = rmse(y[seg[name]], p)
            row[name + " 치우침%"] = bias_pct(y[seg[name]], p)
        # 실습의 재학습: 드리프트 배치 1 이 들어온 시점의 최근 41행, 곧 대상일이 계단 뒤 1~21일인 21문제
        xf, yf = x[seg["드리프트 배치 1(계단 뒤 1~21일)"]], y[seg["드리프트 배치 1(계단 뒤 1~21일)"]]
        kf = int(len(xf) * 0.8)
        m2 = keras.models.clone_model(m)
        m2.set_weights(m.get_weights())
        m2.compile(optimizer=keras.optimizers.Adam(1e-4), loss="mse")
        m2.fit(xf[:kf], (yf[:kf] - cmin) / (cmax - cmin), epochs=10, verbose=0)
        row["재학습 게이트(5개) RMSE"] = rmse(yf[kf:], pred(m2, xf[kf:]))
        for name in ("드리프트 배치 2(22~42일)", "그 뒤 90일"):
            p = pred(m2, x[seg[name]])
            row["재학습 뒤 " + name + " RMSE"] = rmse(y[seg[name]], p)
            row["재학습 뒤 " + name + " 치우침%"] = bias_pct(y[seg[name]], p)
        if col == "jr":
            # 확인 실험: 실제 계단이 없는 구간(학습 때 시험 구간)에서 날씨 칸의 뒤쪽 j 칸만 1.3배로 올린다.
            # j = 1 은 계단 바로 다음 날, j = 20 은 창이 새 수준으로 다 채워진 뒤에 해당한다.
            xb, yb = xtr[k:], ytr[k:]
            for j in (0, 1, 5, 10, 15, 20):
                xs = xb.copy()
                if j:
                    raw = xs[:, SEQ - j:, 1] * (vmax - vmin) + vmin
                    xs[:, SEQ - j:, 1] = (raw * 1.3 - vmin) / (vmax - vmin)
                p = pred(m, xs)
                inject.append({"씨앗": seed, "올린 칸 수": j, "표본": len(yb), "RMSE": rmse(yb, p), "치우침%": bias_pct(yb, p)})
        rows.append(row)
        print(json.dumps({kk: (round(v, 1) if isinstance(v, float) else v) for kk, v in row.items()}, ensure_ascii=False), flush=True)

d = pd.DataFrame(rows)
OUT.mkdir(exist_ok=True)
d.round(3).to_csv(OUT / "04_lstm_sensor_step_result.csv", index=False)
pd.DataFrame(inject).round(3).to_csv(OUT / "04_injected_step_check.csv", index=False)
print("\n=== 인위 계단 확인 (적량 입력 모델, 계단이 없는 구간의 날씨 칸 뒤쪽 j 칸을 1.3배로) : 씨앗 3개 평균 ===")
print(pd.DataFrame(inject).groupby("올린 칸 수")[["표본", "RMSE", "치우침%"]].mean().round(1).to_string())
print("\n=== 씨앗 3개 평균 ===")
print(d.drop(columns=["씨앗"]).groupby("입력").mean(numeric_only=True).round(1).T.to_string())
