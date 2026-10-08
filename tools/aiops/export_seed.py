"""Export approved native bundles without platform-specific SQLite artifact paths."""
from pathlib import Path
import shutil,sys
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'project'))
from serving_app import runtime as rt

def main():
    seed=rt.PROJECT/'serving_app/models/runtime-seed'
    with rt.lock():
        rt.write(seed/'catalog.json',rt.catalog());count=0
        for pid in rt.catalog()['plants']:
            try:pointer=rt.current(pid)
            except FileNotFoundError:continue
            source=rt.version_dir(pid,pointer['version']);meta=rt.read(source/'manifest.json')
            dest=seed/'models'/pid;dest.mkdir(parents=True,exist_ok=True)
            for filename in ['model.keras','scaler.pkl']:
                if rt.sha(source/filename)!=meta['hashes'][filename]:raise ValueError('Bundle integrity failure')
                shutil.copy2(source/filename,dest/filename)
            rt.write(dest/'manifest.json',meta);count+=1
        rt.write(seed/'export.json',dict(approved_models=count,created_at=rt.now(),contains_mlflow_database=False))
    print('PORTABLE SEED EXPORTED',count)
if __name__=='__main__':main()
