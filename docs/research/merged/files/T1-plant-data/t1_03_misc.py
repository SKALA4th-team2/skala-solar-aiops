"""T1 보조: (1) 발전소 공식 좌표와 광양 ASOS 관측소 사이 거리, (2) 두 조사의 자료 기간과 시험 구간, (3) 설비 나이.

좌표 출처
  발전소: 남부발전 '태양광발전소 위치 정보' CSV (../../solar/verify1a/r2/data_15147894.csv) 의 '하동 하수처리장 태양광' 행
  광양시(266) 관측소: 사전 조사 research_3a-weather-kma 에 적힌 북위 34.9434, 동경 127.6914 (이 스크립트에서 원문을 다시 열지는 않았다)

실행: PYTHONDONTWRITEBYTECODE=1 /Users/psm/workspace/skala-aiops/mlflow/.venv/bin/python t1_03_misc.py > t1_03_misc.txt
"""
import os
from math import asin, cos, radians, sin, sqrt

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
SP = os.path.abspath(os.path.join(HERE, "..", ".."))

# (1) 거리
loc = pd.read_csv(os.path.join(SP, "solar", "verify1a", "r2", "data_15147894.csv"), encoding="cp949")
row = loc[loc["발전소명"].str.contains("하수처리장")].iloc[0]
plat, plon = float(row["위도"]), float(row["경도"])
slat, slon = 34.9434, 127.6914


def hav(a, b, c, d):
    a, b, c, d = map(radians, (a, b, c, d))
    h = sin((c - a) / 2) ** 2 + cos(a) * cos(c) * sin((d - b) / 2) ** 2
    return 2 * 6371.0 * asin(sqrt(h))


print(f"(1) 발전소 좌표(남부발전 CSV): 북위 {plat}, 동경 {plon} / 호기 {row['호기']}")
print(f"    광양시(266) 관측소까지 대권 거리 {hav(plat, plon, slat, slon):.1f}km, 위도 차 {plat - slat:+.4f}도")
print(f"    ASOS 분석이 가조시간으로 추정한 광양 위도 34.94 와 사전 조사에 적힌 34.9434 의 차 {34.94 - slat:+.4f}도")

# (2) 기간과 시험 구간
raw = pd.read_csv(os.path.join(SP, "solar", "data_15043409.csv"), encoding="cp949")
rd = pd.to_datetime(raw["년월일"]).sort_values().reset_index(drop=True)
up = pd.read_csv(os.path.join(SP, "asos", "hadong_upload.csv"), parse_dates=["Date"])
SEQ = 20
for nm, dts in (("원본 전체(사전 조사 쪽 D1 의 표본)", rd), ("ASOS 쪽 업로드 파일 hadong_upload.csv", up.Date)):
    n = len(dts)
    ns = n - SEQ
    k = int(ns * 0.8)
    print(f"(2) {nm}: 행 {n}, {dts.iloc[0].date()}~{dts.iloc[-1].date()}, 20일 창 표본 {ns}개, 앞 80% 학습 {k}개(정답일 {dts.iloc[SEQ].date()}~{dts.iloc[SEQ + k - 1].date()}), "
          f"뒤 20% 시험 {ns - k}개(정답일 {dts.iloc[SEQ + k].date()}~{dts.iloc[-1].date()})")
miss = sorted(set(rd) - set(up.Date))
print(f"    원본에는 있고 업로드 파일에는 없는 날 {len(miss)}일: {miss[0].date()}, {miss[1].date()}, {miss[2].date()}~{miss[-1].date()}")

# (3) 설비 나이
for nm, start in (("준공(건설 기간 끝) 2011-12", pd.Timestamp("2011-12-01")), ("전력시장 수급 개시 2012-03", pd.Timestamp("2012-03-01"))):
    for at in ("2021-05-18", "2026-10-07"):
        m = (pd.Timestamp(at).year - start.year) * 12 + pd.Timestamp(at).month - start.month
        print(f"(3) {nm} 기준 {at} 시점: 만 {m // 12}년 {m % 12}개월")
