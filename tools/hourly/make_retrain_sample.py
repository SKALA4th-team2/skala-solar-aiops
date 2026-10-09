"""Generate synthetic hourly drift data for a single-plant lifecycle test."""
import argparse
import csv
from datetime import datetime, timedelta
import io
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'project'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plant', default='hadong-sewage')
    parser.add_argument('--out', type=Path, default=ROOT / 'datasets/fixtures/retrain/hadong-synthetic-drift.csv')
    args = parser.parse_args()
    os.environ.update(SOLAR_STATE_DIR=str(ROOT / 'project/data/runtime-hourly'),
        SOLAR_MODEL_CONTRACT='solar_hourly_24_jma_day2_v1', SOLAR_MODEL_STORE='disabled',
        TF_CPP_MIN_LOG_LEVEL='3', TF_ENABLE_ONEDNN_OPTS='0')
    from serving_app import runtime as rt
    from serving_app.hourly.data import COLUMNS, parse_csv
    from serving_app.hourly.model import load_bundle
    from serving_app.hourly.policy import inspect
    version = str(rt.current(args.plant)['version'])
    model = load_bundle(args.plant, version)
    source = rt.root() / 'history' / f'{args.plant}.csv'
    with source.open(encoding='utf-8-sig') as stream:
        rows = list(csv.DictReader(stream))[-696:]
    if len(rows) != 696:
        raise ValueError('Expected 29 complete history days')
    source_range = [rows[0]['timestamp'], rows[-1]['timestamp']]
    cutoff = datetime.fromisoformat(model.manifest['train_end'])
    previous_upload = rt.root() / 'uploads' / args.plant / 'latest.json'
    if previous_upload.exists():
        cutoff = max(cutoff, datetime.fromisoformat(rt.read(previous_upload)['rows'][-1]['timestamp']))
    start = cutoff.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    for i, row in enumerate(rows):
        row['timestamp'] = (start + timedelta(hours=i)).isoformat()
        reference = min(model.scaler['capacity_kw'], float(row['shortwave_radiation']) * model.scaler['radiation_coefficient'])
        row['generation_kwh'] = reference * .5
    raw = io.StringIO(newline='')
    writer = csv.DictWriter(raw, fieldnames=COLUMNS, lineterminator='\n')
    writer.writeheader(); writer.writerows(rows)
    validated = parse_csv(raw.getvalue(), args.plant)
    report = inspect(validated, model)[0]
    if report['state'] != 'drift':
        raise ValueError('This model did not detect drift; sample was not saved')
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(raw.getvalue(), encoding='utf-8', newline='')
    rt.write(args.out.with_suffix('.json'), dict(plant_id=args.plant, model_version=version,
        synthetic=True, scope='AIOps functionality only; not forecast performance',
        rows=len(validated), start=validated[0]['timestamp'], end=validated[-1]['timestamp'],
        source=source.relative_to(ROOT).as_posix(), source_sha256=rt.sha(source), source_range=source_range,
        transformation='Shift timestamps after train_end and latest upload; generation = 0.5 * capped radiation reference',
        monitor=report, csv_sha256=rt.sha(args.out)))
    print(f'Synthetic sample generated: {args.out}; rows={len(validated)}; drift confirmed')


if __name__ == '__main__': main()
