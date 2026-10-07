"""여러 발전소 도구가 잘못된 자료를 실제로 잡아내는지, 작은 합성 자료로 확인한다.

합성 자료는 임시 폴더에 그때그때 만든다. 값은 정해진 식으로 만들어 돌릴 때마다 같다.
**합성 자료의 수치는 도구의 기능을 확인하는 데만 쓴다. 실제 예측 성능이나 제도 요건의 근거가 아니다.**

확인하는 것 (번호는 결과 표의 번호다):
    S01 남부발전 형식 원자료의 변환(빈 칸, 빠진 날, 0 인 날, 합계 불일치)   S02 정상 자료는 통과
    S03 같은 발전소의 중복 등록과 용량 중복 합산   S04 kW·MW 를 바꿔 적은 용량   S05 단위 환산
    S06 빠진 날짜   S07 중복 날짜   S08 결측을 값으로 적은 행과 결측이 낀 창
    S09 음수와 비유한 값   S10 다른 발전소의 행이 섞인 파일   S11 발전소가 섞인 창
    S12 포트폴리오 구성 변경   S13 구성 버전의 기간 겹침과 이중 소속   S14 용량 변경
    S15 용량을 모르는 발전소   S16 일부 발전소의 자료 누락   S17 일부 발전소의 예측(모델) 누락
    S18 발전소 A 의 업로드가 B 의 학습에 쓰이는 문제   S19 모델과 스케일러의 짝 불일치
    S20 포트폴리오 RMSE 와 발전소별 RMSE 의 합, 오차 상쇄   S21 시간대별 자료의 일부만 더한 하루 값

실행 (저장소 루트에서. 표준 라이브러리만 쓴다):
    python tools/multi_plant/selftest.py [--out <결과를 둘 폴더>]
하나라도 기대와 다르면 종료 코드 1 이다.
"""
import argparse
import json
import math
import os
import platform
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "project"))   # 지금의 서빙 코드(data.storage, data.features)를 그대로 불러 본다

import bundle_check  # noqa: E402
import common as C  # noqa: E402
import convert_kospo_raw  # noqa: E402
import coverage  # noqa: E402
import evaluate  # noqa: E402
import portfolio_capacity  # noqa: E402

START = date(2025, 1, 1)
N_DAYS = 400
PROFILE = [0, 0, 0, 0, 0, 0, 0, 1, 3, 6, 9, 11, 12, 11, 9, 6, 3, 1, 0, 0, 0, 0, 0, 0]   # 시간대별 비중(합 72)
results = []


def lcg(seed):
    x = seed
    while True:
        x = (1103515245 * x + 12345) % (2 ** 31)
        yield x / 2 ** 31


def make_hourly(capacity_kw, seed, n=N_DAYS, start=START):
    """{날짜: [24칸]}. 계절과 구름을 흉내 낸 정해진 값."""
    g, out = lcg(seed), {}
    for i in range(n):
        hours = (3.2 + 1.2 * math.sin(2 * math.pi * (i - 80) / 365)) * (0.35 + 0.65 * next(g))   # 용량 1kW 당 하루 발전 시간
        out[start + timedelta(days=i)] = [round(capacity_kw * hours * w / 72, 6) for w in PROFILE]
    return out


def daily_rows(pid, hourly):
    rows = []
    for d in sorted(hourly):
        v = round(sum(hourly[d]), 6)
        rows.append({"plant_id": pid, "date": d.isoformat(), "energy_kwh": v, "quality": "zero_day" if v == 0 else "ok", "source_file": "synthetic"})
    return rows


def hourly_rows(pid, hourly):
    return [{"plant_id": pid, "date": d.isoformat(), "hour": h + 1, "energy_kwh": v, "quality": "ok", "source_file": "synthetic"}
            for d in sorted(hourly) for h, v in enumerate(hourly[d])]


def plant(pid, cap, unit="kW", dataset=None, valid_from="2025-01-01", valid_to="", lat="35.0", lon="127.7"):
    return {"plant_id": pid, "plant_name": f"합성 {pid}", "source_org": "synthetic", "source_dataset": dataset or pid, "source_url": "",
            "license": "합성 자료", "address": "", "latitude": lat, "longitude": lon, "location_basis": "합성",
            "capacity_value": cap, "capacity_unit": unit, "capacity_kind": "설비 용량", "capacity_basis": "합성",
            "valid_from": valid_from, "valid_to": valid_to, "timezone": "Asia/Seoul", "interval": "hourly",
            "hour_convention": "hour-ending", "note": "selftest"}


def member(pf, ver, pid, ef="2025-01-01", et=""):
    return {"portfolio_id": pf, "composition_version": ver, "plant_id": pid, "effective_from": ef, "effective_to": et, "note": ""}


CAPS = {"fx-a": 100.0, "fx-b": 50.0, "fx-c": 250.0}
BASE_HOURLY = {pid: make_hourly(cap, seed) for (pid, cap), seed in zip(CAPS.items(), (11, 23, 37))}


def base_fixture():
    return {
        "plants": [plant(pid, cap) for pid, cap in CAPS.items()],
        "members": [member("fx-vpp", 1, pid) for pid in CAPS],
        "daily": {pid: daily_rows(pid, h) for pid, h in BASE_HOURLY.items()},
        "hourly": {pid: hourly_rows(pid, h) for pid, h in BASE_HOURLY.items()},
    }


def write_root(root, fx):
    root = Path(root)
    C.write_csv(root / "plants.csv", C.PLANT_COLUMNS, fx["plants"])
    C.write_csv(root / "portfolio_members.csv", C.MEMBER_COLUMNS, fx["members"])
    for pid, rows in fx["daily"].items():
        folder = root / "generation" / pid
        C.write_csv(folder / "generation_daily.csv", C.DAILY_COLUMNS, rows)
        if pid in fx.get("hourly", {}):
            C.write_csv(folder / "generation_hourly.csv", C.HOURLY_COLUMNS, fx["hourly"][pid])
        (folder / "manifest.json").write_text(json.dumps({"schema_version": C.SCHEMA_VERSION, "plant_id": pid, "raw": "synthetic"}) + "\n", encoding="utf-8")
    return root


def load(fx):
    with tempfile.TemporaryDirectory() as tmp:
        return C.load_root(write_root(tmp, fx))


def codes(loaded, level="error"):
    return sorted({i["code"] for i in loaded["issues"] if i["level"] == level})


def record(number, title, expected, actual, passed):
    results.append({"id": number, "title": title, "expected": expected, "actual": actual, "status": "통과" if passed else "실패"})


def s01_convert():
    header = "년월일,호기,총량,평균,최대,최소,최대(시간별),최소(시간별)," + ",".join(str(h) for h in range(1, 25))
    normal = [0] * 8 + [1.5, 4, 6, 8, 9, 8, 6, 4, 1.5] + [0] * 7

    def line(day, hours, total=None):
        total = sum(v for v in hours if v != "") if total is None else total
        return f"{day},1,{total},0,0,0,0,0," + ",".join(str(v) for v in hours)

    blank = list(normal)
    blank[12] = ""
    text = "\n".join([header, line("2025-03-01", normal), line("2025-03-02", [0] * 24),          # 03-03 은 원자료에 없다
                      line("2025-03-04", blank), line("2025-03-05", normal, total=99.0), line("2025-03-06", normal)]) + "\n"
    with tempfile.TemporaryDirectory() as tmp:
        raw = Path(tmp) / "raw.csv"
        raw.write_bytes(text.encode("cp949"))
        daily, hourly, info = convert_kospo_raw.convert(raw, "fx-raw")
    got = [(r["date"], r["quality"], r["energy_kwh"]) for r in daily]
    want = [("2025-03-01", "ok", 48.0), ("2025-03-02", "zero_day", 0.0), ("2025-03-03", "missing", None),
            ("2025-03-04", "partial", None), ("2025-03-05", "mismatch", 99.0), ("2025-03-06", "ok", 48.0)]
    record("S01", "남부발전 형식 원자료의 변환: 빈 칸은 0 이 아니라 partial, 빠진 날은 missing 행, 0 인 날은 zero_day, 합계가 다른 날은 mismatch",
           "ok, zero_day, missing, partial, mismatch, ok (CP949, '(kw)' 가 없는 머리 줄)",
           ", ".join(q for _, q, _ in got) + f" / 03-04 의 하루 값 {got[3][2]} / 인코딩 {info['encoding']}", got == want)


def s02_normal():
    loaded = load(base_fixture())
    record("S02", "정상 합성 자료(발전소 3곳, 400일, 시간대별 포함)는 오류 없이 통과한다", "오류 0건",
           f"오류 {len(C.errors_of(loaded['issues']))}건, 경고 {len(loaded['issues']) - len(C.errors_of(loaded['issues']))}건",
           not C.errors_of(loaded["issues"]))


def s03_duplicate_plant():
    fx = base_fixture()
    fx["plants"].append(plant("fx-a-copy", 100.0, dataset="fx-a"))
    fx["members"].append(member("fx-vpp", 1, "fx-a-copy"))
    fx["daily"]["fx-a-copy"] = [{**r, "plant_id": "fx-a-copy"} for r in fx["daily"]["fx-a"]]
    loaded = load(fx)
    cap = portfolio_capacity.capacity_at(loaded["plants"], loaded["members"], "fx-vpp", date(2025, 6, 1))
    ok = "PLANT-DUPLICATE-SOURCE" in codes(loaded) and cap["capacity_sum_kw"] == 400.0 and len(cap["excluded_duplicate_source"]) == 1
    record("S03", "같은 원자료를 다른 plant_id 로 한 번 더 등록하면 검증이 막고, 용량 합계는 한 번만 센다",
           "오류 PLANT-DUPLICATE-SOURCE, 용량 합계 400kW(500kW 가 아님)",
           f"오류 {codes(loaded)}, 합계 {cap['capacity_sum_kw']:g}kW, 한 번만 센 곳 {[d['plant_id'] for d in cap['excluded_duplicate_source']]}", ok)


def s04_unit_confusion():
    fx = base_fixture()
    fx["plants"][0] = plant("fx-a", 100.0, unit="MW")            # 100kW 를 100MW 로 적음
    too_big = codes(load(fx))
    fx = base_fixture()
    fx["plants"][0] = plant("fx-a", 0.1, unit="kW")              # 0.1MW 를 0.1kW 로 적음
    too_small = codes(load(fx))
    fx = base_fixture()
    fx["plants"][0] = plant("fx-a", 0.1, unit="MW")              # 0.1MW = 100kW. 맞는 값
    right = load(fx)
    ok = "UNIT-FAR-BELOW-CAPACITY" in too_big and "UNIT-OVER-CAPACITY" in too_small and not C.errors_of(right["issues"]) \
        and C.capacity_kw_at(right["plants"], "fx-a", date(2025, 6, 1)) == 100.0
    record("S04", "용량의 kW 와 MW 를 바꿔 적으면 발전량과 견줘 잡는다. 맞게 적은 MW 는 kW 로 환산된다",
           "100MW 로 적으면 UNIT-FAR-BELOW-CAPACITY, 0.1kW 로 적으면 UNIT-OVER-CAPACITY, 0.1MW 는 100kW 로 통과",
           f"100MW: {too_big} / 0.1kW: {too_small} / 0.1MW: 오류 {len(C.errors_of(right['issues']))}건, {C.capacity_kw_at(right['plants'], 'fx-a', date(2025, 6, 1)):g}kW", ok)


def s05_unit_conversion():
    got = (C.to_kw(0.055, "MW"), C.to_kw(55, "kW"), C.to_kwh(1.2, "MWh"), C.to_kwh(1500, "Wh"), C.to_kwh(3, "kWh"))
    ok = all(math.isclose(a, b) for a, b in zip(got, (55.0, 55.0, 1200.0, 1.5, 3.0)))
    record("S05", "단위 환산: MW→kW, MWh·Wh→kWh", "0.055MW=55kW, 1.2MWh=1200kWh, 1500Wh=1.5kWh", f"{got}", ok)


def s06_missing_date():
    fx = base_fixture()
    del fx["daily"]["fx-b"][100]
    loaded = load(fx)
    record("S06", "달력에서 하루의 행이 빠지면 막는다(값이 없어도 행은 둔다)", "오류 DAILY-MISSING-DATE", f"오류 {codes(loaded)}",
           "DAILY-MISSING-DATE" in codes(loaded))


def s07_duplicate_date():
    fx = base_fixture()
    fx["daily"]["fx-b"].insert(100, dict(fx["daily"]["fx-b"][100]))
    loaded = load(fx)
    record("S07", "같은 날짜가 두 번 있으면 막는다", "오류 DAILY-DUPLICATE-DATE", f"오류 {codes(loaded)}", "DAILY-DUPLICATE-DATE" in codes(loaded))


def s08_missing_value():
    fx = base_fixture()
    fx["daily"]["fx-b"][100] = {**fx["daily"]["fx-b"][100], "energy_kwh": None, "quality": "ok"}
    as_value = codes(load(fx))
    fx = base_fixture()
    fx["daily"]["fx-b"][100] = {**fx["daily"]["fx-b"][100], "energy_kwh": None, "quality": "missing"}
    fx["hourly"].pop("fx-b")
    loaded = load(fx)
    full = len(C.build_windows("fx-b", load(base_fixture())["daily"]["fx-b"]))
    holed = len(C.build_windows("fx-b", loaded["daily"]["fx-b"]))
    ok = "DAILY-BLANK-AS-VALUE" in as_value and not C.errors_of(loaded["issues"]) and full - holed == C.SEQ_LEN + 1
    record("S08", "값이 빈 날을 ok 로 적으면 막는다. missing 으로 적으면 받되, 그날이 낀 창은 만들지 않는다(0 으로 채우지 않는다)",
           f"빈 값+ok 는 DAILY-BLANK-AS-VALUE. 빈 값+missing 은 통과하고 창이 {C.SEQ_LEN + 1}개 준다",
           f"빈 값+ok: {as_value} / 빈 값+missing: 오류 {len(C.errors_of(loaded['issues']))}건, 창 {full}개 → {holed}개", ok)


def s09_bad_values():
    fx = base_fixture()
    fx["daily"]["fx-b"][10] = {**fx["daily"]["fx-b"][10], "energy_kwh": -1.0}
    fx["daily"]["fx-b"][11] = {**fx["daily"]["fx-b"][11], "energy_kwh": "nan"}
    fx["daily"]["fx-b"][12] = {**fx["daily"]["fx-b"][12], "energy_kwh": "inf"}
    got = codes(load(fx))
    record("S09", "음수와 유한하지 않은 값(nan, inf)을 막는다", "오류 DAILY-NEGATIVE, DAILY-VALUE", f"오류 {got}",
           "DAILY-NEGATIVE" in got and "DAILY-VALUE" in got)


def s10_wrong_plant_rows():
    fx = base_fixture()
    fx["daily"]["fx-b"][50] = {**fx["daily"]["fx-b"][50], "plant_id": "fx-a"}
    got = codes(load(fx))
    record("S10", "한 발전소의 파일에 다른 발전소의 행이 있으면 막는다", "오류 DAILY-WRONG-PLANT", f"오류 {got}", "DAILY-WRONG-PLANT" in got)


def s11_mixed_sequences():
    from data.features import HAICScaler, build_sequences   # 지금의 서빙 코드
    loaded = load(base_fixture())
    own = [w for pid, rows in loaded["daily"].items() for w in C.build_windows(pid, rows)]
    naive = C.naive_concat_windows(loaded["daily"])
    bad = C.window_problems(naive)
    mixed = sum(1 for b in bad if b[1] == "mixed-plants")
    flat = [{"Date": r["date"].isoformat(), "Close": r["energy_kwh"], "Volume": 1.0} for pid in sorted(loaded["daily"]) for r in loaded["daily"][pid]]
    X, y = build_sequences(flat, HAICScaler().fit(flat))    # 오류 없이 만들어진다
    crafted = [{"plant_id": "fx-a", "row_plant_ids": ["fx-a"] * 20 + ["fx-b"], "input_dates": [START + timedelta(days=i) for i in range(20)],
                "target_date": START + timedelta(days=20)}]
    ok = not C.window_problems(own) and mixed == C.SEQ_LEN * 2 and len(X) == len(naive) and len(C.window_problems(crafted)) == 1
    record("S11", "발전소별로 만든 창에는 섞임이 없다. 행을 이어 붙이면 지금의 build_sequences 는 오류 없이 섞인 창을 만든다",
           f"발전소별 창의 문제 0개. 이어 붙이면 섞인 창 {C.SEQ_LEN * 2}개(경계 2곳 × 20). 점검 함수가 섞인 창을 찾는다",
           f"발전소별 창 {len(own)}개의 문제 {len(C.window_problems(own))}개 / 이어 붙인 창 {len(naive)}개 가운데 섞인 창 {mixed}개, "
           f"build_sequences 가 오류 없이 만든 창 {len(X)}개 / 만든 섞인 창 1개 가운데 찾은 것 {len(C.window_problems(crafted))}개", ok)


def composition_fixture():
    fx = base_fixture()
    fx["members"] = [member("fx-vpp", 1, "fx-a", "2025-01-01", "2025-06-30"), member("fx-vpp", 1, "fx-b", "2025-01-01", "2025-06-30"),
                     member("fx-vpp", 2, "fx-a", "2025-07-01"), member("fx-vpp", 2, "fx-b", "2025-07-01"), member("fx-vpp", 2, "fx-c", "2025-07-01")]
    return fx


def s12_composition_change():
    loaded = load(composition_fixture())
    before = portfolio_capacity.capacity_at(loaded["plants"], loaded["members"], "fx-vpp", date(2025, 6, 30))
    after = portfolio_capacity.capacity_at(loaded["plants"], loaded["members"], "fx-vpp", date(2025, 7, 1))
    try:
        evaluate.run(loaded, "fx-vpp", date(2025, 6, 1), date(2025, 7, 31))
        stopped = "멈추지 않음"
    except SystemExit as exc:
        stopped = str(exc)
    fixed = evaluate.run(loaded, "fx-vpp", date(2025, 6, 1), date(2025, 7, 31), members_override=["fx-a", "fx-b"])
    ok = (before["capacity_sum_kw"], before["composition_version"], after["capacity_sum_kw"], after["composition_version"]) == (150.0, 1, 400.0, 2) \
        and "구성 변경" in stopped and fixed["daily"]["status"] == "ok" and not C.errors_of(loaded["issues"])
    record("S12", "구성이 바뀌면 날짜에 따라 구성 버전과 용량 합계가 달라진다. 구성 변경을 걸친 기간의 평가는 멈추고, 발전소를 고정하면 평가한다",
           "06-30 은 v1 150kW, 07-01 은 v2 400kW. 06-01~07-31 평가는 멈춤. --members 로 고정하면 평가",
           f"06-30 v{before['composition_version']} {before['capacity_sum_kw']:g}kW, 07-01 v{after['composition_version']} {after['capacity_sum_kw']:g}kW / "
           f"멈춤: {'예' if '구성 변경' in stopped else '아니오'} / 고정 평가: {fixed['daily']['status']}, 대상일 {fixed['daily'].get('coverage', {}).get('evaluated_days')}일", ok)


def s13_composition_errors():
    fx = composition_fixture()
    fx["members"][2:] = [member("fx-vpp", 2, p, "2025-06-15") for p in ("fx-a", "fx-b", "fx-c")]      # v1 과 16일 겹친다
    overlap = codes(load(fx))
    fx = base_fixture()
    fx["members"].append(member("fx-other", 1, "fx-a"))
    multi = codes(load(fx))
    fx = base_fixture()
    fx["members"].append(member("fx-vpp", 1, "fx-zz"))
    unknown = codes(load(fx))
    ok = "MEMBER-VERSION-OVERLAP" in overlap and "MEMBER-MULTI-PORTFOLIO" in multi and "MEMBER-UNKNOWN-PLANT" in unknown
    record("S13", "구성 버전의 기간이 겹치거나, 한 발전소가 같은 기간에 두 포트폴리오에 들거나, 등록부에 없는 발전소를 넣으면 막는다",
           "MEMBER-VERSION-OVERLAP, MEMBER-MULTI-PORTFOLIO, MEMBER-UNKNOWN-PLANT", f"{overlap} / {multi} / {unknown}", ok)


def s14_capacity_change():
    fx = base_fixture()
    fx["plants"][0] = plant("fx-a", 100.0, valid_to="2025-06-30")
    fx["plants"].append(plant("fx-a", 120.0, valid_from="2025-07-01"))
    loaded = load(fx)
    caps = (C.capacity_kw_at(loaded["plants"], "fx-a", date(2025, 6, 30)), C.capacity_kw_at(loaded["plants"], "fx-a", date(2025, 7, 1)))
    fx["plants"][-1] = plant("fx-a", 120.0, valid_from="2025-06-01")
    overlap = codes(load(fx))
    ok = caps == (100.0, 120.0) and not C.errors_of(loaded["issues"]) and "PLANT-PERIOD-OVERLAP" in overlap
    record("S14", "용량이 바뀐 발전소는 유효 기간이 다른 두 행으로 적고 날짜로 고른다. 기간이 겹치면 막는다",
           "06-30 은 100kW, 07-01 은 120kW. 겹치면 PLANT-PERIOD-OVERLAP", f"{caps[0]:g}kW, {caps[1]:g}kW / 겹침: {overlap}", ok)


def s15_unknown_capacity():
    fx = base_fixture()
    fx["plants"][2] = plant("fx-c", "", unit="")
    loaded = load(fx)
    cap = portfolio_capacity.capacity_at(loaded["plants"], loaded["members"], "fx-vpp", date(2025, 6, 1))
    ok = not C.errors_of(loaded["issues"]) and "PLANT-CAPACITY-UNKNOWN" in codes(loaded, "warn") \
        and cap["capacity_sum_kw"] == 150.0 and cap["excluded_unknown_capacity"] == ["fx-c"] and cap["is_complete"] is False
    record("S15", "용량을 모르는 발전소는 칸을 비운다. 합계에서 빼고 '전체가 아니다'라고 알린다(값을 지어내지 않는다)",
           "경고 PLANT-CAPACITY-UNKNOWN, 합계 150kW, 뺀 곳 fx-c, 전체 여부 거짓",
           f"경고 {codes(loaded, 'warn')}, 합계 {cap['capacity_sum_kw']:g}kW, 뺀 곳 {cap['excluded_unknown_capacity']}, 전체 여부 {cap['is_complete']}", ok)


def s16_member_data_missing():
    fx = base_fixture()
    fx["daily"].pop("fx-c")
    fx["hourly"].pop("fx-c")
    loaded = load(fx)
    cov = coverage.run(loaded, "fx-vpp")["portfolios"]["fx-vpp"][0]
    ev = evaluate.run(loaded, "fx-vpp", date(2025, 3, 1), date(2025, 8, 31))
    late = base_fixture()
    late["daily"]["fx-c"] = late["daily"]["fx-c"][243:]          # fx-c 의 자료가 2025-09-01 에 시작한다
    late["hourly"].pop("fx-c")
    late_cov = coverage.run(load(late), "fx-vpp")["portfolios"]["fx-vpp"][0]
    ok = cov["members_without_data"] == ["fx-c"] and cov["common_target_days"] == 0 and ev["daily"]["status"] == "not_evaluable" \
        and late_cov["common_first_target"] == "2025-09-21"
    record("S16", "구성원 한 곳의 자료가 없으면 합계를 평가하지 않는다(남은 발전소만 더해 합계라고 부르지 않는다). 자료가 늦게 시작하면 공통 기간이 그만큼 준다",
           "자료 없는 구성원 fx-c, 공통 대상일 0, 평가 not_evaluable. fx-c 가 09-01 에 시작하면 첫 공통 대상일은 09-21",
           f"자료 없는 구성원 {cov['members_without_data']}, 공통 대상일 {cov['common_target_days']}, 평가 {ev['daily']['status']} / 늦게 시작: 첫 공통 대상일 {late_cov['common_first_target']}", ok)


def s17_model_missing():
    loaded = load(base_fixture())
    start, end = date(2025, 10, 1), date(2025, 12, 31)
    series = {p: C.daily_series(rows) for p, rows in loaded["daily"].items()}
    days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
    full = {p: {d: series[p][d] * 0.95 for d in days} for p in series}             # 실제보다 5% 낮게 내는 가짜 모델
    r_full = evaluate.evaluate_daily(loaded, sorted(series), start, end, full)
    partial = {p: v for p, v in full.items() if p != "fx-c"}
    r_partial = evaluate.evaluate_daily(loaded, sorted(series), start, end, partial)
    holes = {p: {d: v for d, v in vals.items() if d.day != 15 or p != "fx-b"} for p, vals in full.items()}
    r_holes = evaluate.evaluate_daily(loaded, sorted(series), start, end, holes)
    ok = "model" in r_full["portfolio"]["methods"] and abs(r_full["portfolio"]["methods"]["model"]["bias_pct"] + 5.0) < 1e-6 \
        and r_partial["coverage"]["model_status"] == "partial" and "model" not in r_partial["portfolio"]["methods"] \
        and r_holes["coverage"]["model_status"] == "restricted" and r_holes["coverage"]["model_days_without_predictions"] == 3 \
        and r_holes["portfolio"]["methods"]["persistence"]["n"] == r_holes["portfolio"]["methods"]["model"]["n"]
    record("S17", "한 발전소의 예측(모델)이 없으면 모델의 합계 지표를 내지 않고 누락을 알린다. 일부 날짜만 없으면 모든 방법을 같은 날짜로 좁혀 견준다",
           "전부 있으면 모델 치우침 -5%. fx-c 가 없으면 partial 이고 모델 합계 없음. fx-b 의 15일 치 3일이 없으면 restricted 이고 기준 예측도 같은 날 수",
           f"전부: 치우침 {r_full['portfolio']['methods']['model']['bias_pct']:.2f}% / 누락: {r_partial['coverage']['model_status']}, 모델 합계 {'있음' if 'model' in r_partial['portfolio']['methods'] else '없음'} / "
           f"일부 날짜: {r_holes['coverage']['model_status']}, 빠진 날 {r_holes['coverage']['model_days_without_predictions']}일, "
           f"날 수 {r_holes['portfolio']['methods']['persistence']['n']} = {r_holes['portfolio']['methods']['model']['n']}", ok)


def s18_upload_selection():
    from data.storage import latest_upload   # 지금의 서빙 코드
    with tempfile.TemporaryDirectory() as tmp:
        flat = Path(tmp) / "flat"
        flat.mkdir()
        for i, name in enumerate(["haic_aaaa_plant_a.csv", "haic_bbbb_plant_b.csv"]):      # A 를 먼저, B 를 나중에 올린다
            f = flat / name
            f.write_text("Date,Close,Volume\n", encoding="utf-8")
            os.utime(f, (1_700_000_000 + i * 60, 1_700_000_000 + i * 60))
        current = Path(latest_upload(str(flat))).name
        split = Path(tmp) / "split"
        for i, pid in enumerate(["fx-a", "fx-b"]):
            (split / pid).mkdir(parents=True)
            f = split / pid / f"upload_{pid}.csv"
            f.write_text("Date,Close,Volume\n", encoding="utf-8")
            os.utime(f, (1_700_000_000 + i * 60, 1_700_000_000 + i * 60))
        proposed = Path(C.latest_upload_for(split, "fx-a")).name
        try:
            C.latest_upload_for(split, "fx-c")
            missing = "오류 없음"
        except FileNotFoundError:
            missing = "FileNotFoundError"
    ok = current == "haic_bbbb_plant_b.csv" and proposed == "upload_fx-a.csv" and missing == "FileNotFoundError"
    record("S18", "지금의 latest_upload() 는 마지막에 올린 파일을 고르므로 A 를 학습하려 해도 B 의 파일이 잡힌다. 발전소별 폴더에서 고르면 A 의 파일이 잡힌다",
           "지금의 코드: B 의 파일(문제의 재현). 제안: A 의 파일. 파일이 없는 발전소는 FileNotFoundError",
           f"지금의 코드: {current} / 제안: {proposed} / 파일 없는 발전소: {missing}", ok)


def s19_bundle_mismatch():
    from data.features import HAICScaler   # 지금의 서빙 코드
    loaded = load(base_fixture())
    rows = {p: [{"Close": r["energy_kwh"], "Volume": 10.0 + i % 7} for i, r in enumerate(loaded["daily"][p])] for p in ("fx-a", "fx-c")}
    with tempfile.TemporaryDirectory() as tmp:
        paths = {}
        for p in rows:
            paths[p] = Path(tmp) / f"scaler_{p}.pkl"
            HAICScaler().fit(rows[p]).save(str(paths[p]))
        manifest = bundle_check.make_manifest("fx-a", bundle_check.model_name_for("fx-a"), 1, paths["fx-a"])
        right = bundle_check.check_bundle(manifest, paths["fx-a"], "fx-a")
        wrong_scaler = [i["code"] for i in bundle_check.check_bundle(manifest, paths["fx-c"], "fx-a")]
        wrong_plant = [i["code"] for i in bundle_check.check_bundle(manifest, paths["fx-a"], "fx-c")]
        a, c = HAICScaler.load(str(paths["fx-a"])), HAICScaler.load(str(paths["fx-c"]))
        silent = (a.inverse_close(0.5), c.inverse_close(0.5))
    ok = not right and wrong_scaler == ["BUNDLE-SCALER"] and wrong_plant == ["BUNDLE-PLANT"] and silent[1] > 2 * silent[0]
    record("S19", "모델의 출력 0.5 를 A 의 스케일러와 C 의 스케일러로 되돌리면 값이 크게 다른데 오류는 나지 않는다. 묶음 기록의 해시와 plant_id 를 견주면 잡힌다",
           "짝이 맞으면 통과. 다른 발전소의 스케일러는 BUNDLE-SCALER, 다른 발전소의 요청은 BUNDLE-PLANT",
           f"맞는 짝: 문제 {len(right)}건 / 다른 스케일러: {wrong_scaler} / 다른 발전소: {wrong_plant} / 같은 출력 0.5 → A {silent[0]:.1f}kWh, C {silent[1]:.1f}kWh (오류 없음)", ok)


def s20_rmse_not_additive():
    # 두 발전소의 하루 발전량이 반대로 움직이게 만든다. 전일값 예측의 오차가 서로 지워진다.
    days = [START + timedelta(days=i) for i in range(120)]
    fx = {"plants": [plant("fx-up", 100.0), plant("fx-down", 100.0)], "members": [member("fx-pair", 1, "fx-up"), member("fx-pair", 1, "fx-down")],
          "daily": {}, "hourly": {}}
    for pid, sign in (("fx-up", 1), ("fx-down", -1)):
        fx["daily"][pid] = [{"plant_id": pid, "date": d.isoformat(), "energy_kwh": 300.0 + sign * (40.0 if i % 2 == 0 else -40.0),
                             "quality": "ok", "source_file": "synthetic"} for i, d in enumerate(days)]
    r = evaluate.run(load(fx), "fx-pair", days[10], days[-1])["daily"]
    port = r["portfolio"]["methods"]["persistence"]
    plants = [r["per_plant"][p]["methods"]["persistence"]["rmse_kwh"] for p in ("fx-up", "fx-down")]
    loaded = load(base_fixture())
    b = evaluate.run(loaded, "fx-vpp", date(2025, 3, 1), date(2025, 12, 31))["daily"]
    bp = b["portfolio"]["methods"]["persistence"]
    ok = all(abs(x - 80.0) < 1e-9 for x in plants) and port["rmse_kwh"] < 1e-9 and abs(port["sum_of_plant_rmse_kwh"] - 160.0) < 1e-9 \
        and bp["rmse_kwh"] < bp["sum_of_plant_rmse_kwh"] and b["averages"]["persistence"]["portfolio_wape_pct"] < b["averages"]["persistence"]["energy_weighted_wape_pct"]
    record("S20", "포트폴리오 RMSE 는 발전소별 RMSE 의 합이 아니다. 오차가 반대로 움직이면 발전소마다 크게 틀려도 합계의 오차는 0 에 가깝다",
           "반대로 움직이는 두 곳: 발전소별 RMSE 80kWh 씩(합 160), 포트폴리오 RMSE 0. 일반 합성 자료에서도 포트폴리오 RMSE < 발전소별 RMSE 의 합",
           f"발전소별 {plants[0]:.1f}, {plants[1]:.1f}kWh (합 {port['sum_of_plant_rmse_kwh']:.1f}), 포트폴리오 {port['rmse_kwh']:.1f}kWh / "
           f"3곳 합성: 포트폴리오 {bp['rmse_kwh']:.1f} < 합 {bp['sum_of_plant_rmse_kwh']:.1f}kWh, 합계끼리 견준 오차율 {b['averages']['persistence']['portfolio_wape_pct']:.1f}% < 발전량 가중 {b['averages']['persistence']['energy_weighted_wape_pct']:.1f}%", ok)


def s21_hourly_partial():
    fx = base_fixture()
    fx["hourly"]["fx-a"] = [r for r in fx["hourly"]["fx-a"] if not (r["date"] == "2025-05-05" and r["hour"] in (12, 13))]
    partial_as_full = codes(load(fx))
    fx = base_fixture()
    target = next(i for i, r in enumerate(fx["hourly"]["fx-a"]) if r["date"] == "2025-05-05" and r["hour"] == 12)
    fx["hourly"]["fx-a"][target] = {**fx["hourly"]["fx-a"][target], "energy_kwh": fx["hourly"]["fx-a"][target]["energy_kwh"] + 5}
    mismatch = codes(load(fx))
    loaded = load(base_fixture())
    h = evaluate.run(loaded, "fx-vpp", date(2025, 3, 1), date(2025, 12, 31), hourly=True)["hourly"]
    ok = "HOURLY-PARTIAL-AS-FULL" in partial_as_full and "HOURLY-SUM-MISMATCH" in mismatch and h["status"] == "ok" and h["portfolio"]["persistence"]["eligible_hours"] > 0
    record("S21", "시간대별 값이 일부만 있는 날을 온전한 하루 값으로 쓰면 막는다. 24칸의 합이 하루 값과 다르면 막는다. 시간대별 참고 계산이 돈다",
           "HOURLY-PARTIAL-AS-FULL, HOURLY-SUM-MISMATCH. 참고 계산 status ok",
           f"{partial_as_full} / {mismatch} / 참고 계산 {h['status']}, 대상 {h['portfolio']['persistence']['eligible_hours']}시간", ok)


CASES = [s01_convert, s02_normal, s03_duplicate_plant, s04_unit_confusion, s05_unit_conversion, s06_missing_date, s07_duplicate_date,
         s08_missing_value, s09_bad_values, s10_wrong_plant_rows, s11_mixed_sequences, s12_composition_change, s13_composition_errors,
         s14_capacity_change, s15_unknown_capacity, s16_member_data_missing, s17_model_missing, s18_upload_selection, s19_bundle_mismatch,
         s20_rmse_not_additive, s21_hourly_partial]


def main():
    C.use_utf8_output()
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--out", type=Path, help="selftest.json 과 selftest.txt 를 둘 폴더")
    a = p.parse_args()

    for case in CASES:
        try:
            case()
        except Exception as exc:   # 도구가 죽는 것도 실패로 적는다
            record(case.__name__[:3].upper(), case.__name__, "예외 없이 끝난다", f"{type(exc).__name__}: {exc}", False)
    failed = [r for r in results if r["status"] != "통과"]
    lines = [f"합성 자료 점검: {len(results)}건 가운데 통과 {len(results) - len(failed)}건, 실패 {len(failed)}건",
             f"파이썬 {platform.python_version()}, 합성 발전소 3곳 × {N_DAYS}일. 합성 자료의 수치는 기능 확인용이고 성능이나 제도 요건의 근거가 아니다", ""]
    for r in results:
        lines += [f"[{r['id']}] {r['status']}  {r['title']}", f"    기대: {r['expected']}", f"    실제: {r['actual']}"]
    print("\n".join(lines))
    if a.out:
        a.out.mkdir(parents=True, exist_ok=True)
        (a.out / "selftest.json").write_text(json.dumps({"python": platform.python_version(), "results": results}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (a.out / "selftest.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
