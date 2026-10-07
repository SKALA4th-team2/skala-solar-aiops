"""T2(설비 이력·정지일·출력 수준 변화) 통합용 공통 적재.

- 기존 폴더(solar, asos)의 파일은 읽기만 한다. 저장소(/Users/psm/workspace/skala-aiops)의 모듈은 import 하지 않는다.
- 발전 실적은 원본 CSV(CP949)에서 직접 읽는다. 이웃 발전소는 사전 조사가 받아 둔 사본(verify1b/c_*.pkl)을 읽는다.
"""
import json, pickle
from pathlib import Path
import numpy as np, pandas as pd

S = Path("(작업 폴더)")
SOLAR, ASOS, HERE = S / "solar", S / "asos", S / "merged" / "T2-history-outage"
HC = [str(i) for i in range(1, 25)]
NB = {"health": "15043406", "subst": "15043405", "water": "15043408", "stadium": "15043404"}
NBK = {"health": "보건소", "subst": "변전소", "water": "정수장", "stadium": "공설운동장"}


def load_raw():
    raw = pd.read_csv(SOLAR / "data_15043409.csv", encoding="cp949")
    raw["date"] = pd.to_datetime(raw["년월일"])
    raw = raw.sort_values("date").reset_index(drop=True)
    H = raw[HC].to_numpy(float)
    df = pd.DataFrame({"y": raw["총량(kw)"].to_numpy(float)}, index=pd.DatetimeIndex(raw["date"], name="date"))
    df["sum24"] = H.sum(axis=1)
    df["peak"] = H.max(axis=1)
    return df, H


def load_neighbors(index):
    tot, hh = {}, {}
    for nm, pk in NB.items():
        o = pickle.load(open(SOLAR / "verify1b" / f"c_{pk}.pkl", "rb"))
        t, h = [], []
        for d in index.strftime("%Y-%m-%d"):
            r = o["d"][d]
            t.append(np.nan if r[0][1] is None else r[0][1])
            h.append([np.nan if v is None else v for v in r[0][2]])
        tot[nm] = np.array(t, float)
        hh[nm] = np.array(h, float)
    return pd.DataFrame(tot, index=index), hh


def load_asos():
    return pd.read_csv(ASOS / "hadong_daily_full.csv", parse_dates=["date"]).set_index("date")


def load_weather(index):
    a = pd.read_csv(SOLAR / "d2r" / "wx_archive_daily.csv", parse_dates=["date"]).set_index("date")
    w = pd.DataFrame(index=index)
    w["sw"] = a["shortwave_radiation_sum"].reindex(index)            # Open-Meteo 과거 날씨 값(2016년까지 ERA5, 2017년부터 ECMWF IFS)
    w["sunfrac"] = (a["sunshine_duration"] / a["daylight_duration"]).reindex(index)
    w["tmax"] = a["temperature_2m_max"].reindex(index)
    j = json.load(open(SOLAR / "q3" / "sat_himawari_daily.json"))
    s = pd.Series(j["daily"]["shortwave_radiation_sum"], index=pd.to_datetime(j["daily"]["time"]), dtype=float)
    w["sat"] = s.reindex(index)                                      # Himawari 위성 일사량(2015-07 이후)
    return w


def rng(a, b):
    return pd.date_range(a, b)


def dates(lst):
    out = []
    for x in lst:
        if isinstance(x, tuple):
            out += list(pd.date_range(x[0], x[1]))
        else:
            out.append(pd.Timestamp(x))
    return pd.DatetimeIndex(sorted(set(out)))


def fmt(ds):
    """날짜 목록을 연속 구간으로 묶어 문자열로."""
    ds = sorted(pd.DatetimeIndex(ds))
    if not ds:
        return "(없음)"
    out, a, p = [], ds[0], ds[0]
    for d in ds[1:]:
        if (d - p).days == 1:
            p = d
            continue
        out.append((a, p)); a = p = d
    out.append((a, p))
    return ", ".join(f"{x.date()}" if x == z else f"{x.date()}~{z.strftime('%m-%d')}({(z - x).days + 1}일)" for x, z in out)
