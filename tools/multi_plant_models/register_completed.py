"""During an active batch, register completed plants one at a time; stop on job failure."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out",default="docs/proposal/evidence/multi_plant_models_20261007")
    ap.add_argument("--timeout-minutes",type=int,default=120)
    args = ap.parse_args()
    out = ROOT/args.out
    admitted = {p["plant_id"] for p in read(out/"screening.json")["admitted"]}
    deadline = time.monotonic()+args.timeout_minutes*60
    while time.monotonic()<deadline:
        index = out/"registry_index.json"
        registered = read(index)["models"] if index.exists() else []
        done = {p for p in admitted if len([r for r in registered if r["plant_id"]==p and r["reload_passed"]])==5}
        if done==admitted:
            print("ALL REGISTERED",len(done),flush=True)
            return
        ready = {p.parent.name for p in (out/"plants").glob("*/result.json")}-done
        for pid in sorted(ready):
            with (out/f"register_{pid}.log").open("w",encoding="utf-8") as fp:
                subprocess.run([sys.executable,"-X","utf8","-B",str(Path(__file__).with_name("register.py")),
                                "--out",args.out,"--plant",pid],stdout=fp,stderr=subprocess.STDOUT,
                               check=True,cwd=ROOT/"project")
            print("REGISTERED PLANT",pid,flush=True)
        statusfile = out/"execution_status.json"
        if statusfile.exists():
            status = read(statusfile)
            if len(status)==len(admitted) and any(r["exit_code"] for r in status):
                raise SystemExit("Training had failed jobs; inspect logs before registry continuation")
        if not ready:
            time.sleep(10)
    raise SystemExit("Registration waiting timeout; trained artifacts remain available")


if __name__=="__main__":
    main()
