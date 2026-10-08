"""Single persistent worker. Start with python -m serving_app.monitoring.worker."""
import os
os.environ.setdefault('TF_ENABLE_ONEDNN_OPTS','0')
os.environ.setdefault('TF_CPP_MIN_LOG_LEVEL','3')
import tensorflow as tf
tf.config.threading.set_intra_op_parallelism_threads(2)
tf.config.threading.set_inter_op_parallelism_threads(1)
import argparse,json,logging,time
from serving_app import runtime as rt

def recover():
    from serving_app.registry import reconcile
    reconcile()
    with rt.db() as conn:
        conn.execute("UPDATE jobs SET status=CASE WHEN attempts<2 THEN 'queued' ELSE 'failed' END, result=?,updated_at=? WHERE status='running'",
                     (json.dumps({'reason':'worker_interrupted'}),rt.now()))

def work_one():
    with rt.lock():
        with rt.db() as conn:
            conn.execute('BEGIN IMMEDIATE')
            row=conn.execute("SELECT * FROM jobs WHERE status='queued' ORDER BY created_at LIMIT 1").fetchone()
            if row is None:return False
            job=dict(row)
            conn.execute("UPDATE jobs SET status='running', attempts=attempts+1,updated_at=? WHERE id=?",(rt.now(),job['id']))
        payload=json.loads(job['payload']);pid=job['plant_id']
        logging.getLogger('aiops').info('[INFO] retrain triggered (window=last_21_days) plant=%s job=%s',pid,job['id'])
        try:
            if rt.digest(payload['rows'])!=payload['data_sha256']:raise ValueError('Job payload hash mismatch')
            from serving_app.train_and_register import fine_tune
            with rt.db() as conn:
                signals={r['plant_id']:json.loads(r['payload']) for r in conn.execute('SELECT plant_id,payload FROM monitoring WHERE end_date=?',(job['end_date'],))}
            members=rt.catalog()['plants']
            capacity=sum(p.get('capacity_kw') or 0 for p in members.values())
            affected=sum((members[p].get('capacity_kw') or 0) for p,s in signals.items() if s['status'] in ['drift_alerted','retrain_triggered','facility_check'])
            if capacity and affected>capacity*.5:
                result=dict(promoted=False,reason='shared_weather_or_data_issue',skipped=True)
            else:result=fine_tune(payload['rows'],pid,payload['base_version'])
            status='skipped' if result.get('skipped') else 'succeeded'
            message='[OK] new_rmse=%s - production promoted: %s v%s' if result.get('promoted') else '[WARN] gate failed - production kept (new_rmse=%s, model=%s, version=%s)'
            logging.getLogger('aiops').info(message,result.get('rmse'),rt.model_name(pid),result.get('version',payload['base_version']))
        except Exception as exc:
            logging.getLogger('aiops').exception('Training failed plant=%s job=%s',pid,job['id'])
            result={'reason':type(exc).__name__,'error':str(exc)};status='failed'
        with rt.db() as conn:
            conn.execute('UPDATE jobs SET status=?,result=?,updated_at=? WHERE id=?',(status,json.dumps(result),rt.now(),job['id']))
        rt.event(pid,'job_finished',dict(job_id=job['id'],status=status,**result))
        from serving_app.model_loader import clear_cache
        clear_cache();tf.keras.backend.clear_session()
        return True

def scan_uploads():
    from data.storage import latest_upload
    from serving_app.routers.data import validate_csv
    from serving_app.model_loader import get_model
    from serving_app.monitoring.retrain_trigger import evaluate
    for pid in rt.catalog()['plants']:
        try:
            path=latest_upload(plant_id=pid)
            from pathlib import Path
            parsed=validate_csv(Path(path).read_text(encoding='utf-8-sig'),pid)[-41:]
            with rt.db() as conn:
                old=conn.execute('SELECT end_date FROM monitoring WHERE plant_id=?',(pid,)).fetchone()
            if old and parsed[-1]['Date']<=old['end_date']:continue
            rows=[dict(date=r['Date'],close=r['Close'],volume=r['Volume'],expected=r.get('Expected')) for r in parsed]
            model=get_model(pid);values=model.predict_many([rows[i:i+20] for i in range(21)])
            records=[dict(date=r['date'],actual=r['close'],expected=r.get('expected'),predicted=v) for r,v in zip(rows[20:],values)]
            evaluate(plant_id=pid,rows=rows,predictions=records,model_version=model.version)
        except FileNotFoundError:continue
        except Exception as exc:rt.event(pid,'upload_monitor_failed',{'reason':str(exc)})

def main():
    p=argparse.ArgumentParser();p.add_argument('--once',action='store_true');p.add_argument('--no-scan',action='store_true');a=p.parse_args()
    (rt.PROJECT/'logs').mkdir(exist_ok=True)
    logging.basicConfig(level=logging.INFO,handlers=[logging.FileHandler(rt.PROJECT/'logs/aiops.log',encoding='utf-8'),logging.StreamHandler()])
    with rt.lock('worker'):
        with rt.lock():recover()
        last_scan=0
        while True:
            with rt.db() as conn:conn.execute('INSERT OR REPLACE INTO heartbeat VALUES(?,?,?)',('worker',rt.now(),os.getpid()))
            if not a.no_scan and time.monotonic()-last_scan>=30:
                scan_uploads();last_scan=time.monotonic()
            try:worked=work_one()
            except RuntimeError as exc:
                if str(exc)!='Another worker or deployment operation is running':raise
                # An API rollback/baseline change can briefly own the same lock.
                # Keep serving and leave queued work for the next poll.
                worked=False
            if a.once:return
            if not worked:time.sleep(2)
if __name__=='__main__':main()

