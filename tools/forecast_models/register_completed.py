"""Register finished jobs while the current foreground batch is running."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time
ROOT=Path(__file__).resolve().parents[2]


def read(path):return json.loads(path.read_text(encoding='utf-8'))


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--out',default='docs/proposal/evidence/forecast_models_20261007');args=ap.parse_args()
    out=ROOT/args.out;plants={p['plant_id'] for p in read(out/'screening.json')['admitted']}
    deadline=time.monotonic()+3*3600
    while time.monotonic()<deadline:
        records=read(out/'registry_index.json')['models'] if (out/'registry_index.json').exists() else []
        done={p for p in plants if {(r['role']) for r in records if r['plant_id']==p}=={'evaluation','release'}}
        if done==plants:print('ALL REGISTERED',len(done),flush=True);return
        ready={p.parent.name for p in (out/'plants').glob('*/result.json')}-done
        for pid in sorted(ready):
            with (out/f'register_{pid}.log').open('w',encoding='utf-8') as fp:
                subprocess.run([sys.executable,'-X','utf8','-B',str(Path(__file__).with_name('register.py')),'--out',args.out,'--plant',pid],
                               cwd=ROOT/'project',stdout=fp,stderr=subprocess.STDOUT,check=True)
            print('REGISTERED PLANT',pid,flush=True)
        status=out/'execution_status.json'
        if status.exists():
            runs=read(status)
            if len(runs)==len(plants) and any(r['exit_code'] for r in runs):raise SystemExit('Training job failure; inspect logs')
        if not ready:time.sleep(10)
    raise SystemExit('Timed out waiting for training; saved files are preserved')


if __name__=='__main__':main()
