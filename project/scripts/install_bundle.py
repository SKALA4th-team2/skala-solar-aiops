"""Validate every portable model bundle before installing, never extract arbitrary paths."""
import argparse,hashlib,json,zipfile
from pathlib import Path
def install(archive,project):
    project=Path(project).resolve();archive=Path(archive)
    expected=archive.with_suffix('.zip.manifest.json')
    if not expected.exists():expected=project.parent/'docs/submission/model-bundle.json'
    if expected.exists():
        meta=json.loads(expected.read_text(encoding='utf-8'))
        if hashlib.sha256(archive.read_bytes()).hexdigest()!=meta['sha256']:raise ValueError('Archive SHA256 mismatch')
    with zipfile.ZipFile(archive) as z:
        manifest=json.loads(z.read('seed-package.json'));names=z.namelist()
        if len(names)!=len(set(names)) or set(names)!=set(manifest['files'])|{'seed-package.json'}:raise ValueError('Unexpected archive entries')
        verified=[]
        for name,info in manifest['files'].items():
            target=(project/name).resolve()
            if not name.startswith('serving_app/models/hourly-seed/') or not target.is_relative_to(project/'serving_app/models/hourly-seed'):raise ValueError('Invalid bundle path')
            data=z.read(name)
            if len(data)!=info['bytes'] or hashlib.sha256(data).hexdigest()!=info['sha256']:raise ValueError('File hash mismatch: '+name)
            if target.exists() and target.read_bytes()!=data:raise ValueError('Existing seed differs; install into a clean checkout')
            verified.append((target,data))
        for target,data in verified:target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
    print('INSTALLED',manifest['plant_count'],'approved models; all hashes verified')
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('archive');p.add_argument('--project',type=Path,default=Path(__file__).resolve().parents[1]);a=p.parse_args();install(a.archive,a.project)
