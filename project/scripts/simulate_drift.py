"""실제 CSV의 연속 41일로 태양광 배치를 만든다. 모델·감시 정책은 서버 담당이다.

project/에서 실행:
  python scripts/simulate_drift.py --end-date 2025-07-31 --target local
  python scripts/simulate_drift.py --end-date 2025-07-31 --export-json /tmp/solar-batches.json
두 번째 명령의 JSON을 대시보드에서 선택할 수 있다. 하락 배치는 발전량에만 0.86을 곱한다.
"""
import argparse
import csv
import json
from pathlib import Path
import sys

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from data.storage import latest_upload
from serving_app.routers.data import validate_csv
from serving_app.schemas import BatchTestRequest, parse_calendar_date

TARGETS = {'local': 'http://localhost:8077', 'container': 'http://localhost:8099'}
DATASETS = Path(__file__).resolve().parents[2] / 'datasets'
BATCH_N = 41
DRIFT_FACTOR = 0.86


def build_batch(csv_path: str | Path, expected_path: str | Path | None, end_date: str | None = None) -> dict:
    rows = validate_csv(Path(csv_path).read_text(encoding='utf-8-sig'))
    if end_date:
        end = parse_calendar_date(end_date).isoformat()
        if not any(row['Date'] == end for row in rows):
            raise ValueError('지정한 끝 날짜가 입력 CSV에 없습니다.')
        rows = [row for row in rows if row['Date'] <= end]
    rows = rows[-BATCH_N:]
    if len(rows) != BATCH_N:
        raise ValueError('선택한 끝 날짜까지 최소 41행이 필요합니다.')
    expected = {}
    if expected_path is not None:
        with Path(expected_path).open(encoding='utf-8-sig') as source:
            reader = csv.DictReader(source)
            if not {'date', 'pi_expected_kwh'}.issubset(reader.fieldnames or []):
                raise ValueError('감시 CSV에 date, pi_expected_kwh 열이 필요합니다.')
            for row in reader:
                day = parse_calendar_date(row['date']).isoformat()
                if day in expected:
                    raise ValueError('감시 CSV 날짜가 중복되었습니다.')
                expected[day] = float(row['pi_expected_kwh']) if row['pi_expected_kwh'].strip() else None
    return BatchTestRequest(
        dates=[row['Date'] for row in rows], prices=[row['Close'] for row in rows],
        volumes=[row['Volume'] for row in rows], expected=[expected.get(row['Date']) for row in rows],
    ).model_dump(mode='json')


def make_bundle(normal: dict) -> dict:
    drift = dict(normal, prices=[value * DRIFT_FACTOR for value in normal['prices']])
    return {'normal': normal, 'drift': BatchTestRequest.model_validate(drift).model_dump(mode='json')}


def send_batch(base_url: str, payload: dict, label: str) -> dict:
    response = requests.post(base_url + '/predict/batch-test', json=payload, timeout=(5, 120))
    response.raise_for_status()
    result = response.json()
    print(f"[{label}] drift_check = {result['drift_check']}")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description='태양광 CSV 기반 정상·14% 하락 배치')
    parser.add_argument('--target', choices=['local', 'container', 'both'], default='local')
    parser.add_argument('--scenario', choices=['normal','drift'], default='normal',help='서버 상태를 보존하므로 한 번에 한 시나리오만 보냅니다. 같은 날짜의 다른 자료는 409입니다.')
    parser.add_argument('--csv', type=Path, help='Date,Close,Volume CSV. 생략하면 최근 업로드, 없으면 태양광 예보 파일')
    parser.add_argument('--expected-csv', type=Path, default=DATASETS / 'hadong_daily_full.csv')
    parser.add_argument('--end-date', help='배치의 마지막 실제 날짜 YYYY-MM-DD. 생략하면 CSV 마지막 날짜')
    parser.add_argument('--export-json', type=Path, help='요청을 보내지 않고 대시보드용 normal/drift JSON 저장')
    args = parser.parse_args()
    csv_path = args.csv
    if csv_path is None:
        try:
            csv_path = Path(latest_upload())
        except FileNotFoundError:
            csv_path = DATASETS / 'hadong_upload_forecast_jma.csv'
    try:
        expected_path = args.expected_csv if args.expected_csv.exists() else None
        if expected_path is None:
            print('[info] 감시 CSV가 없어 expected는 모두 null입니다. 예측 입력에는 영향이 없습니다.')
        bundle = make_bundle(build_batch(csv_path, expected_path, args.end_date))
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    normal = bundle['normal']
    print(f"자료: {csv_path}; 날짜: {normal['dates'][0]} ~ {normal['dates'][-1]}; 사후 기대값 {sum(v is not None for v in normal['expected'])}/41일")
    if args.export_json:
        args.export_json.parent.mkdir(parents=True, exist_ok=True)
        args.export_json.write_text(json.dumps(bundle, ensure_ascii=False, indent=2) + '\n')
        print(f'대시보드용 배치 저장: {args.export_json}')
        return 0
    failed = False
    for target in (['local', 'container'] if args.target == 'both' else [args.target]):
        for label, payload in [(args.scenario,bundle[args.scenario])]:
            try:
                send_batch(TARGETS[target], payload, f'{target}/{label}')
            except requests.RequestException as exc:
                failed = True
                print(f'[{target}/{label}] 요청 실패: {exc}', file=sys.stderr)
    return int(failed)


if __name__ == '__main__':
    raise SystemExit(main())
