"""여러 발전소 자료의 계약(열, 단위, 식별자)과 읽기·검증 함수.

계약의 본문은 docs/proposal/multi-plant-data-contract.md 에 있다. 이 모듈은 그 계약을 기계로 확인하는 쪽이다.
표준 라이브러리만 쓴다. 백엔드를 돌릴 PC 의 project/.venv(requirements.txt)만으로 돌게 하려는 것이다.

자료 폴더(--data-root)의 모양:
    plants.csv                                   발전소 등록부 (한 행 = 한 발전소의 한 유효 기간)
    portfolio_members.csv                        포트폴리오 구성 (한 행 = 한 구성 버전의 한 발전소)
    generation/<plant_id>/generation_daily.csv   하루 발전량
    generation/<plant_id>/generation_hourly.csv  시간대별 발전량 (있을 때만)
    generation/<plant_id>/manifest.json          원자료에서 여기까지의 계보 (있을 때만)

검증 결과는 (수준, 코드, 위치, 문장)의 목록이다. 수준은 "error" 또는 "warn" 이다.
"""
import csv
import hashlib
import math
import re
from datetime import date, timedelta
from pathlib import Path

SCHEMA_VERSION = "0.1"
SEQ_LEN = 20            # project/data/features.py 의 SEQ_LEN 과 같다
REFERENCE_MW = 20.0     # 예측제도 참여 요건에 나오는 설비 용량 기준(초과). 참고 비교에만 쓴다

TO_KW = {"kW": 1.0, "MW": 1000.0}
TO_KWH = {"Wh": 0.001, "kWh": 1.0, "MWh": 1000.0}

# 하루 발전량 행의 품질 표시.
#   ok        값이 있고 이상 표시가 없다
#   zero_day  값이 0 이다. 정지 후보이지 결측이 아니다
#   partial   시간대별 24칸 가운데 일부가 비어 하루 합계를 만들 수 없다 (값은 비운다)
#   mismatch  원자료의 하루 합계와 시간대별 합이 다르다 (값은 원자료의 하루 합계)
#   missing   값이 없다 (값은 비운다. 0 으로 채우지 않는다)
QUALITY = ("ok", "zero_day", "partial", "mismatch", "missing")
HAS_VALUE = ("ok", "zero_day", "mismatch")
USABLE_DEFAULT = ("ok", "zero_day")     # 창과 평가에 쓰는 날. mismatch 는 사람이 본 뒤에 넣는다

PLANT_ID = re.compile(r"^[a-z0-9][a-z0-9-]{1,39}$")

PLANT_COLUMNS = [
    "plant_id", "plant_name", "source_org", "source_dataset", "source_url", "license",
    "address", "latitude", "longitude", "location_basis",
    "capacity_value", "capacity_unit", "capacity_kind", "capacity_basis",
    "valid_from", "valid_to", "timezone", "interval", "hour_convention", "note",
]
PLANT_REQUIRED = ["plant_id", "plant_name", "source_org", "source_dataset", "valid_from", "timezone", "interval"]
MEMBER_COLUMNS = ["portfolio_id", "composition_version", "plant_id", "effective_from", "effective_to", "note"]
DAILY_COLUMNS = ["plant_id", "date", "energy_kwh", "quality", "source_file"]
HOURLY_COLUMNS = ["plant_id", "date", "hour", "energy_kwh", "quality", "source_file"]

FAR_FUTURE = date(9999, 12, 31)


def issue(level, code, where, message):
    return {"level": level, "code": code, "where": str(where), "message": message}


def errors_of(issues):
    return [i for i in issues if i["level"] == "error"]


def read_csv(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        return list(reader.fieldnames or []), list(reader)


def write_csv(path, columns, rows):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=columns, lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow({c: ("" if r.get(c) is None else r.get(c)) for c in columns})


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_date(text):
    """YYYY-MM-DD 만 받는다. 다른 모양이면 None."""
    try:
        d = date.fromisoformat(text)
    except (TypeError, ValueError):
        return None
    return d if d.isoformat() == text else None


def parse_number(text):
    """유한한 실수만 받는다. 빈 칸은 None, 숫자가 아니면 ValueError."""
    if text is None or str(text).strip() == "":
        return None
    value = float(text)
    if not math.isfinite(value):
        raise ValueError("유한한 수가 아니다")
    return value


def to_kw(value, unit):
    return value * TO_KW[unit]


def to_kwh(value, unit):
    return value * TO_KWH[unit]


def _missing_columns(headers, needed):
    return [c for c in needed if c not in headers]


# ───────────────────────────── 발전소 등록부 ─────────────────────────────

def load_plants(path):
    """plants.csv 를 읽어 (행 목록, 문제 목록)을 돌려준다.

    한 발전소의 용량이 바뀌면 같은 plant_id 로 유효 기간이 다른 행을 하나 더 적는다.
    용량이나 좌표를 모르면 칸을 비운다. 비운 칸은 경고로만 알리고 값을 지어내지 않는다.
    """
    issues, rows = [], []
    headers, raw = read_csv(path)
    lack = _missing_columns(headers, PLANT_COLUMNS)
    if lack:
        return [], [issue("error", "PLANT-COLUMNS", path, f"열이 없다: {', '.join(lack)}")]
    for n, r in enumerate(raw, start=2):
        where = f"{Path(path).name}:{n}"
        for c in PLANT_REQUIRED:
            if not (r[c] or "").strip():
                issues.append(issue("error", "PLANT-REQUIRED", where, f"{c} 가 비어 있다"))
        pid = (r["plant_id"] or "").strip()
        if pid and not PLANT_ID.match(pid):
            issues.append(issue("error", "PLANT-ID", where, f"plant_id '{pid}' 는 영문 소문자, 숫자, 붙임표 2~40자여야 한다"))
        vf, vt = parse_date(r["valid_from"]), (parse_date(r["valid_to"]) if (r["valid_to"] or "").strip() else FAR_FUTURE)
        if vf is None or vt is None:
            issues.append(issue("error", "PLANT-DATE", where, "valid_from, valid_to 는 YYYY-MM-DD 여야 한다(valid_to 는 비울 수 있다)"))
            continue
        if vt < vf:
            issues.append(issue("error", "PLANT-DATE", where, "valid_to 가 valid_from 보다 앞이다"))
        cap_kw = None
        try:
            cap = parse_number(r["capacity_value"])
        except ValueError:
            cap = None
            issues.append(issue("error", "PLANT-CAPACITY", where, "capacity_value 가 수가 아니다"))
        unit = (r["capacity_unit"] or "").strip()
        if cap is None:
            issues.append(issue("warn", "PLANT-CAPACITY-UNKNOWN", where, f"{pid}: 용량을 모른다. 용량 합계에서 빼고 따로 알린다"))
        elif unit not in TO_KW:
            issues.append(issue("error", "PLANT-CAPACITY-UNIT", where, f"capacity_unit '{unit}' 는 kW 또는 MW 여야 한다"))
        elif cap <= 0:
            issues.append(issue("error", "PLANT-CAPACITY", where, "용량은 0 보다 커야 한다"))
        else:
            cap_kw = to_kw(cap, unit)
            if not (r["capacity_basis"] or "").strip():
                issues.append(issue("warn", "PLANT-CAPACITY-BASIS", where, f"{pid}: 용량의 근거(capacity_basis)가 비어 있다"))
        lat = lon = None
        try:
            lat, lon = parse_number(r["latitude"]), parse_number(r["longitude"])
        except ValueError:
            issues.append(issue("error", "PLANT-LOCATION", where, "latitude, longitude 가 수가 아니다"))
        if (lat is None) != (lon is None):
            issues.append(issue("error", "PLANT-LOCATION", where, "위도와 경도는 둘 다 적거나 둘 다 비운다"))
        elif lat is None:
            issues.append(issue("warn", "PLANT-LOCATION-UNKNOWN", where, f"{pid}: 좌표를 모른다. 기상 자료를 연결할 수 없다"))
        elif not (-90 <= lat <= 90 and -180 <= lon <= 180):
            issues.append(issue("error", "PLANT-LOCATION", where, "좌표의 범위가 맞지 않다"))
        if (r["interval"] or "").strip() not in ("hourly", "daily"):
            issues.append(issue("error", "PLANT-INTERVAL", where, "interval 은 hourly 또는 daily 여야 한다"))
        rows.append({**{c: (r[c] or "").strip() for c in PLANT_COLUMNS},
                     "_from": vf, "_to": vt, "_cap_kw": cap_kw, "_lat": lat, "_lon": lon, "_where": where})

    by_id = {}
    for r in rows:
        by_id.setdefault(r["plant_id"], []).append(r)
    for pid, group in by_id.items():
        group.sort(key=lambda r: r["_from"])
        for a, b in zip(group, group[1:]):
            if b["_from"] <= a["_to"]:
                issues.append(issue("error", "PLANT-PERIOD-OVERLAP", b["_where"],
                                    f"{pid}: 유효 기간이 겹친다({a['_where']}). 한 날짜에 용량이 둘이 된다"))
    # 같은 원자료를 다른 이름으로 두 번 등록했는가
    by_source = {}
    for r in rows:
        by_source.setdefault((r["source_org"], r["source_dataset"]), set()).add(r["plant_id"])
    for (org, ds), ids in sorted(by_source.items()):
        if ds and len(ids) > 1:
            issues.append(issue("error", "PLANT-DUPLICATE-SOURCE", Path(path).name,
                                f"같은 원자료({org} {ds})가 여러 plant_id 로 등록됐다: {', '.join(sorted(ids))}. 용량이 두 번 더해진다"))
    by_place = {}
    for r in rows:
        if r["_lat"] is not None and r["_cap_kw"] is not None:
            by_place.setdefault((round(r["_lat"], 5), round(r["_lon"], 5), round(r["_cap_kw"], 3)), set()).add(r["plant_id"])
    for key, ids in sorted(by_place.items()):
        if len(ids) > 1:
            issues.append(issue("warn", "PLANT-DUPLICATE-PLACE", Path(path).name,
                                f"좌표와 용량이 같은 발전소가 있다: {', '.join(sorted(ids))}. 같은 설비인지 확인한다"))
    return rows, issues


def plant_ids(plants):
    return sorted({r["plant_id"] for r in plants})


def plant_row_at(plants, plant_id, day):
    for r in plants:
        if r["plant_id"] == plant_id and r["_from"] <= day <= r["_to"]:
            return r
    return None


def capacity_kw_at(plants, plant_id, day):
    """그 날짜에 유효한 용량(kW). 등록이 없거나 용량을 모르면 None."""
    r = plant_row_at(plants, plant_id, day)
    return None if r is None else r["_cap_kw"]


# ───────────────────────────── 포트폴리오 구성 ─────────────────────────────

def load_members(path, plants):
    issues, rows = [], []
    headers, raw = read_csv(path)
    lack = _missing_columns(headers, MEMBER_COLUMNS)
    if lack:
        return [], [issue("error", "MEMBER-COLUMNS", path, f"열이 없다: {', '.join(lack)}")]
    known = set(plant_ids(plants))
    for n, r in enumerate(raw, start=2):
        where = f"{Path(path).name}:{n}"
        pf, pid = (r["portfolio_id"] or "").strip(), (r["plant_id"] or "").strip()
        if not pf or not PLANT_ID.match(pf):
            issues.append(issue("error", "MEMBER-PORTFOLIO-ID", where, "portfolio_id 는 영문 소문자, 숫자, 붙임표 2~40자여야 한다"))
        try:
            ver = int(r["composition_version"])
            if ver < 1:
                raise ValueError
        except (TypeError, ValueError):
            issues.append(issue("error", "MEMBER-VERSION", where, "composition_version 은 1 이상의 정수여야 한다"))
            continue
        ef = parse_date(r["effective_from"])
        et = parse_date(r["effective_to"]) if (r["effective_to"] or "").strip() else FAR_FUTURE
        if ef is None or et is None or et < ef:
            issues.append(issue("error", "MEMBER-DATE", where, "effective_from, effective_to 가 날짜가 아니거나 순서가 뒤집혔다"))
            continue
        if pid not in known:
            issues.append(issue("error", "MEMBER-UNKNOWN-PLANT", where, f"등록부에 없는 plant_id '{pid}'"))
        rows.append({"portfolio_id": pf, "composition_version": ver, "plant_id": pid,
                     "_from": ef, "_to": et, "note": (r["note"] or "").strip(), "_where": where})

    versions = {}
    for r in rows:
        versions.setdefault((r["portfolio_id"], r["composition_version"]), []).append(r)
    spans = {}
    for (pf, ver), group in sorted(versions.items()):
        periods = {(r["_from"], r["_to"]) for r in group}
        if len(periods) > 1:
            issues.append(issue("error", "MEMBER-VERSION-PERIOD", group[0]["_where"],
                                f"{pf} v{ver}: 한 구성 버전의 행은 적용 기간이 모두 같아야 한다"))
        ids = [r["plant_id"] for r in group]
        for pid in sorted({p for p in ids if ids.count(p) > 1}):
            issues.append(issue("error", "MEMBER-DUPLICATE-PLANT", group[0]["_where"],
                                f"{pf} v{ver}: {pid} 가 두 번 들어 있다. 용량이 두 번 더해진다"))
        spans.setdefault(pf, []).append((min(p[0] for p in periods), max(p[1] for p in periods), ver))
    for pf, group in spans.items():
        group.sort()
        for (f1, t1, v1), (f2, t2, v2) in zip(group, group[1:]):
            if f2 <= t1:
                issues.append(issue("error", "MEMBER-VERSION-OVERLAP", f"{Path(path).name}",
                                    f"{pf}: 구성 버전 v{v1} 과 v{v2} 의 적용 기간이 겹친다. 한 날짜에 구성이 둘이 된다"))
            if v2 <= v1:
                issues.append(issue("error", "MEMBER-VERSION-ORDER", f"{Path(path).name}",
                                    f"{pf}: 뒤에 적용되는 구성의 버전 번호(v{v2})가 앞의 것(v{v1})보다 커야 한다"))
    # 한 발전소가 같은 날 두 포트폴리오에 들어 있는가
    by_plant = {}
    for r in rows:
        by_plant.setdefault(r["plant_id"], []).append(r)
    for pid, group in sorted(by_plant.items()):
        for i, a in enumerate(group):
            for b in group[i + 1:]:
                if a["portfolio_id"] != b["portfolio_id"] and a["_from"] <= b["_to"] and b["_from"] <= a["_to"]:
                    issues.append(issue("error", "MEMBER-MULTI-PORTFOLIO", b["_where"],
                                        f"{pid} 가 같은 기간에 {a['portfolio_id']} 와 {b['portfolio_id']} 에 함께 들어 있다"))
    return rows, issues


def members_at(members, portfolio_id, day):
    """그 날짜에 적용되는 (구성 버전, 발전소 목록). 없으면 (None, [])."""
    hit = [r for r in members if r["portfolio_id"] == portfolio_id and r["_from"] <= day <= r["_to"]]
    if not hit:
        return None, []
    return hit[0]["composition_version"], sorted({r["plant_id"] for r in hit})


def composition_versions(members, portfolio_id):
    out = {}
    for r in members:
        if r["portfolio_id"] == portfolio_id:
            v = out.setdefault(r["composition_version"], {"from": r["_from"], "to": r["_to"], "plants": set()})
            v["plants"].add(r["plant_id"])
    return {k: {**v, "plants": sorted(v["plants"])} for k, v in sorted(out.items())}


# ───────────────────────────── 발전 실적 ─────────────────────────────

def load_generation_daily(path, expect_plant_id=None, rejected=None):
    """generation_daily.csv 를 읽어 (행 목록, 문제 목록)을 돌려준다.

    달력의 모든 날짜에 행이 있어야 한다. 값이 없는 날은 행을 두고 energy_kwh 를 비우며 quality 를 missing 으로 적는다.
    rejected 에 집합을 주면, 행은 있지만 값이 틀려 버린 날짜를 거기에 담는다(같은 날의 문제를 두 번 알리지 않으려는 것이다).
    """
    issues, rows = [], []
    headers, raw = read_csv(path)
    lack = _missing_columns(headers, DAILY_COLUMNS)
    if lack:
        return [], [issue("error", "DAILY-COLUMNS", path, f"열이 없다: {', '.join(lack)}")]
    seen, prev = set(), None
    rejected = set() if rejected is None else rejected
    for n, r in enumerate(raw, start=2):
        where = f"{path}:{n}"
        pid = (r["plant_id"] or "").strip()
        d = parse_date(r["date"])
        if d is None:
            issues.append(issue("error", "DAILY-DATE", where, "date 는 YYYY-MM-DD 여야 한다"))
            continue
        # 날짜의 순서, 중복, 빠짐은 값이 맞는지와 따로 본다. 값이 틀린 행도 "그 날짜의 행은 있다"로 센다.
        if d in seen:
            issues.append(issue("error", "DAILY-DUPLICATE-DATE", where, f"{expect_plant_id or pid} {d} 가 두 번 있다"))
            continue
        seen.add(d)
        if prev is not None:
            gap = (d - prev).days
            if gap < 0:
                issues.append(issue("error", "DAILY-ORDER", where, f"날짜가 오름차순이 아니다({prev} 다음에 {d})"))
            elif gap > 1:
                issues.append(issue("error", "DAILY-MISSING-DATE", where,
                                    f"{prev + timedelta(days=1)} ~ {d - timedelta(days=1)} 의 행 {gap - 1}개가 없다. 값이 없어도 행은 둔다"))
        prev = d
        rejected.add(d)
        if expect_plant_id is not None and pid != expect_plant_id:
            issues.append(issue("error", "DAILY-WRONG-PLANT", where, f"'{expect_plant_id}' 의 파일에 '{pid}' 의 행이 있다"))
            continue
        q = (r["quality"] or "").strip()
        if q not in QUALITY:
            issues.append(issue("error", "DAILY-QUALITY", where, f"quality '{q}' 는 {', '.join(QUALITY)} 가운데 하나여야 한다"))
            continue
        try:
            v = parse_number(r["energy_kwh"])
        except ValueError:
            issues.append(issue("error", "DAILY-VALUE", where, "energy_kwh 가 유한한 수가 아니다"))
            continue
        if v is not None and v < 0:
            issues.append(issue("error", "DAILY-NEGATIVE", where, "energy_kwh 가 음수다"))
            continue
        if v is None and q in HAS_VALUE:
            issues.append(issue("error", "DAILY-BLANK-AS-VALUE", where, f"값이 비었는데 quality 가 {q} 다. 결측은 missing 으로 적고 0 으로 채우지 않는다"))
            continue
        if v is not None and q in ("missing", "partial"):
            issues.append(issue("error", "DAILY-VALUE-ON-MISSING", where, f"quality 가 {q} 인데 값이 있다"))
            continue
        if q == "zero_day" and v != 0:
            issues.append(issue("error", "DAILY-ZERO-FLAG", where, "zero_day 인데 값이 0 이 아니다"))
        if q == "ok" and v == 0:
            issues.append(issue("warn", "DAILY-ZERO-AS-OK", where, "값이 0 인데 quality 가 ok 다. 정지 후보이면 zero_day 로 적는다"))
        rejected.discard(d)
        rows.append({"plant_id": pid, "date": d, "energy_kwh": v, "quality": q, "source_file": (r["source_file"] or "").strip()})
    return rows, issues


def load_generation_hourly(path, expect_plant_id=None):
    """generation_hourly.csv 를 읽어 ({날짜: [24칸]}, 문제 목록)을 돌려준다. hour 는 1~24 이고 h 는 (h-1)시~h시다."""
    issues, days, seen = [], {}, set()
    headers, raw = read_csv(path)
    lack = _missing_columns(headers, HOURLY_COLUMNS)
    if lack:
        return {}, [issue("error", "HOURLY-COLUMNS", path, f"열이 없다: {', '.join(lack)}")]
    for n, r in enumerate(raw, start=2):
        where = f"{path}:{n}"
        pid = (r["plant_id"] or "").strip()
        if expect_plant_id is not None and pid != expect_plant_id:
            issues.append(issue("error", "HOURLY-WRONG-PLANT", where, f"'{expect_plant_id}' 의 파일에 '{pid}' 의 행이 있다"))
            continue
        d = parse_date(r["date"])
        try:
            h = int(r["hour"])
            v = parse_number(r["energy_kwh"])
        except (TypeError, ValueError):
            issues.append(issue("error", "HOURLY-VALUE", where, "hour 나 energy_kwh 가 수가 아니다"))
            continue
        if d is None or not 1 <= h <= 24:
            issues.append(issue("error", "HOURLY-TIME", where, "date 는 YYYY-MM-DD, hour 는 1~24 여야 한다"))
            continue
        if v is not None and v < 0:
            issues.append(issue("error", "HOURLY-NEGATIVE", where, "energy_kwh 가 음수다"))
            continue
        if (d, h) in seen:
            issues.append(issue("error", "HOURLY-DUPLICATE", where, f"{pid} {d} {h}시가 두 번 있다"))
            continue
        seen.add((d, h))
        days.setdefault(d, [None] * 24)[h - 1] = v
    return days, issues


def daily_series(rows, usable=USABLE_DEFAULT):
    """{날짜: 값 또는 None}. 쓸 수 없는 날은 None 이다."""
    return {r["date"]: (r["energy_kwh"] if r["quality"] in usable else None) for r in rows}


def check_units(plant_id, plants, rows):
    """용량과 발전량의 단위가 서로 맞는지 본다. 하루 발전량 ÷ (용량 × 24시간)이 1 을 넘거나 지나치게 작으면 알린다."""
    issues, best, best_day = [], 0.0, None
    for r in rows:
        if r["energy_kwh"] is None:
            continue
        cap = capacity_kw_at(plants, plant_id, r["date"])
        if cap is None:
            continue
        cf = r["energy_kwh"] / (cap * 24)
        if cf > best:
            best, best_day = cf, r["date"]
        if cf > 1.0:
            issues.append(issue("error", "UNIT-OVER-CAPACITY", f"{plant_id} {r['date']}",
                                f"하루 발전량 {r['energy_kwh']:g}kWh 가 용량 {cap:g}kW 로 24시간 낼 수 있는 양을 넘는다. 용량이나 발전량의 단위를 확인한다"))
            break
    if best_day is not None and best < 0.03:
        issues.append(issue("error", "UNIT-FAR-BELOW-CAPACITY", plant_id,
                            f"가장 많이 발전한 날({best_day})도 용량의 {best * 100:.2f}% 다. kW 를 MW 로, 또는 kWh 를 MWh 로 잘못 적었을 수 있다"))
    return issues, best


def discover_generation(root):
    base = Path(root) / "generation"
    return sorted(p.name for p in base.iterdir() if p.is_dir()) if base.is_dir() else []


def load_root(root):
    """자료 폴더 전체를 읽어 검증한다. 돌려주는 값: dict(plants, members, daily, hourly, issues)."""
    root = Path(root)
    issues = []
    plants, members = [], []
    if (root / "plants.csv").exists():
        plants, got = load_plants(root / "plants.csv")
        issues += got
    else:
        issues.append(issue("error", "ROOT-NO-PLANTS", root, "plants.csv 가 없다"))
    if (root / "portfolio_members.csv").exists():
        members, got = load_members(root / "portfolio_members.csv", plants)
        issues += got
    daily, hourly = {}, {}
    known = set(plant_ids(plants))
    for pid in discover_generation(root):
        folder = root / "generation" / pid
        if pid not in known:
            issues.append(issue("error", "GEN-UNREGISTERED", folder, f"등록부에 없는 발전소의 자료 폴더 '{pid}'"))
        rejected = set()
        f = folder / "generation_daily.csv"
        if f.exists():
            rows, got = load_generation_daily(f, expect_plant_id=pid, rejected=rejected)
            issues += [{**i, "where": i["where"].replace(str(root) + "/", "")} for i in got]
            daily[pid] = rows
            unit_issues, _ = check_units(pid, plants, rows)
            issues += unit_issues
            for r in rows:
                if plant_row_at(plants, pid, r["date"]) is None and pid in known:
                    issues.append(issue("warn", "GEN-OUTSIDE-VALIDITY", f"{pid} {r['date']}",
                                        f"{pid}: 등록부의 유효 기간 밖의 실적이 있다(첫 날짜만 알린다)"))
                    break
        else:
            issues.append(issue("error", "GEN-NO-DAILY", folder, "generation_daily.csv 가 없다"))
        f = folder / "generation_hourly.csv"
        if f.exists():
            days, got = load_generation_hourly(f, expect_plant_id=pid)
            issues += [{**i, "where": i["where"].replace(str(root) + "/", "")} for i in got]
            hourly[pid] = days
            issues += check_hourly_against_daily(pid, days, daily.get(pid, []), skip=rejected)
        if not (folder / "manifest.json").exists():
            issues.append(issue("warn", "GEN-NO-MANIFEST", f"generation/{pid}", "manifest.json 이 없다. 원자료와 변환 스크립트를 되짚을 수 없다"))
    for pid in sorted(known - set(daily)):
        issues.append(issue("warn", "GEN-NO-DATA", pid, f"{pid}: 등록부에는 있는데 실적 자료가 없다"))
    return {"plants": plants, "members": members, "daily": daily, "hourly": hourly, "issues": issues}


def check_hourly_against_daily(plant_id, hourly_days, daily_rows, tolerance=0.01, skip=()):
    """시간대별 24칸이 모두 있는 날은 그 합이 하루 발전량과 같아야 한다. 일부만 있는 날은 하루 값이 비어 있어야 한다.

    skip 은 하루 행이 이미 오류로 버려진 날짜다. 같은 날을 다시 알리지 않는다.
    """
    issues = []
    daily = {r["date"]: r for r in daily_rows}
    for d, slots in sorted(hourly_days.items()):
        present = [v for v in slots if v is not None]
        row = daily.get(d)
        if row is None and d in skip:
            continue
        if row is None:
            issues.append(issue("error", "HOURLY-NO-DAILY", f"{plant_id} {d}", "시간대별 값은 있는데 하루 행이 없다"))
            continue
        if len(present) < 24:
            if row["quality"] not in ("partial", "missing"):
                issues.append(issue("error", "HOURLY-PARTIAL-AS-FULL", f"{plant_id} {d}",
                                    f"시간대별 값이 {len(present)}칸뿐인데 하루 행의 quality 가 {row['quality']} 다. 일부만 더해 하루 값으로 쓰지 않는다"))
            continue
        if row["energy_kwh"] is not None and row["quality"] != "mismatch" and abs(sum(present) - row["energy_kwh"]) > tolerance:
            issues.append(issue("error", "HOURLY-SUM-MISMATCH", f"{plant_id} {d}",
                                f"시간대별 합 {sum(present):.3f} 과 하루 값 {row['energy_kwh']:.3f} 이 다르다"))
    return issues


# ───────────────────────────── 창(시퀀스) ─────────────────────────────

def build_windows(plant_id, rows, seq_len=SEQ_LEN, usable=USABLE_DEFAULT):
    """한 발전소의 행에서 "이어진 seq_len 일 + 다음 날" 창을 만든다.

    창 안의 날짜가 하루씩 이어져 있고 모든 날의 값을 쓸 수 있을 때만 만든다. 다른 발전소의 행은 받지 않는다.
    돌려주는 값: [{"plant_id", "input_dates": [...], "target_date", "inputs": [...], "target"}]
    """
    assert all(r["plant_id"] == plant_id for r in rows), "다른 발전소의 행이 섞여 있다"
    series = daily_series(rows, usable)
    out = []
    for target in sorted(series):
        days = [target - timedelta(days=k) for k in range(seq_len, 0, -1)]
        values = [series.get(d) for d in days]
        if series[target] is None or any(v is None for v in values):
            continue
        out.append({"plant_id": plant_id, "input_dates": days, "target_date": target, "inputs": values, "target": series[target]})
    return out


def window_problems(windows, seq_len=SEQ_LEN):
    """창이 지켜야 할 것을 어긴 곳을 찾는다: 한 발전소의 행만, 날짜가 하루씩 이어짐, 대상일이 마지막 입력의 다음 날."""
    bad = []
    for i, w in enumerate(windows):
        ids = set(w.get("row_plant_ids", [w["plant_id"]]))
        if len(ids) > 1:
            bad.append((i, "mixed-plants", f"한 창에 발전소가 섞였다: {', '.join(sorted(ids))}"))
            continue
        dates = list(w["input_dates"]) + [w["target_date"]]
        if len(w["input_dates"]) != seq_len:
            bad.append((i, "length", f"입력이 {len(w['input_dates'])}일이다"))
        elif any((b - a).days != 1 for a, b in zip(dates, dates[1:])):
            bad.append((i, "date-gap", f"{w['plant_id']}: 창 안의 날짜가 하루씩 이어지지 않는다({dates[0]} ~ {dates[-1]})"))
    return bad


def naive_concat_windows(daily_by_plant, seq_len=SEQ_LEN):
    """발전소별 행을 그냥 이어 붙여 지금의 실습 코드처럼 창을 만들면 어떻게 되는지 본다(해서는 안 되는 방식).

    project/data/features.py 의 build_sequences 는 행의 날짜와 발전소를 보지 않고 rows[i : i + seq_len] 을 자른다.
    여기서는 같은 규칙으로 창의 범위만 만들어, 발전소나 날짜의 경계를 넘는 창을 센다.
    """
    flat = [r for pid in sorted(daily_by_plant) for r in daily_by_plant[pid]]
    windows = []
    for i in range(len(flat) - seq_len):
        chunk = flat[i:i + seq_len + 1]
        windows.append({"plant_id": chunk[-1]["plant_id"], "row_plant_ids": [r["plant_id"] for r in chunk],
                        "input_dates": [r["date"] for r in chunk[:-1]], "target_date": chunk[-1]["date"]})
    return windows


# ───────────────────────────── 업로드 파일의 선택 (제안하는 방식의 참고 구현) ─────────────────────────────

def latest_upload_for(upload_dir, plant_id):
    """발전소의 폴더(<upload_dir>/<plant_id>/) 안에서만 가장 최근 CSV 를 고른다.

    지금의 project/data/storage.py 의 latest_upload() 는 폴더 전체에서 가장 최근 파일 하나를 고른다.
    발전소가 여럿이면 마지막에 올린 발전소의 파일이 다른 발전소의 학습에 쓰인다. 이 함수는 그 문제를 막는 최소한의 모양이다.
    """
    if not PLANT_ID.match(plant_id or ""):
        raise ValueError(f"plant_id '{plant_id}' 의 모양이 맞지 않다")
    folder = Path(upload_dir) / plant_id
    files = sorted(folder.glob("*.csv"), key=lambda p: p.stat().st_mtime)
    if not files:
        raise FileNotFoundError(f"{plant_id} 의 업로드 파일이 없다: {folder}")
    return str(files[-1])
