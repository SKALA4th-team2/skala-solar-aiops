"""Single durable hourly worker, immutable paired scaler and chronological deployment gate."""
import os
os.environ.setdefault('TF_ENABLE_ONEDNN_OPTS','0');os.environ.setdefault('TF_CPP_MIN_LOG_LEVEL','3')
import tensorflow as tf
tf.config.threading.set_intra_op_parallelism_threads(2);tf.config.threading.set_inter_op_parallelism_threads(1)
import json,time,traceback
import numpy as np
from serving_app import runtime as rt,registry,model_loader
from serving_app.hourly.data import arrays
from serving_app.hourly.policy import inspect

def execute(job):
    pid=job['plant_id'];payload=json.loads(job['payload']);rows=payload['rows'];model=model_loader.get_model(pid)
    if model.version!=payload['base_version']:return dict(promoted=False,reason='current_version_changed')
    if rows[24]['timestamp']<=model.manifest['train_end']:return dict(promoted=False,reason='training_period_overlap')
    if inspect(rows,model)[0]['state']=='held':return dict(promoted=False,reason='possible_outage')
    x,y,_=arrays(rows,model.scaler['capacity_kw']);capacity=model.scaler['capacity_kw']
    if len(x)!=28:raise ValueError('Expected 21 training days and 7 validation days')
    parent=rt.version_dir(pid,model.version)
    candidate=tf.keras.models.load_model(parent/'model.keras',compile=False)
    candidate.compile(optimizer=tf.keras.optimizers.Adam(.0005),loss='mse')
    tf.keras.utils.set_random_seed(42)
    candidate.fit(x[:21],(y[:21]/capacity)[:,:,None],epochs=5,batch_size=7,shuffle=False,verbose=0)
    predicted=np.clip(candidate(x[21:],training=False).numpy().reshape(-1,24)*capacity,0,capacity)
    predicted[x[21:,:,1]<=.001]=0
    incumbent=model.predict_x(x[21:]);rmse=float(np.sqrt(np.mean((predicted-y[21:])**2)))
    previous=float(np.sqrt(np.mean((incumbent-y[21:])**2)))
    limit=min(model.manifest['evaluation']['limit_kwh'],previous)
    gate=dict(passed=rmse<=limit,rmse_kwh=rmse,limit_kwh=limit,incumbent_rmse_kwh=previous,validation_hours=168,policy='hourly-retrain-v1: <= initial gate and same-window incumbent')
    metadata={k:v for k,v in model.manifest.items() if k not in ['version','hashes','gate','run_id','created_at','model_name']}
    # Validation labels remain held out of weights; future jobs may train on them.
    metadata.update(train_end=rows[527]['timestamp'],validated_through=rows[-1]['timestamp'],parent_version=model.version,job_id=job['id'],retrain_source_sha256=payload['data_sha256'])
    result=registry.register(candidate,parent/'scaler.pkl',metadata,x[-1:],gate=gate,kind='hourly-fine-tune')
    if gate['passed']:
        registry.activate(pid,result['version'],expected_version=model.version);result['promoted']=True
        model_loader.clear_cache()
    return result

def step():
    with rt.db() as conn:
        conn.execute('INSERT OR REPLACE INTO heartbeat VALUES(?,?,?)',('worker',rt.now(),os.getpid()))
        job=conn.execute("SELECT * FROM jobs WHERE kind='hourly_fine_tune' AND status='queued' ORDER BY created_at LIMIT 1").fetchone()
    if job is None:return False
    try:
        with rt.lock():
            with rt.db() as conn:conn.execute("UPDATE jobs SET status='running',attempts=attempts+1,updated_at=? WHERE id=?",(rt.now(),job['id']))
            try:result=execute(dict(job));status='succeeded' if result.get('promoted') else 'rejected'
            except Exception as exc:traceback.print_exc();result=dict(error=str(exc));status='failed'
            with rt.db() as conn:conn.execute('UPDATE jobs SET status=?,result=?,updated_at=? WHERE id=?',(status,json.dumps(result),rt.now(),job['id']))
            rt.event(job['plant_id'],'hourly_job_finished',dict(job_id=job['id'],status=status,result=result))
    except RuntimeError:return False
    return True

def recover():
    with rt.lock():
        registry.reconcile()
        with rt.db() as conn:
            conn.execute("UPDATE jobs SET status=CASE WHEN attempts<2 THEN 'queued' ELSE 'failed' END,updated_at=? WHERE status='running'",(rt.now(),))

def main():
    rt.configure_logging()
    with rt.lock('worker'):
        recover()
        while True:step();time.sleep(2)
if __name__=='__main__':main()
