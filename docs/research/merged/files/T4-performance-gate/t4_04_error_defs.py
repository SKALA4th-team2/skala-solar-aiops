"""T4: 오차율 정의(용량 기준 포함)에 따라 같은 예측이 얼마로 보이는지, 제도의 6%·4% 를 그대로 쓸 수 있는지.

공통 구간 898일(2023-07-17 ~ 2025-12-30)에서, 용량 50kW 와 55kW 두 가정으로 계산한다. 정의는 사전 조사 D2(solar/d2r/04_metrics.py)와 같다.
  A  합계 오차율      = sum|예측-실제| / sum 실제
  B  용량 x 24시간    = 평균|예측-실제| / (용량 x 24)
  C  용량 x 유효 시간 = sum|예측-실제| / (용량 x 실제 이용률이 10% 이상인 시간 수의 합)
  D  시간대 환산      = 하루 합계 예측을 '직전 20일 시간 분포'로 24칸에 나눈 뒤, 실제 이용률 10% 이상인 시간대의 |예측_h-실제_h| / 용량 평균
  E  24시간 전체 환산 = D 와 같은 시간대 예측을 24칸 모두에서 평균(밤 시간 포함). 문헌의 '24시간 전체 평균 NMAE' 와 같은 눈금
     (제도는 시간대별 예측을 요구하고, 이 모델은 하루 합계만 낸다. D 는 환산값이지 제도상의 오차율이 아니다)
입력: t4_preds.pkl, 발전 실적 원본의 시간값. 출력: t4_error_defs.csv, 표준출력
"""
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
Dd = pd.read_pickle(HERE / "t4_preds.pkl")
P, Y = Dd["P"], Dd["Y"]
pd.set_option("display.width", 250)
pd.set_option("display.max_colwidth", 64)

raw = pd.read_csv(ROOT / "solar" / "data_15043409.csv", encoding="cp949")
raw["date"] = pd.to_datetime(raw["년월일"])
raw = raw.sort_values("date").reset_index(drop=True)
HC = [str(i) for i in range(1, 25)]
HH = raw[HC].to_numpy(float)
pos = pd.Series(np.arange(len(raw)), index=raw["date"])
print(f"시간값: 최대 {HH.max():.3f} kW, 50kW 초과 {int((HH > 50).sum())}칸({int((HH > 50).any(axis=1).sum())}일), 52.8kW 초과 {int((HH > 52.8).sum())}칸, 55kW 초과 {int((HH > 55).sum())}칸")
top = np.sort(HH.ravel())[::-1][:5]
print("  가장 큰 시간값 5개:", np.round(top, 3).tolist())


def profile(i, k=20):
    s = HH[i - k:i].sum(axis=0)
    return s / s.sum()


def defs(idx, p, cap):
    ii = pos.loc[idx].to_numpy()
    A = HH[ii]
    y = Y.loc[idx].to_numpy()
    Q = A >= 0.1 * cap
    n10 = Q.sum(axis=1)
    ae = np.abs(p - y)
    PROF = np.vstack([profile(i) for i in ii])
    err = np.abs(p[:, None] * PROF - A) / cap * 100
    e = err[Q]
    return {"A 합계 오차율%": ae.sum() / y.sum() * 100, "B 용량x24h%": ae.mean() / (cap * 24) * 100, "C 용량x유효시간%": ae.sum() / (cap * n10.sum()) * 100,
            "D 시간대 환산%": e.mean(), "D 6% 이하 시간대%": (e <= 6).mean() * 100, "D 4% 이하 시간대%": (e <= 4).mean() * 100,
            "E 24시간 전체 환산%": err.mean(),      # 문헌의 '24시간 전체 평균 NMAE' 에 대응하는 환산값(밤 시간 포함)
            "RMSE": float(np.sqrt(((p - y) ** 2).mean())), "RMSE/(용량x24)%": float(np.sqrt(((p - y) ** 2).mean())) / (cap * 24) * 100, "유효 시간/일": n10.mean()}


ROWS = [
    ("하루 합계를 완벽히 맞힘(바닥값)", None),
    ("기준 어제 값", "기준 어제 값"), ("기준 7일 평균", "기준 7일 평균"), ("기준 20일 평균", "기준 20일 평균"),
    ("가벼운 모델 발전량만(사전 D2 Ridge)", "사전 D2 Ridge: 발전량만"),
    ("실습 LSTM 발전량만(2013~ 학습)", "보완 LSTM(T1): 발전량+상수(2013~ 학습)"),
    ("실습 LSTM 발전량만(ASOS 분할 A)", "ASOS LSTM(분할 A): 발전량만(둘째 열 0)"),
    ("규칙C: 7일 효율 x 24h 예보", "규칙C 7일 효율(24h 예보) x 24h 예보"),
    ("실습 LSTM 24h 예보로 학습", "보완 LSTM(T1): 발전량+24h 일사량 예보(358개 학습)"),
    ("실습 LSTM ASOS 로 학습, 24h 예보로 서빙", "보완 LSTM(서빙 교체): ASOS 실제로 학습, T-1·T 칸을 24h 예보로 서빙"),
    ("실습 LSTM ASOS 로 학습, 48h 예보로 서빙", "보완 LSTM(서빙 교체): ASOS 실제로 학습, T 칸 48h 예보·T-1 칸 24h 예보"),
    ("상한: 실습 LSTM 재분석 실제 일사량", "보완 LSTM(T1): 발전량+대상일 실제 재분석 일사량(2013~ 학습)"),
    ("상한: 실습 LSTM ASOS 실제 일사량", "ASOS LSTM(실습 절차): forecast_proxy.csv, 발전량+대상일 실제 광양 일사량"),
]
out = []
for wname, (a, b) in {"C898": ("2023-07-17", "2025-12-30"), "T1_958": ("2023-07-17", "2026-02-28")}.items():
    idx = Y.loc[a:b].index
    for cap in (50.0, 55.0):
        for name, lab in ROWS:
            if lab is None:
                ms = [defs(idx, Y.loc[idx].to_numpy(), cap)]
            else:
                ms = [defs(idx, s.reindex(idx).to_numpy(), cap) for s in P[lab].values() if s.reindex(idx).notna().all()]
            if not ms:
                continue
            m = pd.DataFrame(ms).mean().to_dict()
            out.append({"구간": wname, "용량": cap, "예측": name, "시드 수": len(ms), **m})
O = pd.DataFrame(out)
O.to_csv(HERE / "t4_error_defs.csv", index=False)
for wname in ("C898", "T1_958"):
    for cap in (50.0, 55.0):
        s = O[(O["구간"] == wname) & (O["용량"] == cap)].drop(columns=["구간", "용량"])
        print(f"\n=== 구간 {wname}, 용량 {cap:.0f}kW 가정 (유효 시간 하루 평균 {s['유효 시간/일'].iloc[0]:.2f}시간)")
        print(s.drop(columns=["유효 시간/일"]).round(2).to_string(index=False))

# 사전 조사 5번이 직접 계산한 '전날 값 5.6%(용량 55kW, 2013~2026)' 과 D2 의 '어제 값 5.59%(50kW, 958일)' 가 같은 값인지
print("\n=== 두 문서의 '어제 값 5.6%' 대조")
for a, b, lab in [("2013-01-02", "2026-02-28", "전 기간(2013-01-02 ~ 2026-02-28)"), ("2023-07-17", "2026-02-28", "T1 958일"), ("2023-05-31", "2025-12-31", "ASOS 분할 A 946일")]:
    idx = Y.loc[a:b].index
    mae = np.abs(Y.shift(1).loc[idx] - Y.loc[idx]).mean()
    mae_const = np.abs(Y.loc[:pd.Timestamp(a) - pd.Timedelta(days=1)].mean() - Y.loc[idx]).mean() if a != "2013-01-02" else np.nan
    print(f"  {lab:34s} 어제 값 MAE {mae:6.2f} kWh | 50kW 기준 {mae / 1200 * 100:.2f}% | 55kW 기준 {mae / 1320 * 100:.2f}% | 구간 이전 평균 고정값 MAE/(50x24) {mae_const / 1200 * 100:.2f}%")
