"""Solar warm-start training with chronological 16/5 split and fixed paired scaler."""
import os
os.environ.setdefault('TF_ENABLE_ONEDNN_OPTS','0')
os.environ.setdefault('TF_CPP_MIN_LOG_LEVEL','3')
from serving_app import runtime as rt
from serving_app.monitoring.policy import metrics,classify
FINE_TUNE_EPOCHS=10
FINE_TUNE_LR=1e-4
RMSE_GATE='per-plant relative baseline; no dollar threshold'

def fine_tune(rows,plant_id=rt.DEFAULT_PLANT,base_version=None):
    import tensorflow as tf
    import numpy as np
    from serving_app import registry
    from serving_app.model_loader import load_bundle
    from serving_app.schemas import BatchTestRequest
    request=BatchTestRequest(plant_id=plant_id,dates=[r['date'] for r in rows],prices=[r['close'] for r in rows],
                             volumes=[r['volume'] for r in rows],expected=[r.get('expected') for r in rows])
    if len(rows)!=41:raise ValueError('Fine tuning requires exactly 41 consecutive rows')
    current=rt.current(plant_id);version=str(base_version or current['version'])
    if str(current['version'])!=version:return dict(promoted=False,reason='stale_base_version',skipped=True)
    entry=rt.plant(plant_id);flags=classify(rows,entry['capacity_kw'])
    if any(f['outage'] or f['hold'] for f in flags):return dict(promoted=False,reason='facility_hold',skipped=True)
    if not all(f['valid'] for f in flags):return dict(promoted=False,reason='expected_values_missing',skipped=True)
    incumbent=load_bundle(plant_id,version)
    if rows[20]['date']<=incumbent.manifest['train_end']:
        return dict(promoted=False,reason='window_overlaps_model_training',skipped=True)
    scaler=incumbent.scaler
    x=np.array([[scaler.transform_point(r['close'],r['volume']) for r in rows[i:i+20]] for i in range(21)],dtype='float32')
    y=np.array([r['close'] for r in rows[20:]],dtype='float32')
    before=np.array(incumbent.predict_many([rows[i:i+20] for i in range(16,21)]))
    tf.keras.utils.set_random_seed(42)
    candidate=incumbent._keras_model
    candidate.compile(optimizer=tf.keras.optimizers.Adam(FINE_TUNE_LR),loss='mse')
    scaled_y=np.array([scaler.scale_close(float(v)) for v in y],dtype='float32')
    candidate.fit(x[:16],scaled_y[:16],epochs=FINE_TUNE_EPOCHS,batch_size=8,shuffle=False,verbose=0)
    after=np.maximum(candidate(x[16:],training=False).numpy().ravel()*(scaler.close_max-scaler.close_min)+scaler.close_min,0)
    scores=metrics(y[16:].tolist(),after.tolist());old=metrics(y[16:].tolist(),before.tolist())
    limit=incumbent.manifest['gate']['limit_kwh']
    gate=dict(scores,limit_kwh=limit,incumbent_rmse_kwh=old['rmse_kwh'],
              passed=scores['rmse_kwh']<=limit and scores['rmse_kwh']<=old['rmse_kwh'],policy='demo-5-day-plus-incumbent-v1',
              quality_guarantee=False)
    meta={k:v for k,v in incumbent.manifest.items() if k not in ['version','hashes','gate','run_id','created_at','model_name','contract']}
    meta.update(train_end=rows[35]['date'],parent_version=version,data_sha256=rt.digest(rows),
                fine_tune=dict(epochs=10,learning_rate=1e-4,training_targets=16,gate_targets=5,
                               gate_start=rows[36]['date'],gate_end=rows[-1]['date'],scaler_refit=False),
                baseline_update='preserved: current job has only 41 days, not a new 365-day baseline')
    result=registry.register(candidate,rt.version_dir(plant_id,version)/'scaler.pkl',meta,x[:1],gate=gate,kind='warm-start')
    if gate['passed']:
        registry.activate(plant_id,result['version'],expected_version=version)
        result['promoted']=True
    result.update(rmse=scores['rmse_kwh'],base_version=version)
    return result

def train_and_register(csv_path=None,rows=None,plant_id=rt.DEFAULT_PLANT):
    if rows is None:
        from data.features import load_rows
        from data.storage import latest_upload
        raw=load_rows(csv_path or latest_upload(plant_id=plant_id))
        rows=[dict(date=r['Date'],close=r['Close'],volume=r['Volume'],expected=r.get('Expected')) for r in raw]
    with rt.lock():return fine_tune(rows[-41:],plant_id)

if __name__=='__main__':
    import argparse,json
    p=argparse.ArgumentParser();p.add_argument('--plant-id',default=rt.DEFAULT_PLANT);p.add_argument('--csv')
    a=p.parse_args();print(json.dumps(train_and_register(a.csv,plant_id=a.plant_id),ensure_ascii=False))
