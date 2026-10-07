"""T1 보조: ASOS 분석이 쓴 '경사각 27도'와 공식 설치각 30도, 사전 조사 청천 모형의 35도가 얼마나 다른 값인지 본다.

ASOS 분석(a1_02_station.py)은 광양(266)의 수평면 하루 일사량을 정남 경사면으로 환산한 값과 하동 발전량의
상관이 학습 구간(2013-01-01 ~ 2022-12-31, 발전량 > 0)에서 가장 높은 경사각을 골랐다. 같은 계산을 경사각별로 다시 한다.
환산식(Erbs 확산 비율, Liu-Jordan 등방성)은 ../../asos/a1/a1_common.py 의 tilted() 를 옮겨 적은 것이다.
주의: 같은 날의 관측 일사량과 발전량의 관계다. 예측 시점(대상일 전날)에는 받을 수 없는 값이다.

실행: PYTHONDONTWRITEBYTECODE=1 /Users/psm/workspace/skala-aiops/mlflow/.venv/bin/python t1_02_tilt.py > t1_02_tilt.txt
"""
import os

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
FULL = os.path.abspath(os.path.join(HERE, "..", "..", "asos", "hadong_daily_full.csv"))
LAT_GY = 34.94          # ASOS 분석이 가조시간에 맞춰 추정한 광양 관측소 위도


def solar_geom(dates, lat_deg):
    doy = pd.DatetimeIndex(dates).dayofyear.values.astype(float)
    phi = np.radians(lat_deg)
    dr = 1 + 0.033 * np.cos(2 * np.pi * doy / 365.0)
    delta = 0.409 * np.sin(2 * np.pi * doy / 365.0 - 1.39)
    ws = np.arccos(np.clip(-np.tan(phi) * np.tan(delta), -1, 1))
    H0 = (24 * 60 / np.pi) * 0.0820 * dr * (ws * np.sin(phi) * np.sin(delta) + np.cos(phi) * np.cos(delta) * np.sin(ws))
    return H0, delta, ws


def tilted(H, dates, lat_deg, beta_deg, rho=0.2):
    H = np.asarray(H, dtype=float)
    H0, delta, ws = solar_geom(dates, lat_deg)
    phi = np.radians(lat_deg)
    KT = np.clip(H / H0, 0.01, 0.85)
    f1 = np.where(KT < 0.715, 1 - 0.2727 * KT + 2.4495 * KT**2 - 11.9514 * KT**3 + 9.3879 * KT**4, 0.143)
    f2 = np.where(KT < 0.722, 1 + 0.2832 * KT - 2.5557 * KT**2 + 0.8448 * KT**3, 0.175)
    fd = np.where(ws <= np.radians(81.4), f1, f2)
    Hd = fd * H
    b = np.radians(beta_deg)
    wsp = np.minimum(ws, np.arccos(np.clip(-np.tan(phi - b) * np.tan(delta), -1, 1)))
    Rb = ((np.cos(phi - b) * np.cos(delta) * np.sin(wsp) + wsp * np.sin(phi - b) * np.sin(delta))
          / (np.cos(phi) * np.cos(delta) * np.sin(ws) + ws * np.sin(phi) * np.sin(delta)))
    return (H - Hd) * Rb + Hd * (1 + np.cos(b)) / 2 + H * rho * (1 - np.cos(b)) / 2


d = pd.read_csv(FULL, parse_dates=["date"]).set_index("date")
d = d.loc["2013-01-01":"2025-12-31"]
gen, gsr = d.gen_kwh, d.gy_gsr_obs
tr = (d.index <= "2022-12-31") & (gen > 0) & gsr.notna()
te = (d.index >= "2023-01-01") & (gen > 0) & gsr.notna()
print(f"학습 구간 {int(tr.sum())}일(2013-01-01~2022-12-31, 발전량>0, 광양 일사량 관측 있음), 평가 구간 {int(te.sum())}일(2023-01-01~2025-12-31)")
rows = []
for beta in list(range(0, 61, 1)):
    ht = pd.Series(tilted(gsr.values, d.index, LAT_GY, beta), index=d.index)
    rows.append((beta, np.corrcoef(ht[tr], gen[tr])[0, 1], np.corrcoef(ht[te], gen[te])[0, 1]))
r = pd.DataFrame(rows, columns=["경사각", "학습 r", "평가 r"]).set_index("경사각")
best = r["학습 r"].idxmax()
print(f"학습 구간 상관이 가장 높은 경사각: {best}도 (r={r.loc[best, '학습 r']:.4f})")
print(r.loc[[0, 20, 25, 27, 30, 33, 35, 40]].round(4).to_string())
print(f"27도와 30도의 차이: 학습 r {r.loc[27, '학습 r'] - r.loc[30, '학습 r']:+.4f}, 평가 r {r.loc[27, '평가 r'] - r.loc[30, '평가 r']:+.4f}")
ok = r[r["학습 r"] >= r["학습 r"].max() - 0.001]
print(f"학습 r 이 최댓값에서 0.001 안에 드는 경사각 범위: {ok.index.min()}~{ok.index.max()}도")
h27 = tilted(gsr.values, d.index, LAT_GY, 27)
h30 = tilted(gsr.values, d.index, LAT_GY, 30)
m = gsr.notna().values
print(f"27도 환산값과 30도 환산값의 상관 {np.corrcoef(h27[m], h30[m])[0, 1]:.5f}, 비(30도/27도)의 범위 {np.nanmin(h30[m] / h27[m]):.3f}~{np.nanmax(h30[m] / h27[m]):.3f}")
