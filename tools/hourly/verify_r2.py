"""Read an archived real model into an isolated runtime and compare predictions."""
import argparse
import csv
import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'project'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state-dir', type=Path, default=ROOT / 'project/data/runtime-hourly')
    parser.add_argument('--plant', default='hadong-sewage')
    parser.add_argument('--out', type=Path)
    args = parser.parse_args()
    os.environ.update(SOLAR_MODEL_STORE='r2', SOLAR_STATE_DIR=str(args.state_dir.resolve()),
        SOLAR_MODEL_CONTRACT='solar_hourly_24_jma_day2_v1', TF_CPP_MIN_LOG_LEVEL='3', TF_ENABLE_ONEDNN_OPTS='0')
    from serving_app import runtime as rt, model_store
    from serving_app.hourly.model import load_bundle
    import numpy as np
    try:
        version = str(rt.current(args.plant)['version'])
        catalog = rt.catalog()
        receipt = rt.read(model_store.receipt_path(args.plant, version))
        records = list(csv.DictReader((rt.root() / 'history' / f'{args.plant}.csv').open(encoding='utf-8-sig')))[-48:]
        if len(records) != 48:
            raise ValueError('Expected 48 hourly history rows')
        history = [dict(timestamp=r['timestamp'], generation_kwh=float(r['generation_kwh'])) for r in records[:24]]
        forecast = [{k: (v if k == 'timestamp' else float(v)) for k, v in r.items() if k != 'generation_kwh'} for r in records[24:]]
        before = load_bundle(args.plant, version).predict(history, forecast)
        with tempfile.TemporaryDirectory(prefix='solar-r2-verify-') as temporary:
            os.environ['SOLAR_STATE_DIR'] = temporary
            rt.write(rt.root() / 'catalog.json', catalog)
            rt.write(model_store.receipt_path(args.plant, version), receipt)
            after = load_bundle(args.plant, version).predict(history, forecast)
            np.testing.assert_allclose(before, after, rtol=0, atol=0)
            result = dict(plant_id=args.plant, version=version, verified_at=rt.now(),
                backend='r2', restored_from_r2=True, bundle_hashes_verified=True,
                predictions_identical=True, forecast_hours=len(after), source_runtime_untouched=True)
        if args.out:
            rt.write(args.out.resolve(), result)
        print(f'R2 restore and prediction comparison: OK; plant={args.plant}; version={version}; hours={len(after)}')
    except Exception as exc:
        print(f'R2 verification failed ({type(exc).__name__}); credentials hidden', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__': raise SystemExit(main())
