"""Plan scoped deletion of ten user-excluded plants; update registries with --apply.

File deletion is performed separately from the emitted, absolute path manifest.
Historical aggregate scores and shared source/weather files are retained.
"""
import argparse,json,os,re,sqlite3,sys
from pathlib import Path
from urllib.parse import unquote,urlparse
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'project'))
from serving_app import runtime as rt
IDS={'15043388_u1','15043391_u4','15043396_u1','15043401_u1','15043408_u1','15109998_u1','15043386_u1','15043386_u2','15043389_u1','15043407_u5'}
PUBLIC={s.replace('_','-') for s in IDS}
SINGLE={s.split('_')[0] for s in IDS if s not in {'15043391_u4','15043407_u5'}}
EVIDENCE=ROOT/'docs/proposal/evidence/aiops_backend_20261007'

def targeted(name):
    return any(re.search(r'(?<!\d)'+re.escape(s)+r'(?!\d)',name) for s in IDS|PUBLIC|SINGLE)

def filter_entries(value):
    if isinstance(value,list):return [filter_entries(v) for v in value if not (isinstance(v,dict) and v.get('plant_id') in IDS|PUBLIC)]
    if isinstance(value,dict):return {k:filter_entries(v) for k,v in value.items() if k not in IDS|PUBLIC}
    return value

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--apply',action='store_true');args=ap.parse_args()
    candidates=set();databases=[];catalogs=[];indexes=[]
    for base in [ROOT/'datasets',ROOT/'docs/proposal/evidence',ROOT/'project/data',ROOT/'project/serving_app/models']:
        for current,dirs,files in os.walk(base):
            dirs[:]=[d for d in dirs if d not in ['.git','__pycache__','github_snapshot']]
            for d in list(dirs):
                if targeted(d):candidates.add(Path(current)/d);dirs.remove(d)
            for name in files:
                p=Path(current)/name
                if targeted(name):candidates.add(p)
                if name=='mlflow.db':databases.append(p)
                if name=='catalog.json':catalogs.append(p)
                if name in ['screening.json','registry_index.json','plant_mapping.json','bootstrap.json']:indexes.append(p)
    registries=[]
    for db in databases:
        with sqlite3.connect(db) as c:
            tables={r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if 'registered_models' not in tables:continue
            names=[r[0] for r in c.execute('SELECT name FROM registered_models') if targeted(r[0])]
            runids=[r[0] for r in c.execute("SELECT run_uuid FROM tags WHERE key='plant_id' AND value IN ("+','.join('?' for _ in IDS|PUBLIC)+')',tuple(IDS|PUBLIC))]
            logged=[]
            for runid in runids:
                uri=c.execute('SELECT artifact_uri FROM runs WHERE run_uuid=?',(runid,)).fetchone()
                uris=[uri[0]] if uri else []
                if 'logged_models' in tables:
                    for mid,loc in c.execute('SELECT model_id,artifact_location FROM logged_models WHERE source_run_id=?',(runid,)):
                        logged.append(mid);uris.append(loc)
                for uri in uris:
                    if uri.startswith('file:'):
                        path=unquote(urlparse(uri).path)
                        if re.match(r'^/[A-Za-z]:',path):path=path[1:]
                        p=Path(path)
                        if p.exists():candidates.add(p)
            if names or runids:registries.append(dict(database=str(db),models=names,runs=runids,logged_models=logged))
    verified=[]
    for p in sorted(candidates):
        resolved=p.resolve(strict=True)
        if not resolved.is_relative_to(ROOT) or resolved==ROOT or p.is_symlink():raise ValueError(f'Unsafe deletion target: {p}')
        verified.append(str(resolved))
    plan=dict(plant_ids=sorted(PUBLIC),paths=verified,registries=registries,shared_source_preserved='15043391.csv and 15043407.csv: approved sibling units remain',approved_models_before=33)
    rt.write(EVIDENCE/'removal-plan.json',plan)
    if not args.apply:
        print('PLAN',len(verified),'paths',sum(len(r['models']) for r in registries),'registered models');return
    with rt.lock():
        import subprocess
        with sqlite3.connect(rt.root()/'mlflow.db') as db:current_schema=db.execute('SELECT version_num FROM alembic_version').fetchone()[0]
        code="""import json,sys
from pathlib import Path
from mlflow import MlflowClient
r=json.loads(sys.argv[1]);c=MlflowClient(tracking_uri='sqlite:///'+Path(r['database']).as_posix())
for name in r['models']:c.delete_registered_model(name)
for mid in r['logged_models']:c.delete_logged_model(mid)
for runid in r['runs']:c.delete_run(runid)
"""
        for reg in registries:
            with sqlite3.connect(reg['database']) as db:schema=db.execute('SELECT version_num FROM alembic_version').fetchone()[0]
            python=sys.executable if schema==current_schema else str(ROOT/'project/.venv-models-20261007/Scripts/python.exe')
            subprocess.run([python,'-X','utf8','-c',code,json.dumps(reg)],check=True)
        for p in catalogs:
            content=rt.read(p)
            if 'plants' not in content:continue
            content=filter_entries(content)
            for portfolio in content.get('portfolios',{}).values():
                old=portfolio['members'];portfolio['members']=[pid for pid in old if pid not in PUBLIC]
                if old!=portfolio['members']:portfolio['version']=portfolio['version']+'-approved33'
            if isinstance(content['plants'],list) and 'summary' in content:
                plants=content['plants'];content['summary'].update(units=len(plants),daily_sources=len({p['source_id'] for p in plants}),upload_ready_units=sum(bool(p['uploads']) for p in plants),upload_files=sum(len(p['uploads']) for p in plants),upload_rows=sum(u['rows'] for p in plants for u in p['uploads']))
            rt.write(p,content)
        for p in indexes:rt.write(p,filter_entries(rt.read(p)))
        with rt.db() as c:
            for pid in PUBLIC:
                for table in ['jobs','monitoring','windows']:c.execute(f'DELETE FROM {table} WHERE plant_id=?',(pid,))
        import csv,io
        for rel in ['datasets/multi_plant/catalog.csv','datasets/plant_forecasts/coverage.csv']:
            p=ROOT/rel
            with p.open(encoding='utf-8-sig',newline='') as f:reader=csv.DictReader(f);fields=reader.fieldnames;rows=[r for r in reader if r.get('plant_id') not in IDS]
            with p.open('w',encoding='utf-8',newline='') as f:writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader();writer.writerows(rows)
    rt.write(EVIDENCE/'removal-registry.json',dict(completed=True,plant_ids=sorted(PUBLIC),registered_models_removed=sum(len(r['models']) for r in registries),runs_deleted=sum(len(r['runs']) for r in registries)))
    print('REGISTRIES UPDATED; delete only removal-plan.json paths next')
if __name__=='__main__':main()
