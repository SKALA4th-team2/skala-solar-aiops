"""Independent checks against downloaded source rows, ASOS days and the real app loader."""
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "datasets/multi_plant"
sys.path.insert(0, str(REPO / "project"))
from data.features import HAICScaler, build_sequences, load_rows, SEQ_LEN


def main():
    catalog = json.loads((OUT / "catalog.json").read_text(encoding="utf-8"))
    sources = json.loads((OUT / "sources.json").read_text(encoding="utf-8"))
    wx = pd.read_csv(OUT / "weather/asos_selected_daily.csv", parse_dates=["tm"])
    lookup = wx.set_index(["stnId", "tm"])["sumGsr"]
    verified, sequences = [], 0
    for plant in catalog["plants"]:
        sid, unit = plant["source_id"], plant["unit"]
        path = OUT / "raw" / f"{sid}.csv"
        assert hashlib.sha256(path.read_bytes()).hexdigest() == sources[sid]["sha256"]
        raw = pd.read_csv(path, encoding="cp949", dtype=str).fillna("")
        total = next(c for c in raw if c.startswith("총량"))
        if sid == "15140095":
            labels = ["(신재생) (하동) 익산 다송리 태양광", "(신재생) 익산 다송리 태양광"]
            raw = raw[raw["호기"].isin(labels)]
        else:
            raw = raw[raw["호기"] == unit]
        raw["Date"] = pd.to_datetime(raw["년월일"])
        generation = raw.drop_duplicates("Date").set_index("Date")[total].astype(float)
        daily = pd.read_csv(OUT / plant["daily_file"], parse_dates=["date"]).set_index("date")
        assert daily.index.is_unique and daily.index.is_monotonic_increasing
        assert np.allclose(daily.gen_kwh, generation.reindex(daily.index), atol=1e-7, rtol=1e-10, equal_nan=True)
        for item in plant["uploads"]:
            path = OUT / item["file"]
            assert hashlib.sha256(path.read_bytes()).hexdigest() == item["sha256"]
            frame = pd.read_csv(path, parse_dates=["Date"]).set_index("Date")
            assert len(frame) >= 365 and len(frame) == item["rows"]
            assert frame.index.is_unique and frame.index.is_monotonic_increasing
            assert frame.index.to_series().diff().dropna().eq(pd.Timedelta(days=1)).all(), item["file"]
            assert list(frame.columns) == ["Close", "Volume"]
            assert np.isfinite(frame.to_numpy()).all() and (frame.to_numpy() >= 0).all()
            assert np.allclose(frame.Close, generation.reindex(frame.index), atol=1e-7, rtol=1e-10)
            used = daily.loc[frame.index]
            assert used.generation_valid.eq(1).all()
            # Every Volume must equal an actual ASOS observation from exactly d-1.
            weather_keys = pd.MultiIndex.from_arrays([used.gsr_lag1_station_id.astype(int), frame.index - pd.Timedelta(days=1)])
            assert np.allclose(frame.Volume, lookup.reindex(weather_keys), atol=1e-9, rtol=0)
            if plant["region"] == "경남 하동":
                old = pd.read_csv(REPO / "datasets/hadong_upload.csv", parse_dates=["Date"]).set_index("Date")
                common = frame.index.intersection(old.index)
                assert np.allclose(frame.loc[common, "Volume"], old.loc[common, "Volume"], atol=1e-9, rtol=0)
            rows = load_rows(str(path))
            split = max(1, int(len(rows) * 0.8))
            scaler = HAICScaler().fit(rows[:split])
            X, y = build_sequences(rows, scaler)
            assert len(X) == len(rows) - SEQ_LEN
            assert np.asarray(X).shape == (len(rows) - SEQ_LEN, SEQ_LEN, 2)
            assert np.isfinite(np.asarray(X)).all()
            assert np.allclose(y, frame.Close.iloc[SEQ_LEN:], atol=1e-7)
            sequences += len(X)
            verified.append({"file": item["file"], "rows": len(rows), "samples": len(X)})
    expected = {i["file"] for p in catalog["plants"] for i in p["uploads"]}
    actual = {p.relative_to(OUT).as_posix() for p in (OUT / "uploads").glob("*.csv")}
    assert expected == actual, "Stale/missing upload files"
    result = {"passed": True, "units_checked": len(catalog["plants"]), "files_checked": len(verified),
              "upload_rows": sum(x["rows"] for x in verified), "sequence_samples": sequences,
              "checks": ["original-generation equality", "source hashes", "unique ascending calendar dates", "no missing calendar days inside uploads",
                         "finite nonnegative values", "exact ASOS d-1 lookup", "Hadong original Volume equality", "real load_rows/build_sequences shape and targets", "no stale uploads"],
              "model_training_performed": False, "http_predict_verified": False, "files": verified}
    (OUT / "validation.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "files"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
