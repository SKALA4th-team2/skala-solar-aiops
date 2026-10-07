"""발전소별 자료 기간과, 포트폴리오를 함께 평가할 수 있는 기간을 확인한다. 창이 발전소끼리 섞이지 않는지도 본다.

내는 것:
    1. 발전소별: 첫 날과 끝 날, 쓸 수 있는 날과 못 쓰는 날의 수, 가장 길게 이어진 구간, 만들 수 있는 창(20일 + 다음 날)의 수
    2. 포트폴리오: 구성 버전별 구성원, 모든 구성원을 함께 평가할 수 있는 대상일의 수와 범위,
       날마다의 커버리지(자료가 있는 구성원 수와 그 용량의 비율), 빠진 발전소
    3. 창 점검: 발전소별로 만든 창에 다른 발전소나 날짜의 틈이 섞였는가.
       발전소의 행을 그냥 이어 붙였을 때 경계를 넘는 창이 몇 개 생기는가(해서는 안 되는 방식의 크기)

실행 (저장소 루트에서. 표준 라이브러리만 쓴다):
    python tools/multi_plant/coverage.py --data-root <자료 폴더> [--portfolio <portfolio_id>] [--start YYYY-MM-DD --end YYYY-MM-DD] [--json <결과 파일>]
"""
import argparse
import json
import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C  # noqa: E402

MIN_TEST_DAYS = 180   # docs/decisions/0005-deployment-gate.md 의 시험 구간 하한


def plant_coverage(pid, rows):
    series = C.daily_series(rows)
    usable_days = [d for d, v in series.items() if v is not None]
    longest = run = 0
    best_end = prev = None
    for d in sorted(usable_days):
        run = run + 1 if prev is not None and (d - prev).days == 1 else 1
        if run > longest:
            longest, best_end = run, d
        prev = d
    windows = C.build_windows(pid, rows)
    counts = {q: 0 for q in C.QUALITY}
    for r in rows:
        counts[r["quality"]] += 1
    return {
        "plant_id": pid,
        "first_date": rows[0]["date"].isoformat() if rows else None,
        "last_date": rows[-1]["date"].isoformat() if rows else None,
        "days": len(rows),
        "usable_days": len(usable_days),
        "quality_days": counts,
        "longest_usable_run": {"days": longest, "end": best_end.isoformat() if best_end else None},
        "windows": len(windows),
        "first_target": windows[0]["target_date"].isoformat() if windows else None,
        "last_target": windows[-1]["target_date"].isoformat() if windows else None,
        "test_days_at_20pct": len(windows) - int(len(windows) * 0.8),
    }, windows


def portfolio_coverage(loaded, portfolio_id, windows_by_plant, start=None, end=None):
    plants, members = loaded["plants"], loaded["members"]
    versions = C.composition_versions(members, portfolio_id)
    targets = {pid: {w["target_date"] for w in ws} for pid, ws in windows_by_plant.items()}
    series = {pid: C.daily_series(rows) for pid, rows in loaded["daily"].items()}
    out = []
    for ver, v in versions.items():
        ids = v["plants"]
        have = [p for p in ids if p in targets]
        lacking = [p for p in ids if p not in targets]
        lo = max([v["from"]] + ([start] if start else []))
        hi = min([v["to"]] + ([end] if end else []))
        # 자료가 있는 날짜의 범위 안으로 좁힌다
        firsts = [min(series[p]) for p in have if series[p]]
        lasts = [max(series[p]) for p in have if series[p]]
        if firsts:
            lo, hi = max(lo, min(firsts)), min(hi, max(lasts))
        common = sorted(d for d in (set.intersection(*[targets[p] for p in have]) if have and not lacking else set()) if lo <= d <= hi)
        day, any_days, full_days, cap_cov = lo, 0, 0, []
        while firsts and day <= hi:
            present = [p for p in have if series[p].get(day) is not None]
            caps = {p: C.capacity_kw_at(plants, p, day) for p in ids}
            if present:
                any_days += 1
            if len(present) == len(ids):
                full_days += 1
            if all(c is not None for c in caps.values()) and sum(caps.values()) > 0:
                cap_cov.append(sum(caps[p] for p in present) / sum(caps.values()))
            day += timedelta(days=1)
        span = (hi - lo).days + 1 if firsts and hi >= lo else 0
        out.append({
            "composition_version": ver,
            "effective": [v["from"].isoformat(), None if v["to"] == C.FAR_FUTURE else v["to"].isoformat()],
            "members": ids,
            "members_without_data": lacking,
            "window_checked": [lo.isoformat(), hi.isoformat()] if span else None,
            "days_in_window": span,
            "days_all_members_have_value": full_days,
            "days_some_member_has_value": any_days,
            "mean_capacity_coverage_pct": round(sum(cap_cov) / len(cap_cov) * 100, 2) if cap_cov else None,
            "common_target_days": len(common),
            "common_first_target": common[0].isoformat() if common else None,
            "common_last_target": common[-1].isoformat() if common else None,
            "enough_for_gate_test": (len(common) - int(len(common) * 0.8)) >= MIN_TEST_DAYS,
            "note": ("구성원 가운데 자료가 없는 곳이 있어 합계를 평가할 수 없다" if lacking else
                     "공통 대상일은 모든 구성원이 이어진 20일과 대상일의 값을 가진 날이다"),
        })
    return out


def run(loaded, portfolio_id=None, start=None, end=None):
    per_plant, windows_by_plant = [], {}
    for pid, rows in sorted(loaded["daily"].items()):
        info, windows = plant_coverage(pid, rows)
        per_plant.append(info)
        windows_by_plant[pid] = windows
    own = [w for ws in windows_by_plant.values() for w in ws]
    naive = C.naive_concat_windows(loaded["daily"])
    naive_bad = C.window_problems(naive)
    result = {
        "schema_version": C.SCHEMA_VERSION,
        "seq_len": C.SEQ_LEN,
        "plants": per_plant,
        "sequence_check": {
            "per_plant_windows": len(own),
            "per_plant_problems": len(C.window_problems(own)),
            "naive_concat_windows": len(naive),
            "naive_concat_mixed_plants": sum(1 for b in naive_bad if b[1] == "mixed-plants"),
            "naive_concat_date_gaps": sum(1 for b in naive_bad if b[1] == "date-gap"),
            "note": "naive_concat 은 발전소의 행을 이어 붙여 지금의 build_sequences 처럼 자른 경우다. 쓰면 안 되는 방식의 크기를 보이려는 값이다",
        },
    }
    ids = [portfolio_id] if portfolio_id else sorted({m["portfolio_id"] for m in loaded["members"]})
    result["portfolios"] = {pf: portfolio_coverage(loaded, pf, windows_by_plant, start, end) for pf in ids}
    return result


def render(result):
    lines = ["[발전소별]"]
    for p in result["plants"]:
        q = p["quality_days"]
        lines.append(f"  {p['plant_id']}: {p['first_date']} ~ {p['last_date']}, {p['days']}일 가운데 쓸 수 있는 날 {p['usable_days']}일 "
                     f"(zero_day {q['zero_day']}, partial {q['partial']}, mismatch {q['mismatch']}, missing {q['missing']}), "
                     f"가장 긴 이어진 구간 {p['longest_usable_run']['days']}일, 창 {p['windows']}개, 뒤 20% 는 {p['test_days_at_20pct']}일")
    s = result["sequence_check"]
    lines.append("[창 점검]")
    lines.append(f"  발전소별로 만든 창 {s['per_plant_windows']}개 가운데 문제 {s['per_plant_problems']}개")
    lines.append(f"  행을 이어 붙여 만들면 창 {s['naive_concat_windows']}개 가운데 발전소가 섞인 창 {s['naive_concat_mixed_plants']}개, 날짜가 끊긴 창 {s['naive_concat_date_gaps']}개")
    for pf, versions in result["portfolios"].items():
        lines.append(f"[포트폴리오 {pf}]")
        for v in versions:
            lines.append(f"  구성 v{v['composition_version']} ({v['effective'][0]} ~ {v['effective'][1] or '계속'}): {', '.join(v['members'])}")
            if v["members_without_data"]:
                lines.append(f"    자료가 없는 구성원: {', '.join(v['members_without_data'])}")
            if v["window_checked"]:
                lines.append(f"    본 기간 {v['window_checked'][0]} ~ {v['window_checked'][1]} ({v['days_in_window']}일): 모든 구성원에 값이 있는 날 {v['days_all_members_have_value']}일, "
                             f"용량 기준 평균 커버리지 {v['mean_capacity_coverage_pct']}%")
            lines.append(f"    함께 평가할 수 있는 대상일 {v['common_target_days']}일 ({v['common_first_target']} ~ {v['common_last_target']}), "
                         f"게이트의 시험 구간 {MIN_TEST_DAYS}일 이상 {'가능' if v['enough_for_gate_test'] else '불가'}")
            lines.append(f"    {v['note']}")
    return "\n".join(lines)


def main():
    C.use_utf8_output()
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--data-root", type=Path, required=True)
    p.add_argument("--portfolio")
    p.add_argument("--start")
    p.add_argument("--end")
    p.add_argument("--json", type=Path)
    a = p.parse_args()

    loaded = C.load_root(a.data_root)
    blocking = C.errors_of(loaded["issues"])
    for i in blocking:
        print(f"[오류] {i['code']}  {i['where']}  {i['message']}")
    if blocking:
        print("자료에 오류가 있어 기간을 계산하지 않는다. 먼저 validate.py 로 고친다.")
        sys.exit(1)
    start, end = (C.parse_date(a.start) if a.start else None), (C.parse_date(a.end) if a.end else None)
    result = run(loaded, a.portfolio, start, end)
    print(render(result))
    if a.json:
        a.json.parent.mkdir(parents=True, exist_ok=True)
        a.json.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    sys.exit(1 if result["sequence_check"]["per_plant_problems"] else 0)


if __name__ == "__main__":
    main()
