"""Package only approved portable seeds, with per-file and archive SHA256."""
from pathlib import Path
import hashlib,json,zipfile,subprocess
ROOT=Path(__file__).resolve().parents[2];PROJECT=ROOT/'project'
def sha(data):return hashlib.sha256(data).hexdigest()
def main():
    seed=PROJECT/'serving_app/models/hourly-seed';catalog=json.loads((seed/'catalog.json').read_text(encoding='utf-8'))
    files=[seed/'catalog.json',seed/'portfolio_quality.json']
    for pid in catalog['plants']:
        folder=seed/'models'/pid;manifest=json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
        assert manifest['gate']['passed'] and manifest['plant_id']==pid
        for name in ['model.keras','scaler.pkl']:
            assert sha((folder/name).read_bytes())==manifest['hashes'][name]
        files.extend(folder/name for name in ['model.keras','scaler.pkl','manifest.json'])
        files.append(seed/'history'/f'{pid}.csv')
    package=dict(contract=catalog['contract'],plant_count=len(catalog['plants']),files={p.relative_to(PROJECT).as_posix():dict(sha256=sha(p.read_bytes()),bytes=p.stat().st_size) for p in files})
    output=PROJECT/'submission/solar-hourly-seed.zip';output.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        z.writestr('seed-package.json',json.dumps(package,ensure_ascii=False,indent=2))
        for p in files:z.write(p,p.relative_to(PROJECT).as_posix())
    target=ROOT/'docs/submission/model-bundle.json';target.parent.mkdir(parents=True,exist_ok=True)
    metadata=dict(filename=output.name,sha256=sha(output.read_bytes()),bytes=output.stat().st_size,plant_count=len(catalog['plants']),contract=catalog['contract'],source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=PROJECT,text=True).strip())
    target.write_text(json.dumps(metadata,indent=2),encoding='utf-8')
    output.with_suffix('.zip.manifest.json').write_text(json.dumps(metadata,indent=2),encoding='utf-8')
    print('PACKAGED',len(catalog['plants']),'plants',output.stat().st_size,'bytes',sha(output.read_bytes()))
if __name__=='__main__':main()
