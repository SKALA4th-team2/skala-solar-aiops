"""자료 폴더(등록부, 포트폴리오 구성, 발전소별 실적)가 계약을 지키는지 확인한다.

보는 것:
    - 등록부: 필수 칸, plant_id 의 모양, 유효 기간의 겹침, 같은 원자료의 중복 등록, 용량의 단위, 좌표
    - 포트폴리오 구성: 등록부에 있는 발전소인가, 한 구성 안의 중복, 구성 버전끼리의 기간 겹침, 한 발전소의 이중 소속
    - 실적: 폴더 이름과 행의 plant_id, 날짜의 형식·순서·중복·빠짐, 음수와 비유한 값, 결측을 값으로 적은 행
    - 단위: 하루 발전량 ÷ (용량 × 24시간)이 1 을 넘거나 지나치게 작은가
    - 시간대별 자료: 24칸의 합과 하루 값, 일부만 있는 날을 하루 값으로 쓴 곳

실행 (저장소 루트에서. 표준 라이브러리만 쓴다):
    python tools/multi_plant/validate.py --data-root <자료 폴더> [--json <결과 파일>]
오류가 있으면 종료 코드 1 이다. 경고만 있으면 0 이다.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C  # noqa: E402


def summarize(loaded):
    plants = C.plant_ids(loaded["plants"])
    per_plant = {}
    for pid, rows in loaded["daily"].items():
        counts = {q: 0 for q in C.QUALITY}
        for r in rows:
            counts[r["quality"]] += 1
        per_plant[pid] = {"rows": len(rows), "first_date": rows[0]["date"].isoformat() if rows else None,
                          "last_date": rows[-1]["date"].isoformat() if rows else None, "quality_days": counts,
                          "hourly_days": len(loaded["hourly"].get(pid, {}))}
    errors = C.errors_of(loaded["issues"])
    return {
        "schema_version": C.SCHEMA_VERSION,
        "plants_registered": plants,
        "portfolios": sorted({m["portfolio_id"] for m in loaded["members"]}),
        "generation": per_plant,
        "errors": len(errors),
        "warnings": len(loaded["issues"]) - len(errors),
        "issues": loaded["issues"],
    }


def main():
    C.use_utf8_output()
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--data-root", type=Path, required=True)
    p.add_argument("--json", type=Path, help="결과를 JSON 으로도 쓴다")
    a = p.parse_args()

    report = summarize(C.load_root(a.data_root))
    print(f"등록된 발전소 {len(report['plants_registered'])}곳, 포트폴리오 {len(report['portfolios'])}개, 실적이 있는 발전소 {len(report['generation'])}곳")
    for pid, g in report["generation"].items():
        q = g["quality_days"]
        print(f"  {pid}: {g['first_date']} ~ {g['last_date']}, {g['rows']}일 "
              f"(ok {q['ok']}, zero_day {q['zero_day']}, partial {q['partial']}, mismatch {q['mismatch']}, missing {q['missing']}), 시간대별 {g['hourly_days']}일")
    for i in report["issues"]:
        print(f"  [{'오류' if i['level'] == 'error' else '경고'}] {i['code']}  {i['where']}  {i['message']}")
    print(f"오류 {report['errors']}건, 경고 {report['warnings']}건")
    if a.json:
        a.json.parent.mkdir(parents=True, exist_ok=True)
        a.json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    sys.exit(1 if report["errors"] else 0)


if __name__ == "__main__":
    main()
