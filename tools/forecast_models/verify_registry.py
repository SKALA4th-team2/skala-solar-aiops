"""Verify actual registry aliases and paired extra files against local bundles."""
import os
os.environ.setdefault('MLFLOW_DISABLE_AGENT_HINT','1')
import argparse
import hashlib
import json
from pathlib import Path
import mlflow
from mlflow.tracking import MlflowClient
import yaml

ROOT=Path(__file__).resolve().parents[2]
def read(path):return json.loads(path.read_text(encoding='utf-8'))
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--out',default='docs/proposal/evidence/forecast_models_20261007')
    ap.add_argument('--partial',action='store_true')
    args=ap.parse_args();out=ROOT/args.out
    index=read(out/'registry_index.json');mlflow.set_tracking_uri(index['tracking_uri'])
    client=MlflowClient();checks=[]
    if not args.partial:
        assert len(index['models'])==2*len(read(out/'screening.json')['admitted'])
    for row in index['models']:
        version=client.get_model_version(row['registered_name'],str(row['version']))
        assert version.status=='READY' and version.run_id==row['run_id']
        assert version.current_stage!='Production'
        alias=client.get_model_version_by_alias(row['registered_name'],row['alias'])
        assert str(alias.version)==str(row['version'])
        assert version.tags['bundle_sha256']==row['bundle_sha256']
        directory=Path(mlflow.artifacts.download_artifacts(artifact_uri=row['model_uri']))
        spec=yaml.safe_load((directory/'MLmodel').read_text(encoding='utf-8'))
        assert spec['metadata']['input_contract']=='solar_next_day_jma_msm_day1_v1'
        assert spec['metadata']['input_space']=='scaled'
        assert spec['metadata']['plant_id']==row['plant_id'] and spec['metadata']['role']==row['role']
        assert spec['flavors']['tensorflow']['model_type']=='keras'
        source=out/'plants'/row['plant_id']/row['role']
        for file in ['scaler.pkl','scaler.json','metadata.json','bundle_hashes.json']:
            assert sha(directory/'extra_files'/file)==sha(source/file)
        assert (directory/'data/model.keras').is_file()
        checks.append(dict(plant_id=row['plant_id'],role=row['role'],version=str(version.version),passed=True))
    result=dict(passed=True,partial=args.partial,versions_checked=len(checks),checks=checks)
    suffix='_partial' if args.partial else ''
    (out/f'registry_audit{suffix}.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print('REGISTRY AUDIT PASSED',len(checks))


if __name__=='__main__':main()
