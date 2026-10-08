"""Extract needed ASOS columns, first verifying them against the existing Hadong files."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from config import REGIONS

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "datasets/multi_plant"
STATIONS = sorted({sid for _, stations in REGIONS.values() for sid in stations})
COLS = ["stnId", "stnNm", "tm", "sumGsr", "sumSsHr", "ssDur", "maxTa"]


def hadong_weather(weather):
    index = pd.date_range("2013-01-01", "2025-12-31")
    w = {sid: weather[weather.stnId == sid].set_index("tm").reindex(index) for sid in (266, 192, 263)}
    gy, jj, ur = w[266], w[192], w[263]
    jj_gsr = jj.sumGsr.mask((index >= "2016-01-07") & (index <= "2018-04-05"))
    result = pd.DataFrame(index=index)
    result["gy_gsr_obs"] = gy.sumGsr
    result["gy_gsr"] = gy.sumGsr.fillna(jj_gsr).fillna(ur.sumGsr)
    result["gy_gsr_fill"] = np.where(gy.sumGsr.notna(), "obs", np.where(jj_gsr.notna(), "jinju192", "uiryeong263"))
    result["gy_ss_obs"] = gy.sumSsHr
    result["gy_ss"] = gy.sumSsHr.mask(gy.sumSsHr > gy.ssDur + 0.05).fillna(jj.sumSsHr.mask(jj.sumSsHr > jj.ssDur + 0.05))
    result["gy_max_ta"] = gy.maxTa
    result["gsr_station_id"] = np.where(gy.sumGsr.notna(), 266, np.where(jj_gsr.notna(), 192, 263))
    return result


def compare(a, b, atol=1e-8):
    a, b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    ok = np.isclose(a, b, atol=atol, rtol=0, equal_nan=True)
    finite = np.isfinite(a) & np.isfinite(b)
    return {"rows": len(a), "mismatches": int((~ok).sum()),
            "max_abs_diff": float(np.max(np.abs(a[finite] - b[finite]))) if finite.any() else None}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--asos-dir", type=Path, required=True)
    args = parser.parse_args()
    frames, sources = [], []
    for year in range(2013, 2026):
        path = args.asos_dir / f"ASOS_{year}.csv"
        data = pd.read_csv(path, encoding="utf-8-sig", usecols=COLS)
        frames.append(data[data.stnId.isin(STATIONS)])
        sources.append({"file": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                        "bytes": path.stat().st_size, "source_rows": len(data), "selected_rows": len(frames[-1])})
    weather = pd.concat(frames, ignore_index=True)
    weather["tm"] = pd.to_datetime(weather.tm)
    if weather.duplicated(["stnId", "tm"]).any():
        raise ValueError("ASOS duplicate station/date")
    weather = weather.sort_values(["stnId", "tm"])
    hadong = hadong_weather(weather)
    existing = pd.read_csv(REPO / "datasets/hadong_daily_full.csv", parse_dates=["date"]).set_index("date").reindex(hadong.index)
    checks = {col: compare(hadong[col], existing[col]) for col in ["gy_gsr_obs", "gy_gsr", "gy_ss_obs", "gy_ss", "gy_max_ta"]}
    checks["gy_gsr_fill"] = {"rows": len(hadong), "mismatches": int((hadong.gy_gsr_fill != existing.gy_gsr_fill).sum())}
    upload = pd.read_csv(REPO / "datasets/hadong_upload.csv", parse_dates=["Date"]).set_index("Date")
    checks["upload_Volume_lag1"] = compare(hadong.gy_gsr.shift(1).reindex(upload.index), upload.Volume)
    checks["upload_Close"] = compare(existing.gen_kwh.reindex(upload.index), upload.Close)
    report = {"checks": checks, "passed": all(c["mismatches"] == 0 for c in checks.values()),
              "provider": "기상청", "source_type": "user-supplied annual ASOS daily API exports",
              "source_url": "https://www.data.go.kr/data/15059093/openapi.do",
              "source_api_license": "공공누리 제1유형(출처표시), 무료; 공식 API 페이지 2026-10-07 확인",
              "station_ids": STATIONS, "columns": COLS,
              "policy": "Compare raw observations and original Gwangyang/Jinju/Uiryeong fill before publishing extracted weather.",
              "sources": sources}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "weather_verification.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"passed": report["passed"], "checks": checks}, ensure_ascii=False, indent=2))
    if not report["passed"]:
        raise ValueError("ASOS differs from existing Hadong data; extracted weather was NOT published")
    dest = OUT / "weather"
    dest.mkdir(exist_ok=True)
    weather.to_csv(dest / "asos_selected_daily.csv", index=False, encoding="utf-8", date_format="%Y-%m-%d")
    report["output_sha256"] = hashlib.sha256((dest / "asos_selected_daily.csv").read_bytes()).hexdigest()
    (OUT / "weather_verification.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Saved {len(weather)} rows, {weather.stnId.nunique()} ASOS stations")


if __name__ == "__main__":
    main()
