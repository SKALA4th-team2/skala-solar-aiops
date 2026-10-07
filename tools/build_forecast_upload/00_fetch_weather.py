"""Open-Meteo 에서 하동 좌표의 날씨를 받는다(키·로그인 불필요). 결과는 이 폴더에만 저장한다.

1) archive-api            : 재분석(ERA5 계열) 일별 값, 2013-01-01 ~ 2026-02-28      -> wx_archive_daily.csv
2) previous-runs-api      : 예보 모델의 "24시간 전·48시간 전에 낸 값" 시간별, 2022-06-01 ~ 2026-02-28
                            -> wx_prevruns_hourly.csv, 하루 합계 wx_prevruns_daily.csv
3) historical-forecast-api: 각 실행분의 첫 몇 시간을 이어 붙인 값(예보가 아니라 분석값에 가깝다) 일별
                            -> wx_histfc_daily.csv
4) 같은 과제의 앞선 시도(../d2)가 받아 둔 사본이 있으면 값이 같은지 대조한다.
"""
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

OUT = Path(__file__).resolve().parent
OLD = OUT.parent / "d2"
LAT, LON = 35.06, 127.76   # 하동읍 신기교차로 부근(OSM 35.0599, 127.7623). 처리장의 정확한 좌표는 확인하지 못해 읍 단위 근사값을 쓴다.
TZ = "Asia/Seoul"


def get(base, params, tries=3):
    url = base + "?" + urllib.parse.urlencode(params)
    last = None
    for i in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=120) as r:
                raw = r.read()
                return json.loads(raw.decode("utf-8")), url, len(raw)
        except Exception as e:  # noqa: BLE001
            last = e
            print("  재시도", i, repr(e), file=sys.stderr)
            time.sleep(3)
    raise RuntimeError(f"호출 실패: {url} ({last!r})")


# ---------- 1) 재분석 ----------
daily_vars = ["shortwave_radiation_sum", "sunshine_duration", "daylight_duration", "cloud_cover_mean",
              "temperature_2m_max", "precipitation_sum"]
j, url, nb = get("https://archive-api.open-meteo.com/v1/archive", dict(
    latitude=LAT, longitude=LON, start_date="2013-01-01", end_date="2026-02-28",
    daily=",".join(daily_vars), timezone=TZ))
print("[archive] URL:", url)
print(f"[archive] 응답 {nb/1024:.0f} KB, 격자 ({j['latitude']}, {j['longitude']}), 고도 {j['elevation']} m, 단위 {j['daily_units']}")
a = pd.DataFrame(j["daily"]).rename(columns={"time": "date"})
a.to_csv(OUT / "wx_archive_daily.csv", index=False)
print("[archive] 행", len(a), a["date"].iloc[0], "~", a["date"].iloc[-1], "빈 값", int(a.isna().sum().sum()))
time.sleep(1)

# ---------- 2) 이전 실행분(예보) ----------
hv = []
for base in ["shortwave_radiation", "sunshine_duration", "cloud_cover"]:
    hv += [base, base + "_previous_day1", base + "_previous_day2"]
parts = []
for s, e in [("2022-06-01", "2022-12-31"), ("2023-01-01", "2023-12-31"),
             ("2024-01-01", "2024-12-31"), ("2025-01-01", "2026-02-28")]:
    j, url, nb = get("https://previous-runs-api.open-meteo.com/v1/forecast", dict(
        latitude=LAT, longitude=LON, start_date=s, end_date=e, hourly=",".join(hv), timezone=TZ))
    print(f"[prevruns] {s}~{e} 응답 {nb/1024:.0f} KB, 격자 ({j['latitude']}, {j['longitude']}), 단위 {j['hourly_units']['shortwave_radiation']}")
    if s.startswith("2022"):
        print("[prevruns] URL 예:", url)
    parts.append(pd.DataFrame(j["hourly"]))
    time.sleep(1)
h = pd.concat(parts, ignore_index=True)
h["time"] = pd.to_datetime(h["time"])
h.to_csv(OUT / "wx_prevruns_hourly.csv", index=False)
h["date"] = h["time"].dt.strftime("%Y-%m-%d")


def day_agg(col):
    g = h.groupby("date")[col]
    full = g.count() == 24                       # 하루 24칸이 모두 있을 때만 인정
    if col.startswith("shortwave_radiation"):
        v = g.sum() * 3600 / 1e6                 # W/m2(시간 평균) -> MJ/m2(하루 합계)
    elif col.startswith("sunshine_duration"):
        v = g.sum() / 3600.0                     # 초 -> 시간
    else:
        v = g.mean()
    return v.where(full)


d = pd.DataFrame({c: day_agg(c) for c in hv}).reset_index()
d.to_csv(OUT / "wx_prevruns_daily.csv", index=False)
print("[prevruns] 일별 행", len(d))
for c in hv:
    ok = d.loc[d[c].notna(), "date"]
    print(f"   {c:40s} 값 있는 날 {len(ok):5d}  {ok.min()} ~ {ok.max()}")
gap = d[(d["date"] >= "2022-07-03") & d["shortwave_radiation_previous_day1"].isna()]["date"].tolist()
print("[prevruns] 2022-07-03 이후 하루 전 예보가 빈 날:", gap)

# ---------- 3) 이어 붙인 예보(분석값에 가까움) ----------
j, url, nb = get("https://historical-forecast-api.open-meteo.com/v1/forecast", dict(
    latitude=LAT, longitude=LON, start_date="2022-01-01", end_date="2026-02-28",
    daily="shortwave_radiation_sum,sunshine_duration,cloud_cover_mean", timezone=TZ))
f = pd.DataFrame(j["daily"]).rename(columns={"time": "date"})
f.to_csv(OUT / "wx_histfc_daily.csv", index=False)
print(f"[histfc] 응답 {nb/1024:.0f} KB, 행 {len(f)}, 빈 값 {int(f.isna().sum().sum())}, 격자 ({j['latitude']}, {j['longitude']})")
print("[histfc] URL:", url)

# ---------- 4) 앞선 시도의 사본과 대조 ----------
for name in ["wx_archive_daily.csv", "wx_prevruns_daily.csv", "wx_histfc_daily.csv"]:
    p = OLD / name
    if not p.exists():
        print("[대조] 이전 사본 없음:", name)
        continue
    o = pd.read_csv(p)
    n = pd.read_csv(OUT / name)
    common = [c for c in n.columns if c in o.columns and c != "date"]
    m = o.merge(n, on="date", suffixes=("_old", "_new"))
    worst = 0.0
    for c in common:
        diff = (m[c + "_old"] - m[c + "_new"]).abs().max()
        worst = max(worst, 0.0 if np.isnan(diff) else float(diff))
        nan_mismatch = int((m[c + "_old"].isna() != m[c + "_new"].isna()).sum())
        if nan_mismatch:
            print(f"   {name} {c}: 빈 값 위치가 다른 날 {nan_mismatch}")
    print(f"[대조] {name}: 같은 날짜 {len(m)}행, 공통 열 {len(common)}개, 최대 절대차 {worst:.6g}")
