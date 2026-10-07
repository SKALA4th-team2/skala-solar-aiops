"""적량면 시간 자료를 하루 값으로 바꿔 datasets/jeokryang_daily.csv 를 만든다.

원본의 일사량 열은 시간별 값이 아니라 그날 0시부터 쌓인 누적값이다. 그래서 하루 일사량은 그날의 최댓값이다.
원본(11.6MB)은 저장소에 없다. 받은 파일의 경로를 인자로 주거나 datasets/raw/ 에 아래 이름으로 둔다.

실행 (저장소 루트에서):
    python tools/jeokryang/01_build_daily.py [원본 CSV 경로]
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from common import DAILY, DATASETS

RAW = Path(sys.argv[1]) if len(sys.argv) > 1 else DATASETS / "raw" / "하동_적량면_667831A001_시간자료_20130101_20260331.csv"

d = pd.read_csv(RAW, encoding="utf-8-sig", dtype=str)
d.columns = ["code", "do", "name", "dt", "ta", "tmax", "tmin", "rh", "wd", "ws", "rn", "gsr", "ss", "sm"]
d["dt"] = pd.to_datetime(d["dt"])
print("행:", len(d), "| 기간:", d.dt.min(), "~", d.dt.max(), "| 지점코드:", d.code.unique().tolist(), "| 중복 시각:", int(d.dt.duplicated().sum()))
hours = pd.date_range(d.dt.min(), d.dt.max(), freq="h")
print("있어야 할 시간 수:", len(hours), "| 빠진 시간:", len(hours) - d.dt.nunique())
for c, name in [("ta", "기온"), ("rh", "습도"), ("ws", "풍속"), ("rn", "강수량"), ("gsr", "일사량"), ("ss", "일조시간"), ("sm", "토양수분")]:
    print(f"  {name}: 결측 표시('-') {((d[c] == '-') | d[c].isna()).mean() * 100:.1f}%")

d = d.drop_duplicates("dt").sort_values("dt")
for c in ["ta", "rn", "gsr"]:
    d[c] = pd.to_numeric(d[c].replace("-", np.nan), errors="coerce")
d["date"] = d["dt"].dt.normalize()
d["h"] = d["dt"].dt.hour


def daily(x: pd.DataFrame) -> pd.Series:
    v = x.dropna(subset=["gsr"])
    day = v[(v.h >= 6) & (v.h <= 19)]
    late = v[v.h >= 20]
    # 낮(6~19시) 값이 12개 이상이고 20시 이후 값이 하나라도 있어야 하루 값을 인정한다
    ok = len(day) >= 12 and len(late) >= 1
    predawn = v[v.h <= 4]["gsr"].max() if len(v[v.h <= 4]) else np.nan
    at19 = v[v.h == 19]["gsr"]
    after = (late["gsr"].max() - at19.max()) if (len(late) and len(at19)) else np.nan
    return pd.Series({
        "gsr_mj": v["gsr"].max() if ok else np.nan,   # 하루 일사량 (MJ/m2)
        "n_hours": len(v),                            # 일사량 값이 있는 시간 수
        "predawn_mj": predawn,                        # 해 뜨기 전(0~4시) 누적값. 0 이어야 정상
        "after_sunset_mj": after,                     # 19시 뒤에 더 쌓인 양. 0 이어야 정상
        "tmax_c": x["ta"].max(),                      # 시간별 기온의 하루 최댓값
        "rain_mm": x["rn"].max(),                     # 강수량 열도 누적값이라 최댓값을 쓴다
    })


j = d.groupby("date")[["h", "gsr", "ta", "rn"]].apply(daily)
j = j.reindex(pd.date_range(j.index.min(), j.index.max(), freq="D"))
j.index.name = "date"
j["n_hours"] = j["n_hours"].fillna(0).astype(int)
j.round(2).to_csv(DAILY)
print(f"\n{DAILY.name}: {len(j)}행, {j.index.min().date()} ~ {j.index.max().date()}, 하루 일사량이 유효한 날 {int(j.gsr_mj.notna().sum())}일")

# 일사량 열이 누적값이라는 확인: 하루 안에서 줄어들지 않고 23시 값이 0 보다 큰 날의 비율
g = d.dropna(subset=["gsr"])
mono = g.groupby("date")["gsr"].apply(lambda s: len(s) >= 20 and bool(np.all(np.diff(s.values) >= -1e-9)) and s.values[-1] > 0.5)
full = g.groupby("date")["gsr"].size() >= 20
print("값이 20시간 이상 있는 날 가운데 누적 모양인 날:", f"{mono[full].mean() * 100:.1f}%")
