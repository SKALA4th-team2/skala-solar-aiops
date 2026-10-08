"""Place a chosen model/scaler pair at the current app's existing local paths.

Does not start/restart a server, clear a live cache, or promote an MLflow model.
"""
import argparse
import json
from pathlib import Path
import shutil
import hashlib
from datetime import datetime, timezone
ROOT=Path(__file__).resolve().parents[2]


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--out',default='docs/proposal/evidence/forecast_models_20261007')
    ap.add_argument('--plant',default='15043409_u1');ap.add_argument('--role',choices=['evaluation','release'],default='evaluation');args=ap.parse_args()
    out=ROOT/args.out;source=out/'plants'/args.plant/args.role
    assert source.resolve().is_relative_to((out/'plants').resolve())
    hashes=json.loads((source/'bundle_hashes.json').read_text(encoding='utf-8'))
    for filename,digest in hashes.items():assert hashlib.sha256((source/filename).read_bytes()).hexdigest()==digest
    destination=ROOT/'project/serving_app/models';destination.mkdir(exist_ok=True)
    backup=out/'local_install_backup'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')
    mapping={'model.keras':'haic_v1.keras','scaler.pkl':'scaler.pkl','metadata.json':'forecast_manifest.json'}
    for old,new in mapping.items():
        if (destination/new).exists():
            backup.mkdir(parents=True,exist_ok=True);shutil.copy2(destination/new,backup/new)
        shutil.copy2(source/old,destination/new)
        assert hashlib.sha256((source/old).read_bytes()).hexdigest()==hashlib.sha256((destination/new).read_bytes()).hexdigest()
    receipt={'plant_id':args.plant,'role':args.role,'source':str(source),'destination':str(destination),
             'files':mapping,'installed_utc':datetime.now(timezone.utc).isoformat(),
             'server_restarted':False,'production_promoted':False}
    (out/'local_install.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(receipt,ensure_ascii=False))


if __name__=='__main__':main()
