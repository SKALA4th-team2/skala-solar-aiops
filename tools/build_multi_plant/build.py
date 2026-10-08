"""Build per-unit daily data and calendar-contiguous uploads; never alter original CSVs."""
import hashlib
import json
from pathlib import Path
import re

import numpy as np
import pandas as pd

from config import EXCLUDED, REGIONS, SOURCE_REGION, SPEC_NAMES
from fetch_sources import CANDIDATES
from prepare_weather import hadong_weather

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "datasets/multi_plant"
MIN_SEGMENT_DAYS = 365


def read_csv(path):
    for encoding in ("utf-8-sig", "cp949"):
        try:
            return pd.read_csv(path, encoding=encoding, dtype=str).fillna("")
        except UnicodeDecodeError:
            pass
    raise ValueError(f"Unknown encoding: {path.name}")


def weather_for(region, weather):
    index = pd.date_range(weather.tm.min(), weather.tm.max())
    stations = REGIONS[region][1]
    station_frames = {sid: weather[weather.stnId == sid].set_index("tm").reindex(index) for sid in stations}
    primary = station_frames[stations[0]]
    result = pd.DataFrame(index=index)
    result["gsr_mj_m2"] = np.nan
    result["gsr_station_id"] = np.nan
    if region == "hadong":
        h = hadong_weather(weather)
        result["gsr_mj_m2"] = h.gy_gsr
        result["gsr_station_id"] = h.gsr_station_id.where(h.gy_gsr.notna())
    else:
        for sid, frame in station_frames.items():
            valid = frame.sumGsr.where(np.isfinite(frame.sumGsr) & (frame.sumGsr >= 0))
            fill = result.gsr_mj_m2.isna() & valid.notna()
            result.loc[fill, "gsr_mj_m2"] = valid[fill]
            result.loc[fill, "gsr_station_id"] = sid
    result["gsr_is_fallback"] = np.where(result.gsr_mj_m2.isna(), np.nan, (result.gsr_station_id != stations[0]).astype(int))
    result["sunshine_hours"] = primary.sumSsHr.where((primary.sumSsHr >= 0) & (primary.sumSsHr <= primary.ssDur + 0.05))
    result["max_temp_c"] = primary.maxTa
    result["local_station_id"] = stations[0]
    result["gsr_lag1_mj_m2"] = result.gsr_mj_m2.shift(1)
    result["gsr_lag1_station_id"] = result.gsr_station_id.shift(1)
    return result


def contiguous(frame):
    if frame.empty:
        return []
    return [part for _, part in frame.groupby(frame.index.to_series().diff().dt.days.ne(1).cumsum())]


def build_unit(sid, unit, source, hourly_cols, total_col, weather, specs):
    key = f"{sid}_u{unit}"
    source = source.copy()
    source["date"] = pd.to_datetime(source["년월일"], format="%Y-%m-%d", errors="coerce")
    invalid_date_rows = int(source.date.isna().sum())
    source = source[source.date.notna()]
    source = source.sort_values("date")
    numeric = source[[total_col] + hourly_cols].apply(pd.to_numeric, errors="coerce")
    d = pd.DataFrame({"date": source.date, "gen_kwh": numeric[total_col],
                      "hourly_sum_kwh": numeric[hourly_cols].sum(axis=1, min_count=24),
                      "peak_interval_kwh": numeric[hourly_cols].max(axis=1)})
    d["numeric_valid"] = (np.isfinite(numeric).all(axis=1) & numeric.ge(0).all(axis=1)).astype(int)
    d["sum_matches"] = np.isclose(d.gen_kwh, d.hourly_sum_kwh, rtol=1e-6, atol=0.05).astype(int)
    # Compare the full source row: conflicting duplicates are never silently averaged.
    signature = source.drop(columns=["date", "호기"]).astype(str).agg("|".join, axis=1)
    unique_per_date = signature.groupby(source.date).nunique()
    conflicts = unique_per_date[unique_per_date > 1].index
    d["duplicate_conflict"] = d.date.isin(conflicts).astype(int)
    duplicate_rows = int(d.date.duplicated().sum())
    d = d.drop_duplicates("date").set_index("date")
    d.index.name = "date"
    region = SOURCE_REGION[sid]
    spec_name = SPEC_NAMES.get(sid, "")
    if sid == "15043391":
        spec_name = {"1": "삼척소내태양광#1", "2": "삼척소내태양광 #2", "3": "삼척소내 태양광# 3", "4": "삼척 소내태양광#4"}.get(unit, "")
    if sid == "15043407":
        spec_name = f"하동화력태양광 #{unit}"
    match = specs[specs["발전소명"] == spec_name]
    capacity = None
    address = ""
    if len(match) == 1:
        address = match.iloc[0]["발전소 주소지"]
        cap_match = re.match(r"([\d,.]+)\s*kW", match.iloc[0]["설치용량"], re.I)
        if cap_match:
            capacity = float(cap_match[1].replace(",", ""))
    capacity_source = "15030079" if capacity is not None else "unresolved"
    if "설비용량(kW)" in source:
        caps = pd.to_numeric(source["설비용량(kW)"], errors="coerce").dropna().unique()
        if len(caps) == 1 and caps[0] > 0:
            capacity = float(caps[0])
            capacity_source = sid
    d["capacity_kw"] = capacity if capacity is not None else np.nan
    d["capacity_suspect"] = ((d.peak_interval_kwh > capacity * 1.2) | (d.gen_kwh > capacity * 24)).astype(int) if capacity else 0
    d["zero_generation"] = d.gen_kwh.eq(0).astype(int)
    d["generation_valid"] = ((d.numeric_valid == 1) & (d.sum_matches == 1) & (d.duplicate_conflict == 0) & (d.capacity_suspect == 0)).astype(int)
    d = d.join(weather[region], how="left")
    d["source_id"] = sid
    d["unit"] = unit
    daily_path = OUT / "daily" / f"{key}.csv"
    d.to_csv(daily_path, encoding="utf-8", date_format="%Y-%m-%d", float_format="%.12g")
    ready = d[(d.generation_valid == 1) & d.gsr_lag1_mj_m2.notna() & (d.gsr_lag1_mj_m2 >= 0)]
    uploaded = []
    rejected_segments = []
    for segment in contiguous(ready):
        zero_fraction = float(segment.zero_generation.mean())
        if len(segment) < MIN_SEGMENT_DAYS or zero_fraction > 0.25:
            rejected_segments.append({"start": str(segment.index.min().date()), "end": str(segment.index.max().date()),
                                      "rows": len(segment), "reason": "shorter_than_365_days" if len(segment) < MIN_SEGMENT_DAYS else "over_25_percent_zero_generation"})
            continue
        upload = pd.DataFrame({"Date": segment.index.strftime("%Y-%m-%d"), "Close": segment.gen_kwh.values,
                               "Volume": segment.gsr_lag1_mj_m2.values})
        filename = f"{key}_asos_lag1_{segment.index[0]:%Y%m%d}_{segment.index[-1]:%Y%m%d}.csv"
        upload.to_csv(OUT / "uploads" / filename, index=False, encoding="utf-8", float_format="%.12g")
        uploaded.append({"file": f"uploads/{filename}", "rows": len(upload), "start": upload.Date.iloc[0], "end": upload.Date.iloc[-1],
                         "zero_days": int(segment.zero_generation.sum()), "sha256": hashlib.sha256((OUT / "uploads" / filename).read_bytes()).hexdigest()})
    count_missing = (d.index.max() - d.index.min()).days + 1 - len(d) if len(d) else 0
    return {"plant_id": key, "source_id": sid, "name": CANDIDATES[sid], "unit": unit, "region": REGIONS[region][0],
            "address": address, "capacity_kw": capacity, "capacity_source": capacity_source,
            "unit_basis": "explicit_kWh" if "kWh" in total_col else "inferred_kWh_legacy_label",
            "weather_mapping": {"station_priority": REGIONS[region][1], "status": "regional_proxy_not_site_measurement"},
            "daily_file": f"daily/{key}.csv", "rows": len(d), "start": str(d.index.min().date()), "end": str(d.index.max().date()),
            "invalid_date_rows": invalid_date_rows, "duplicate_rows": duplicate_rows, "duplicate_conflict_dates": len(conflicts),
            "missing_calendar_days": count_missing, "invalid_generation_days": int((d.generation_valid == 0).sum()),
            "sum_mismatch_days": int((d.sum_matches == 0).sum()), "capacity_suspect_days": int(d.capacity_suspect.sum()),
            "zero_days": int(d.zero_generation.sum()), "weather_missing_days": int(d.gsr_lag1_mj_m2.isna().sum()),
            "fallback_weather_days": int(d.gsr_is_fallback.fillna(0).sum()),
            "status": "upload_ready" if uploaded else "review_only", "uploads": uploaded,
            "primary_upload": max(uploaded, key=lambda u: (u['rows'], u['end']))['file'] if uploaded else None,
            "excluded_segments": rejected_segments}


def main():
    for folder in ("daily", "uploads"):
        (OUT / folder).mkdir(parents=True, exist_ok=True)
    report = json.loads((OUT / "weather_verification.json").read_text(encoding="utf-8"))
    weather_path = OUT / "weather/asos_selected_daily.csv"
    if not report["passed"] or hashlib.sha256(weather_path.read_bytes()).hexdigest() != report["output_sha256"]:
        raise ValueError("ASOS verification/hash check failed")
    sources = json.loads((OUT / "sources.json").read_text(encoding="utf-8"))
    specs = read_csv(OUT / "raw/15030079.csv")
    wx = pd.read_csv(weather_path, parse_dates=["tm"])
    weather = {region: weather_for(region, wx) for region in REGIONS}
    approved = set(json.loads((REPO / "tools/aiops/approved_plants.json").read_text(encoding="utf-8")))
    plants, skipped = [], []
    for sid in CANDIDATES:
        if not any(pid.startswith(sid + "_") for pid in approved):continue
        raw_path = OUT / "raw" / f"{sid}.csv"
        if "error" in sources[sid]:
            skipped.append({"source_id": sid, "name": CANDIDATES[sid], "reason": sources[sid]["error"]})
            continue
        if hashlib.sha256(raw_path.read_bytes()).hexdigest() != sources[sid]["sha256"]:
            raise ValueError(f"Source hash mismatch {sid}")
        if sid in EXCLUDED:
            skipped.append({"source_id": sid, "name": CANDIDATES[sid], "reason": EXCLUDED[sid]})
            continue
        data = read_csv(raw_path)
        total_col = next(c for c in data.columns if c.startswith("총량"))
        hours = [str(i) for i in range(1, 25)] if "1" in data.columns else [f"{i}-{i+1}시 발전량(kWh)" for i in range(24)]
        if not set(hours).issubset(data.columns):
            raise ValueError(f"Unexpected hourly schema: {sid}")
        # Both labels explicitly identify the same Iksan Dasongri plant; preserve rows in raw.
        if sid == "15140095":
            labels = {"(신재생) (하동) 익산 다송리 태양광", "(신재생) 익산 다송리 태양광"}
            if not set(data["호기"]) <= labels | {""}:
                raise ValueError("Unrecognized Iksan unit label")
            data["호기"] = data["호기"].replace({label: "1" for label in labels})
        missing_units = int(data["호기"].eq("").sum())
        if missing_units:
            skipped.append({"source_id": sid, "name": CANDIDATES[sid], "reason": "missing_unit_rows", "rows": missing_units})
        for unit, group in data[data["호기"] != ""].groupby("호기"):
            if not re.fullmatch(r"\d+", unit):
                raise ValueError(f"Unsupported unit: {sid}/{unit}")
            if f"{sid}_u{unit}" not in approved:continue
            plant = build_unit(sid, unit, group, hours, total_col, weather, specs)
            plants.append(plant)
            print(f"{plant['plant_id']} {plant['status']} rows={plant['rows']} uploads={len(plant['uploads'])} invalid={plant['invalid_generation_days']}", flush=True)
    summary = {"candidate_sources": len(CANDIDATES), "daily_sources": len({p['source_id'] for p in plants}),
               "units": len(plants), "upload_ready_units": sum(bool(p['uploads']) for p in plants),
               "upload_files": sum(len(p['uploads']) for p in plants), "upload_rows": sum(u['rows'] for p in plants for u in p['uploads']),
               "regions": sorted({p['region'] for p in plants if p['uploads']}),
               "policy": {"volume": "ASOS measured daily GSR at calendar date d-1, MJ/m2", "minimum_contiguous_days": MIN_SEGMENT_DAYS,
                          "sum_tolerance": "atol=0.05 kWh, rtol=1e-6", "zero_segment_review_threshold": 0.25,
                          "capacity_screen": "peak hourly energy > 1.2 * reported kW, or daily energy > 24 * reported kW; heuristic, not outage truth"}}
    (OUT / "catalog.json").write_text(json.dumps({"summary": summary, "plants": plants, "excluded": skipped}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    flat = [{k: p[k] for k in ("plant_id", "source_id", "name", "unit", "region", "capacity_kw", "unit_basis", "rows", "start", "end", "status", "daily_file", "invalid_generation_days", "missing_calendar_days", "zero_days", "primary_upload")} | {"upload_files": len(p['uploads'])} for p in plants]
    pd.DataFrame(flat).to_csv(OUT / "catalog.csv", index=False, encoding="utf-8")
    index_lines = ["# 발전소별 파일 목록", "", "`build.py`가 catalog.json에서 생성한다. 원본 자료의 호기별로 분리했으며 독립된 사업장 수와는 다르다.", "",
                   "권장 시작 파일은 해당 호기의 가장 긴 연속 구간이다. 품질/성능 순위가 아니며, 나머지 구간은 catalog.json의 uploads에 있다.", "",
                   "| 발전소·호기 | 지역 | 원본 기간 | 연속 구간 수 | 권장 시작 파일 |", "| --- | --- | --- | --- | --- |"]
    for plant in plants:
        primary = plant["primary_upload"]
        link = f"[{primary.split('/')[-1]}]({primary})" if primary else "보류: daily/raw만 보관"
        index_lines.append(f"| {plant['name']} #{plant['unit']} | {plant['region']} | {plant['start']} ~ {plant['end']} | {len(plant['uploads'])} | {link} |")
    (OUT / "INDEX.md").write_text("\n".join(index_lines) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
