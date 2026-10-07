"""포트폴리오의 설비 용량 합계를 낸다. 같은 발전소를 두 번 더하지 않고, 용량을 모르는 발전소는 빼고 따로 알린다.

합계는 **등록부에 적힌 설비 용량의 합**이다. 발전량의 합이 아니고, 시간 단위가 붙지 않는다.
제도의 참여 요건(설비 용량 20MW 초과)과 견준 값은 참고다. 이 합계가 20MW 를 넘어도 제도의 참여 요건을 채웠다는 뜻이 아니다.
요건에는 용량 말고도 등록, 계량, 구성 비율, 등록시험이 있다(docs/proposal/multi-plant-extension.md 2절).

실행 (저장소 루트에서. 표준 라이브러리만 쓴다):
    python tools/multi_plant/portfolio_capacity.py --data-root <자료 폴더> --portfolio <portfolio_id> [--date YYYY-MM-DD] [--json <결과 파일>]
--date 를 주지 않으면 구성 버전마다 그 버전이 시작하는 날의 합계를 낸다.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C  # noqa: E402


def capacity_at(plants, members, portfolio_id, day):
    version, ids = C.members_at(members, portfolio_id, day)
    known, unknown, unregistered, seen_sources, duplicates = [], [], [], {}, []
    for pid in ids:
        row = C.plant_row_at(plants, pid, day)
        if row is None:
            unregistered.append(pid)
            continue
        source = (row["source_org"], row["source_dataset"])
        if source in seen_sources:
            duplicates.append({"plant_id": pid, "same_as": seen_sources[source]})
            continue
        seen_sources[source] = pid
        if row["_cap_kw"] is None:
            unknown.append(pid)
        else:
            known.append({"plant_id": pid, "capacity_kw": row["_cap_kw"], "capacity_kind": row["capacity_kind"],
                          "capacity_basis": row["capacity_basis"], "entered_as": f"{row['capacity_value']} {row['capacity_unit']}"})
    total_kw = sum(k["capacity_kw"] for k in known)
    return {
        "portfolio_id": portfolio_id,
        "date": day.isoformat(),
        "composition_version": version,
        "members": ids,
        "counted": known,
        "capacity_sum_kw": round(total_kw, 6),
        "capacity_sum_mw": round(total_kw / 1000, 9),
        "excluded_unknown_capacity": unknown,
        "excluded_duplicate_source": duplicates,
        "excluded_not_registered_on_date": unregistered,
        "is_complete": not (unknown or unregistered) and version is not None,
        "reference": {"scheme_requirement": f"설비 용량 {C.REFERENCE_MW:g}MW 초과 (참고 비교)",
                      "share_of_reference_pct": round(total_kw / (C.REFERENCE_MW * 1000) * 100, 4),
                      "exceeds_reference": total_kw > C.REFERENCE_MW * 1000,
                      "note": "용량의 비교일 뿐 참여 자격의 판정이 아니다"},
    }


def render(r):
    lines = [f"{r['portfolio_id']} @ {r['date']} (구성 v{r['composition_version']}): 구성원 {len(r['members'])}곳, "
             f"확인된 설비 용량 합계 {r['capacity_sum_kw']:g}kW = {r['capacity_sum_mw']:g}MW"]
    for k in r["counted"]:
        lines.append(f"    {k['plant_id']}: {k['capacity_kw']:g}kW (적은 값 {k['entered_as']}, {k['capacity_kind'] or '종류 미기입'})")
    if r["excluded_unknown_capacity"]:
        lines.append(f"    용량을 몰라 뺀 곳: {', '.join(r['excluded_unknown_capacity'])}  → 합계는 전체가 아니다")
    for d in r["excluded_duplicate_source"]:
        lines.append(f"    같은 원자료라 한 번만 센 곳: {d['plant_id']} (= {d['same_as']})")
    if r["excluded_not_registered_on_date"]:
        lines.append(f"    그 날짜에 등록부의 유효 기간 밖인 곳: {', '.join(r['excluded_not_registered_on_date'])}")
    ref = r["reference"]
    lines.append(f"    참고: 제도 기준 {C.REFERENCE_MW:g}MW 의 {ref['share_of_reference_pct']:g}%. 기준 초과 {'예' if ref['exceeds_reference'] else '아니오'}. {ref['note']}")
    return "\n".join(lines)


def main():
    C.use_utf8_output()
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--data-root", type=Path, required=True)
    p.add_argument("--portfolio", required=True)
    p.add_argument("--date")
    p.add_argument("--json", type=Path)
    a = p.parse_args()

    plants, issues = C.load_plants(a.data_root / "plants.csv")
    members, got = C.load_members(a.data_root / "portfolio_members.csv", plants)
    issues += got
    blocking = C.errors_of(issues)
    for i in blocking:
        print(f"[오류] {i['code']}  {i['where']}  {i['message']}")
    if blocking:
        print("등록부나 구성에 오류가 있어 합계를 내지 않는다. 먼저 validate.py 로 고친다.")
        sys.exit(1)
    if a.date:
        day = C.parse_date(a.date)
        if day is None:
            raise SystemExit("--date 는 YYYY-MM-DD 여야 한다")
        days = [day]
    else:
        days = [v["from"] for v in C.composition_versions(members, a.portfolio).values()]
        if not days:
            raise SystemExit(f"포트폴리오 '{a.portfolio}' 의 구성이 없다")
    results = [capacity_at(plants, members, a.portfolio, d) for d in days]
    for r in results:
        print(render(r))
    if a.json:
        a.json.parent.mkdir(parents=True, exist_ok=True)
        a.json.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
