"""Start one API and one durable training worker, and stop both together."""
import argparse,os,subprocess,sys,time
from pathlib import Path
PROJECT=Path(__file__).resolve().parents[1]
def main():
    p=argparse.ArgumentParser();p.add_argument('--host',default='127.0.0.1');p.add_argument('--port',type=int,default=8077);a=p.parse_args()
    os.chdir(PROJECT)
    os.environ.setdefault('TF_ENABLE_ONEDNN_OPTS','0');os.environ.setdefault('TF_CPP_MIN_LOG_LEVEL','3')
    os.environ.setdefault('PYTHONUTF8','1')
    os.environ.setdefault('SOLAR_MODEL_CONTRACT','solar_hourly_24_jma_day2_v1')
    hourly=os.environ['SOLAR_MODEL_CONTRACT']=='solar_hourly_24_jma_day2_v1'
    os.environ.setdefault('SOLAR_STATE_DIR',str(PROJECT/('data/runtime-hourly' if hourly else 'data/runtime')))
    state=Path(os.environ['SOLAR_STATE_DIR'])
    seed=PROJECT/('serving_app/models/hourly-seed' if hourly else 'serving_app/models/runtime-seed')
    incomplete_seed=(seed/'catalog.json').exists() and any(
        not (state/'models'/folder.name/'current.json').exists() for folder in (seed/'models').iterdir())
    if incomplete_seed:
        subprocess.run([sys.executable,'-X','utf8','scripts/seed_runtime.py'],check=True)
    if not (state/'catalog.json').exists():raise SystemExit('Generate hourly models: tools/hourly/prepare.py, train.py, finalize.py; or provide hourly-seed.')
    log_dir=Path(os.getenv('SOLAR_LOG_DIR',str(PROJECT/'logs')));log_dir.mkdir(parents=True,exist_ok=True)
    processes=[]
    try:
        for name,command in [('api',['-m','uvicorn','serving_app.hourly.app:app' if hourly else 'serving_app.main:app','--host',a.host,'--port',str(a.port),'--workers','1']),
                              ('worker',['-m','serving_app.hourly.worker' if hourly else 'serving_app.monitoring.worker'])]:
            with (log_dir/f'{name}-stdout.log').open('a',encoding='utf-8') as output:
                process=subprocess.Popen([sys.executable,'-X','utf8',*command],stdout=output,stderr=subprocess.STDOUT,
                    creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            processes.append(process)
        print(f'API http://{a.host}:{a.port}/docs ; worker running. Logs: {PROJECT / "logs"}',flush=True)
        while all(p.poll() is None for p in processes):time.sleep(1)
        raise SystemExit('A backend process stopped; inspect api-stdout.log / worker-stdout.log.')
    except KeyboardInterrupt:pass
    finally:
        for process in processes:
            if process.poll() is None:process.terminate()
        for process in processes:
            try:process.wait(timeout=15)
            except subprocess.TimeoutExpired:process.kill();process.wait()
if __name__=='__main__':main()

