"""T3(날씨 자료와 두 번째 입력) 공통 읽기 함수.

기존 폴더(solar, asos, merged/gap1)의 파일은 읽기만 한다. 새 파일은 이 폴더에만 만든다.
실행: PYTHONDONTWRITEBYTECODE=1 /Users/psm/workspace/skala-aiops/mlflow/.venv/bin/python <스크립트>
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
SCR = HERE.parent.parent                      # .../scratchpad
SOLAR = SCR / "solar"
ASOS = SCR / "asos"
GAP1 = SCR / "merged" / "gap1"


def load_generation_raw():
    """발전 실적 원본(CP949)에서 날짜와 하루 합계를 읽는다. 열 이름에 기대지 않고 위치로 읽는다."""
    raw = pd.read_csv(SOLAR / "data_15043409.csv", encoding="cp949")
    cols = list(raw.columns)
    date_col = [c for c in cols if "일" in c and ("년" in c or "날" in c or "자" in c)]
    return raw, cols


def load_full():
    """ASOS 결합 자료(광양 266 관측 + 발전 실적)."""
    f = pd.read_csv(ASOS / "hadong_daily_full.csv", parse_dates=["date"])
    return f


def load_archive():
    """Open-Meteo 보관 자료. 기본값(2016년까지 ERA5, 2017년부터 ECMWF IFS)과 전 기간 ERA5."""
    a = pd.read_csv(SOLAR / "d2r" / "wx_archive_daily.csv", parse_dates=["date"])
    a = a.rename(columns={"shortwave_radiation_sum": "om_gsr", "sunshine_duration": "om_ss_sec",
                          "cloud_cover_mean": "om_cloud", "temperature_2m_max": "om_tmax",
                          "daylight_duration": "om_daylen_sec", "precipitation_sum": "om_rain"})
    a["om_ss"] = a["om_ss_sec"] / 3600.0
    e = pd.read_csv(SOLAR / "d2r" / "wx_archive_daily_era5.csv", parse_dates=["date"])
    e = e.rename(columns={"shortwave_radiation_sum": "era5_gsr", "sunshine_duration": "era5_ss_sec"})
    e["era5_ss"] = e["era5_ss_sec"] / 3600.0
    return a.merge(e[["date", "era5_gsr", "era5_ss"]], on="date", how="left")


def load_himawari():
    j = json.load(open(SOLAR / "q3" / "sat_himawari_daily.json"))
    d = pd.DataFrame(j["daily"]).rename(columns={"time": "date", "shortwave_radiation_sum": "sat_gsr"})
    d["date"] = pd.to_datetime(d["date"])
    return d, (j["latitude"], j["longitude"])


def load_power():
    j = json.load(open(SOLAR / "q3" / "power_full.json"))
    p = j["properties"]["parameter"]
    d = pd.DataFrame({"power_gsr_kwh": pd.Series(p["ALLSKY_SFC_SW_DWN"]),
                      "power_kt": pd.Series(p["ALLSKY_KT"]),
                      "power_cloud": pd.Series(p["CLOUD_AMT"])})
    d.index = pd.to_datetime(d.index, format="%Y%m%d")
    d = d.replace(-999, np.nan).replace(-999.0, np.nan)
    d["power_gsr"] = d["power_gsr_kwh"] * 3.6          # kWh/m2 -> MJ/m2
    return d.rename_axis("date").reset_index()


def load_prevruns_daily():
    """D2 가 받은 Previous Runs API 일 합계(기본 모델). MJ/m2."""
    p = pd.read_csv(SOLAR / "d2r" / "wx_prevruns_daily.csv", parse_dates=["date"])
    p = p.rename(columns={"shortwave_radiation": "fc0_gsr",
                          "shortwave_radiation_previous_day1": "fc1_gsr",
                          "shortwave_radiation_previous_day2": "fc2_gsr",
                          "cloud_cover": "fc0_cloud_all",
                          "cloud_cover_previous_day1": "fc1_cloud_all",
                          "cloud_cover_previous_day2": "fc2_cloud_all"})
    return p[["date", "fc0_gsr", "fc1_gsr", "fc2_gsr", "fc0_cloud_all", "fc1_cloud_all", "fc2_cloud_all"]]


def load_prevruns_hourly():
    h = pd.read_csv(SOLAR / "d2r" / "wx_prevruns_hourly.csv", parse_dates=["time"])
    return h


def load_gsm_cloud_daily(h0=7, h1=18):
    """JMA GSM 구름양 하루 전 예보(Previous Runs). 낮 h0~h1시(KST) 평균. 칸이 모두 있는 날만."""
    j = json.load(open(SOLAR / "q3" / "pr_jma_gsm_cloud.json"))
    h = pd.DataFrame(j["hourly"])
    h["time"] = pd.to_datetime(h["time"])
    h["date"] = h["time"].dt.normalize()
    h["hour"] = h["time"].dt.hour
    d = h[(h["hour"] >= h0) & (h["hour"] <= h1)]
    g = d.groupby("date")["cloud_cover_previous_day1"]
    out = g.mean().where(g.count() == (h1 - h0 + 1))
    return out.rename("gsm_cloud_fc1").reset_index()


def load_asos_cloud():
    """ASOS 원자료 사본에서 광양(266), 여수(168)의 일 평균 전운량(1/10)."""
    use = ["stnId", "tm", "avgTca", "sumGsr", "sumSsHr"]
    a = pd.read_csv(ASOS / "a1" / "a1_asos_all.csv", usecols=use, parse_dates=["tm"])
    a = a[(a["tm"] >= "2013-01-01")]
    out = None
    for sid, name in [(266, "gy"), (168, "ys")]:
        s = a[a["stnId"] == sid][["tm", "avgTca"]].rename(columns={"tm": "date", "avgTca": f"{name}_tca"})
        out = s if out is None else out.merge(s, on="date", how="outer")
    return out


def stats_pair(x, y):
    """x 를 기준(관측)으로 본 y 의 일치도."""
    m = x.notna() & y.notna()
    x, y = x[m].astype(float), y[m].astype(float)
    n = len(x)
    if n < 3:
        return dict(n=n)
    d = y - x
    slope = np.polyfit(x, y, 1)[0]
    return dict(n=n, mean_x=x.mean(), mean_y=y.mean(), ratio_sum=y.sum() / x.sum(), bias=d.mean(),
                mae=d.abs().mean(), rmse=float(np.sqrt((d ** 2).mean())),
                rrmse_pct=float(np.sqrt((d ** 2).mean()) / x.mean() * 100),
                r=float(np.corrcoef(x, y)[0, 1]), slope=float(slope))


def fmt(s):
    if s.get("n", 0) < 3:
        return f"n={s.get('n', 0)}"
    return (f"n={s['n']:5d} 평균(기준)={s['mean_x']:6.2f} 평균(비교)={s['mean_y']:6.2f} 합의 비={s['ratio_sum']:.3f} "
            f"치우침={s['bias']:+.2f} MAE={s['mae']:.2f} RMSE={s['rmse']:.2f} ({s['rrmse_pct']:.1f}%) "
            f"상관={s['r']:.3f} 기울기={s['slope']:.3f}")
