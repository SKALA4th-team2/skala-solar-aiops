"""Explicit archive management; local backend by default, no production switch."""
import argparse
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'project'))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['publish', 'restore'])
    parser.add_argument('--backend', choices=['local', 'r2'], default='local')
    parser.add_argument('--archive-dir', type=Path, default=ROOT / 'project/data/model-archive')
    parser.add_argument('--state-dir', type=Path, default=ROOT / 'project/data/runtime-hourly')
    parser.add_argument('--plant', required=True)
    parser.add_argument('--version', required=True)
    args = parser.parse_args()
    os.environ.update(SOLAR_MODEL_STORE=args.backend,
        SOLAR_MODEL_ARCHIVE_DIR=str(args.archive_dir.resolve()),
        SOLAR_STATE_DIR=str(args.state_dir.resolve()),
        SOLAR_MODEL_CONTRACT='solar_hourly_24_jma_day2_v1')
    from serving_app import runtime as rt, model_store, registry
    try:
        with rt.lock():
            if args.action == 'publish':
                registry.archive_bundle(args.plant, args.version)
            else:
                model_store.ensure_local(args.plant, args.version)
                model_store.validate(rt.version_dir(args.plant, args.version), args.plant, args.version)
        print(f'{args.action}: OK; backend={args.backend}; plant={args.plant}; version={args.version}')
    except Exception as exc:
        print(f'{args.action}: failed ({type(exc).__name__}); production version unchanged', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__': raise SystemExit(main())
