"""t3_05: 예보 파일의 2024-01-24 ~ 02-15 구간 값이 어느 모델에서 왔는지 본다.

Open-Meteo Previous Runs API 를 2024-02-01 ~ 02-02 이틀 치만, 모델을 나눠 한 번(3.5KB), 모델 지정 없이 한 번(1.4KB) 불렀다.
키와 로그인은 쓰지 않았다. 받은 시각은 api/fetch_time_gapmodel.txt 에 있다.
"""
import json

import numpy as np
import pandas as pd

import t3_common as c

m = pd.DataFrame(json.load(open(c.HERE / "api" / "prev_gap_models.json"))["hourly"])
d = pd.DataFrame(json.load(open(c.HERE / "api" / "prev_gap_default.json"))["hourly"])
m["time"] = pd.to_datetime(m["time"]); d["time"] = pd.to_datetime(d["time"])
x = m.merge(d, on="time")
x.columns = [k.replace("shortwave_radiation_previous_day1", "pd1") for k in x.columns]
day = x[(x["time"].dt.hour >= 7) & (x["time"].dt.hour <= 18)]
print(day.to_string(index=False))
print("\n모델 지정 없는 호출(pd1)과 같은 값인 칸 수(낮 24칸 가운데, 값이 있는 칸만)")
for k in [col for col in x.columns if col.startswith("pd1_")]:
    both = day["pd1"].notna() & day[k].notna()
    same = int((np.abs(day.loc[both, "pd1"] - day.loc[both, k]) < 1e-9).sum())
    print(f"  {k:22s} 값 있는 칸 {int(day[k].notna().sum()):2d}, 같은 칸 {same:2d}")
# 저장해 둔 d2r 사본과도 대조
h = c.load_prevruns_hourly()
hh = h[(h["time"] >= "2024-02-01") & (h["time"] < "2024-02-03")][["time", "shortwave_radiation_previous_day1"]]
z = hh.merge(d, on="time")
print("\n어제(2026-10-06) 받아 둔 사본과 오늘 다시 받은 값의 최대 차이:",
      float((z["shortwave_radiation_previous_day1_x"] - z["shortwave_radiation_previous_day1_y"]).abs().max()))
