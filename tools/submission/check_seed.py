"""Validate the complete approved portable seed before publishing or booting CI."""
import csv
import hashlib
import json
from pathlib import Path

SEED = Path(__file__).resolve().parents[2] / "project/serving_app/models/hourly-seed"


def main():
    catalog = json.loads((SEED / "catalog.json").read_text(encoding="utf-8"))
    plants = catalog["plants"]
    if len(plants) != 31:
        raise ValueError(f"Expected 31 approved plants, got {len(plants)}")
    expected = {"catalog.json", "portfolio_quality.json"}
    for plant in plants:
        folder = SEED / "models" / plant
        manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
        if manifest["plant_id"] != plant or manifest["gate"]["passed"] is not True:
            raise ValueError(f"Unapproved or mismatched manifest: {plant}")
        for name in ("model.keras", "scaler.pkl"):
            digest = hashlib.sha256((folder / name).read_bytes()).hexdigest()
            if digest != manifest["hashes"][name]:
                raise ValueError(f"Hash mismatch: {plant}/{name}")
        expected.update(f"models/{plant}/{name}" for name in ("model.keras", "scaler.pkl", "manifest.json"))
        history = f"history/{plant}.csv"
        expected.add(history)
        with (SEED / history).open(encoding="utf-8", newline="") as source:
            rows = csv.reader(source)
            if not next(rows, None) or not next(rows, None):
                raise ValueError(f"Empty replay history: {plant}")
    actual = {p.relative_to(SEED).as_posix() for p in SEED.rglob("*") if p.is_file()}
    if actual != expected:
        raise ValueError(f"Unexpected or missing seed files: {sorted(actual ^ expected)}")
    print(f"PASS: {len(plants)} approved plants, {len(actual)} files, all model/scaler hashes verified")


if __name__ == "__main__":
    main()
