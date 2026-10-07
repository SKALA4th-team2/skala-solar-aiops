"""Chronological hourly LSTM evaluation, latest-data refit and native MLflow release."""
import os
os.environ.setdefault('TF_ENABLE_ONEDNN_OPTS','0');os.environ.setdefault('TF_CPP_MIN_LOG_LEVEL','3');os.environ.setdefault('MLFLOW_DISABLE_AGENT_HINT','1')
os.environ['SOLAR_MODEL_CONTRACT']='solar_hourly_24_jma_day2_v1'
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
os.environ.setdefault('SOLAR_STATE_DIR',str(ROOT/'project/data/runtime-hourly'))
import tensorflow as tf
tf.config.threading.set_intra_op_parallelism_threads(2);tf.config.threading.set_inter_op_parallelism_threads(1)
import argparse,json,pickle,sys,subprocess,time
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor,as_completed
import numpy as np
import pandas as pd
sys.path.insert(0,str(ROOT/'project'))
from serving_app import runtime as rt,registry
from serving_app.hourly.model import features,build_model,FEATURES,CONTRACT
EVIDENCE=Path(os.getenv('HOURLY_EVIDENCE_DIR',str(ROOT/'docs/proposal/evidence/hourly_20261007')))

@contextmanager
def release_lock():
    for attempt in range(300):
        lock=rt.lock()
        try:lock.__enter__();break
        except RuntimeError:
            if attempt==299:raise
            time.sleep(1)
    try:yield
    finally:lock.__exit__(None,None,None)

def samples(entry):
    frame=pd.read_csv(ROOT/entry['hourly_file']);frame['timestamp']=pd.to_datetime(frame.timestamp);frame=frame.set_index('timestamp')
    groups={str(day.date()):g.reset_index().assign(timestamp=lambda d:d.timestamp.map(lambda t:t.isoformat())).to_dict('records') for day,g in frame.groupby(frame.index.normalize())}
    dates=[];xx=[];yy=[];forecasts=[];histories=[]
    for day,rows in groups.items():
        previous=str((pd.Timestamp(day)-pd.Timedelta(days=1)).date())
        if previous not in groups or len(rows)!=24 or len(groups[previous])!=24:continue
        dates.append(day);xx.append(features(groups[previous],rows,entry['capacity_kw']));yy.append([r['generation_kwh'] for r in rows]);forecasts.append(rows);histories.append(groups[previous])
    return np.asarray(xx),np.asarray(yy),np.array(dates),histories,forecasts

def metrics(y,p,capacity,daylight):
    e=p-y;day=e[daylight];return dict(n_hours=int(y.size),n_days=int(len(y)),rmse_kwh=float(np.sqrt(np.mean(e**2))),mae_kwh=float(np.mean(abs(e))),bias_pct=float(100*e.sum()/y.sum()),capacity_nrmse_pct=float(100*np.sqrt(np.mean(e**2))/capacity),daylight_rmse_kwh=float(np.sqrt(np.mean(day**2))))

def train(entry):
    pid=entry['plant_id'];dest=EVIDENCE/'plants'/pid;dest.mkdir(parents=True,exist_ok=True)
    if (dest/'result.json').exists():return
    x,y,dates,histories,forecasts=samples(entry);capacity=entry['capacity_kw']
    tr=np.flatnonzero(dates<'2024-07-01');va=np.flatnonzero((dates>='2024-07-01')&(dates<'2025-01-01'));te=np.flatnonzero((dates>='2025-01-01')&(dates<'2026-01-01'))
    radiation=x[:,:,1]*1000;coef=float(np.sum(radiation[tr]*y[tr])/np.sum(radiation[tr]**2));normalized_coef=coef*1000/capacity
    scaler=dict(contract=CONTRACT,capacity_kw=capacity,features=FEATURES,normalization='fixed physical scales; no refit',radiation_coefficient=coef)
    with (dest/'scaler.pkl').open('wb') as f:pickle.dump(scaler,f)
    def fit(indices,epochs,validation=None):
        tf.keras.backend.clear_session();tf.keras.utils.set_random_seed(42);m=build_model(normalized_coef)
        callbacks=[tf.keras.callbacks.EarlyStopping(monitor='val_loss',patience=5,restore_best_weights=True)] if validation is not None else []
        history=m.fit(x[indices],(y[indices]/capacity)[:,:,None],validation_data=(x[validation],(y[validation]/capacity)[:,:,None]) if validation is not None else None,epochs=epochs,batch_size=64,shuffle=False,verbose=0,callbacks=callbacks).history
        return m,history
    model,history=fit(tr,25,va);epochs=int(np.argmin(history['val_loss'])+1);rt.write(dest/'validation_history.json',history)
    model,_=fit(np.r_[tr,va],epochs)
    pred=np.clip(model(x[te],training=False).numpy().reshape(-1,24)*capacity,0,capacity);pred[radiation[te]<=1]=0
    daylight=radiation[te]>=20
    scores=metrics(y[te],pred,capacity,daylight)
    persistence=metrics(y[te],x[te,:,0]*capacity,capacity,daylight)
    reference=np.clip(radiation[te]*coef,0,capacity);reference[radiation[te]<=1]=0
    reference_scores=metrics(y[te],reference,capacity,daylight)
    limit=min(.95*persistence['rmse_kwh'],1.05*reference_scores['rmse_kwh'])
    gate=dict(scores,limit_kwh=limit,passed=len(te)>=180 and scores['rmse_kwh']<=limit and abs(scores['bias_pct'])<=15 and scores['daylight_rmse_kwh']<=1.05*reference_scores['daylight_rmse_kwh'],policy='hourly-v1: n>=180days; RMSE<=.95 lag24 and <=1.05 radiation; abs bias<=15; daylight<=1.05 radiation')
    model.save(dest/'evaluation.keras')
    pd.DataFrame(dict(timestamp=[r['timestamp'] for i in te for r in forecasts[i]],actual_kwh=y[te].ravel(),predicted_kwh=pred.ravel(),lag24_kwh=(x[te,:,0]*capacity).ravel(),reference_kwh=reference.ravel())).to_csv(dest/'test_predictions.csv',index=False)
    rt.write(dest/'evaluation.json',dict(gate=gate,persistence=persistence,radiation_reference=reference_scores,epochs=epochs,train_end='2024-12-31',test_start=str(dates[te[0]]),test_end=str(dates[te[-1]])))
    # Deployment weights use all available data; held-out scores belong to evaluation.keras.
    model,_=fit(np.arange(len(dates)),epochs)
    metadata=dict(plant_id=pid,train_end=str(dates[-1])+'T23:00:00+09:00',trained_through=str(dates[-1]),hourly_source=entry['hourly_file'],source_sha256=entry['hourly_sha256'],capacity_kw=capacity,features=FEATURES,radiation_coefficient=coef,forecast_lead_hours=48,interval='start timestamp [t,t+1h), Asia/Seoul',evaluation=gate,evaluation_model='evaluation.keras through 2024-12-31',release_uses_all_valid_data=True,publication_cutoff_verified=False,regional_weather_proxy=True)
    rt.write(dest/'sample.json',dict(plant_id=pid,history=[{k:r[k] for k in ['timestamp','generation_kwh']} for r in histories[-1]],forecast=[{k:v for k,v in r.items() if k!='generation_kwh'} for r in forecasts[-1]]))
    with release_lock():
        result=registry.register(model,dest/'scaler.pkl',metadata,x[-1:],gate=gate,kind='hourly-initial')
        if gate['passed']:registry.activate(pid,result['version']);result['promoted']=True
        rt.write(dest/'result.json',dict(result,epochs=epochs,metrics=scores))
    print('COMPLETE',pid,'epochs',epochs,'gate',gate['passed'],'rmse',scores['rmse_kwh'],'limit',limit,flush=True)

def main():
    a=argparse.ArgumentParser();a.add_argument('--plant');a.add_argument('--workers',type=int,default=2);args=a.parse_args()
    entries=rt.read(ROOT/'datasets/hourly/screening.json')['included'];EVIDENCE.mkdir(parents=True,exist_ok=True)
    if not (rt.root()/'catalog.json').exists():rt.write(rt.root()/'catalog.json',dict(plants={p['plant_id']:p for p in entries},portfolios={},contract=CONTRACT))
    if args.plant:train(next(p for p in entries if p['plant_id']==args.plant));return
    def run(entry):
        pid=entry['plant_id']
        with (EVIDENCE/f'{pid}.log').open('w',encoding='utf-8') as out:result=subprocess.run([sys.executable,'-X','utf8','-B',str(Path(__file__).resolve()),'--plant',pid],cwd=ROOT/'project',stdout=out,stderr=subprocess.STDOUT)
        return pid,result.returncode
    failed=[]
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for future in as_completed([pool.submit(run,p) for p in entries]):
            result=future.result();print('PROCESS',result,flush=True)
            if result[1]:failed.append(result)
    if failed:raise SystemExit('Training processes failed: '+str(failed))
if __name__=='__main__':main()
