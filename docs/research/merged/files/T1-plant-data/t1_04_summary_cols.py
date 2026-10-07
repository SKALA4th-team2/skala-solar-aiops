"""T1 보조: 요약 열 최대(시간별_kw), 최소(시간별_kw) 의 뜻과 자릿수 규칙이 바뀌는 날을 원본으로 다시 확인한다.

실행: PYTHONDONTWRITEBYTECODE=1 /Users/psm/workspace/skala-aiops/mlflow/.venv/bin/python t1_04_summary_cols.py > t1_04_summary_cols.txt
"""
import os
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.abspath(os.path.join(HERE, "..", "..", "solar", "data_15043409.csv"))
df = pd.read_csv(RAW, encoding="cp949", dtype=str)
df["date"] = pd.to_datetime(df["년월일"])
df = df.sort_values("date").reset_index(drop=True)
HC = [str(i) for i in range(1, 25)]
hv = df[HC].map(Decimal)
mx = hv.max(axis=1)
pos_min = hv.apply(lambda r: min([x for x in r if x > 0], default=Decimal(0)), axis=1)
tmax = df["최대(시간별_kw)"].map(Decimal)
tmin = df["최소(시간별_kw)"].map(Decimal)


def q(x, places, mode):
    return x.quantize(Decimal(1).scaleb(-places), rounding=mode)


print("최대(시간별_kw) == 시간값 최댓값:", int((tmax == mx).sum()), "/", len(df), "일")
diff = df[tmax != mx]
print("  다른 날", len(diff), "일, 기간", diff.date.min().date(), "~", diff.date.max().date(),
      ", 그중 소수 둘째 자리 아래 버림과 일치", int(sum(q(a, 2, ROUND_DOWN) == b for a, b in zip(mx[diff.index], tmax[diff.index]))), "일")
print("최소(시간별_kw) == 0보다 큰 시간값의 최솟값:", int((tmin == pos_min).sum()), "/", len(df), "일")
segs = [("2013-01-01", "2017-02-28"), ("2017-03-01", "2020-07-31"), ("2020-08-01", "2022-06-30"), ("2022-07-01", "2023-03-31"), ("2023-04-01", "2026-02-28")]
for a, b in segs:
    m = (df.date >= a) & (df.date <= b)
    idx = df.index[m]
    ex = int(sum(tmin[i] == pos_min[i] for i in idx))
    tr = int(sum(tmin[i] == q(pos_min[i], 2, ROUND_DOWN) for i in idx))
    r1 = int(sum(tmin[i] == q(pos_min[i], 1, ROUND_HALF_UP) for i in idx))
    print(f"  {a}~{b} ({len(idx)}일): 원값과 일치 {ex}, 소수 둘째 자리 아래 버림과 일치 {tr}, 소수 첫째 자리 반올림과 일치 {r1}")
