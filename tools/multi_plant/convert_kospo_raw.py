"""한국남부발전 「태양광발전실적」 원자료(CSV)를 계약의 정규화 실적으로 바꾼다.

원자료의 모양(공공데이터포털, 발전소마다 파일 하나):
    년월일, 호기, 총량, 평균, 최대, 최소, 최대(시간별), 최소(시간별), 1, 2, ..., 24
    - 열 이름 뒤에 "(kw)" 가 붙은 파일과 붙지 않은 파일이 있다. 값은 그 시간의 발전량(kWh)으로 읽는다.
    - 시간 열 h 는 (h-1)시 ~ h시의 값이다(docs/research/merged/T1-plant-data.md).

만드는 것 (--out-root/generation/<plant_id>/ 아래):
    generation_daily.csv    plant_id, date, energy_kwh, quality, source_file
    generation_hourly.csv   plant_id, date, hour, energy_kwh, quality, source_file
    manifest.json           원자료의 해시, 변환 스크립트, 행 수, 품질별 날 수

지키는 것:
    - 빈 칸을 0 으로 채우지 않는다. 시간 칸이 하나라도 비면 그날의 하루 값은 비우고 partial 로 적는다.
    - 원자료에 없는 날짜는 값이 빈 missing 행으로 채워, 달력의 모든 날짜에 행이 있게 한다.
    - 하루 합계가 0 인 날은 zero_day 로 적는다. 정지 후보이지 결측이 아니다.
    - 호기가 둘 이상이면 멈춘다. 더할지 따로 볼지는 사람이 정한다.

실행 (저장소 루트에서. 표준 라이브러리만 쓴다):
    python tools/multi_plant/convert_kospo_raw.py --raw <원자료.csv> --plant-id hadong-sewage --out-root <자료 폴더>
"""
import argparse
import csv
import io
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C  # noqa: E402

TOLERANCE = 0.01   # 하루 합계와 시간대별 합의 차이를 같다고 보는 한도(kWh)


def read_raw(path):
    data = Path(path).read_bytes()
    for enc in ("utf-8-sig", "cp949"):
        try:
            return list(csv.reader(io.StringIO(data.decode(enc)))), enc
        except UnicodeDecodeError:
            continue
    raise SystemExit(f"{path}: UTF-8 로도 CP949 로도 읽을 수 없다")


def convert(raw_path, plant_id):
    rows, encoding = read_raw(raw_path)
    header, body = [h.strip() for h in rows[0]], [r for r in rows[1:] if r and r[0].strip()]
    if not C.PLANT_ID.match(plant_id):
        raise SystemExit(f"plant_id '{plant_id}' 는 영문 소문자, 숫자, 붙임표 2~40자여야 한다")
    try:
        i_date, i_unit = header.index("년월일"), header.index("호기")
        i_total = next(i for i, h in enumerate(header) if h.startswith("총량"))
        i_hours = [header.index(str(h)) for h in range(1, 25)]
    except (ValueError, StopIteration):
        raise SystemExit(f"{raw_path}: 년월일, 호기, 총량, 1~24 열이 있어야 한다. 머리 줄: {header}")
    units = sorted({r[i_unit].strip() for r in body})
    if len(units) != 1:
        raise SystemExit(f"{raw_path}: 호기가 {units} 로 여러 개다. 더할지 따로 볼지 정한 뒤 변환한다")

    name = Path(raw_path).name
    by_date, duplicates = {}, []
    for n, r in enumerate(body, start=2):
        d = C.parse_date(r[i_date].strip())
        if d is None:
            raise SystemExit(f"{raw_path}:{n}: 날짜 '{r[i_date]}' 를 읽을 수 없다")
        if d in by_date:
            duplicates.append(d.isoformat())
            continue
        try:
            total = C.parse_number(r[i_total])
            hours = [C.parse_number(r[i]) if i < len(r) else None for i in i_hours]
        except ValueError:
            raise SystemExit(f"{raw_path}:{n}: 숫자가 아닌 값이 있다")
        if any(v is not None and v < 0 for v in hours + [total]):
            raise SystemExit(f"{raw_path}:{n}: 음수가 있다")
        by_date[d] = (total, hours)
    if duplicates:
        raise SystemExit(f"{raw_path}: 같은 날짜가 두 번 있다: {duplicates[:5]} 등 {len(duplicates)}건")

    daily, hourly, counts = [], [], {q: 0 for q in C.QUALITY}
    day, last = min(by_date), max(by_date)
    while day <= last:
        if day not in by_date:
            daily.append({"plant_id": plant_id, "date": day.isoformat(), "energy_kwh": None, "quality": "missing", "source_file": name})
            counts["missing"] += 1
            day += timedelta(days=1)
            continue
        total, hours = by_date[day]
        present = [v for v in hours if v is not None]
        if len(present) < 24:
            quality, value = ("missing", None) if not present and total is None else ("partial", None)
        else:
            hour_sum = sum(present)
            if total is None:
                value = round(hour_sum, 6)
                quality = "zero_day" if value == 0 else "ok"
            elif abs(hour_sum - total) > TOLERANCE:
                value, quality = total, "mismatch"
            else:
                value, quality = total, ("zero_day" if total == 0 else "ok")
        counts[quality] += 1
        daily.append({"plant_id": plant_id, "date": day.isoformat(), "energy_kwh": value, "quality": quality, "source_file": name})
        for h, v in enumerate(hours, start=1):
            if v is not None:
                hourly.append({"plant_id": plant_id, "date": day.isoformat(), "hour": h, "energy_kwh": v,
                               "quality": "ok" if len(present) == 24 else "partial", "source_file": name})
        day += timedelta(days=1)
    return daily, hourly, {"encoding": encoding, "header": header, "raw_rows": len(body), "unit_id": units[0],
                           "first_date": min(by_date).isoformat(), "last_date": last.isoformat(), "quality_days": counts}


def git_commit():
    root = Path(__file__).resolve().parents[2]
    r = subprocess.run(["git", "-C", str(root), "rev-parse", "--short", "HEAD"], capture_output=True, text=True)
    return r.stdout.strip() or None


def main():
    C.use_utf8_output()
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--raw", type=Path, required=True, help="원자료 CSV")
    p.add_argument("--plant-id", required=True)
    p.add_argument("--out-root", type=Path, required=True, help="자료 폴더. 그 아래 generation/<plant_id>/ 에 쓴다")
    a = p.parse_args()

    daily, hourly, info = convert(a.raw, a.plant_id)
    out = a.out_root / "generation" / a.plant_id
    C.write_csv(out / "generation_daily.csv", C.DAILY_COLUMNS, daily)
    C.write_csv(out / "generation_hourly.csv", C.HOURLY_COLUMNS, hourly)
    manifest = {
        "schema_version": C.SCHEMA_VERSION,
        "plant_id": a.plant_id,
        "created_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "raw": {"file": a.raw.name, "sha256": C.sha256_file(a.raw), "bytes": a.raw.stat().st_size, **info},
        "script": {"path": "tools/multi_plant/convert_kospo_raw.py", "git_commit": git_commit(),
                   "sha256": C.sha256_file(Path(__file__))},
        "outputs": {f.name: {"sha256": C.sha256_file(f), "rows": n}
                    for f, n in ((out / "generation_daily.csv", len(daily)), (out / "generation_hourly.csv", len(hourly)))},
        "unit": {"energy": "kWh", "hour_convention": "hour h = (h-1)시 ~ h시, 한국 시각"},
    }
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    q = info["quality_days"]
    print(f"{a.plant_id}: {info['first_date']} ~ {info['last_date']}, 하루 행 {len(daily)}개 "
          f"(ok {q['ok']}, zero_day {q['zero_day']}, partial {q['partial']}, mismatch {q['mismatch']}, missing {q['missing']}), "
          f"시간 행 {len(hourly)}개 -> {out}")


if __name__ == "__main__":
    main()
