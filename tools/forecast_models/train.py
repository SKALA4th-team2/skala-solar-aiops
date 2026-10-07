"""Train forecast-native replay and latest-data model bundles for the reviewed API."""
import os
os.environ.setdefault("TF_ENABLE_ONEDNN_OPTS","0")
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL","2")
os.environ.setdefault("TF_NUM_INTRAOP_THREADS","2")
os.environ.setdefault("TF_NUM_INTEROP_THREADS","1")
os.environ.setdefault("OMP_NUM_THREADS","2")
os.environ.setdefault("MLFLOW_DISABLE_AGENT_HINT","1")
import argparse
import hashlib
import importlib.metadata
import json
import pickle
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
if "--plant" in sys.argv:
    import tensorflow as tf
import numpy as np
import pandas as pd
from bundle import CONTRACT, ForecastModel

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT/"datasets/plant_forecasts"
DEFAULT = "docs/proposal/evidence/forecast_models_20261007"


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def dump(path,value):
    path=Path(path); temp=path.with_name(path.name+".tmp")
    temp.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False,default=str),encoding="utf-8")
    os.replace(temp,path)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat()


def metrics(y,p):
    p=np.maximum(np.asarray(p),0)
    assert p.shape==y.shape and np.isfinite(p).all() and y.sum()>0
    return {"rmse_kwh":float(np.sqrt(np.mean((p-y)**2))),"mae_kwh":float(np.mean(np.abs(p-y))),
            "wape_pct":float(100*np.abs(p-y).sum()/y.sum()),"bias_pct":float(100*(p-y).sum()/y.sum()),"n":len(y)}


def make_data(path):
    df=pd.read_csv(path,parse_dates=["target_date"]).set_index("target_date").sort_index()
    assert df.index.is_unique
    # Reindex the calendar, retain invalid days as invalid; never join across holes.
    df=df.reindex(pd.date_range(df.index.min(),df.index.max()))
    c=df.gen_kwh.to_numpy()
    v=df.shortwave_radiation_previous_day1.shift(-1).to_numpy()
    gen_ok=np.isfinite(c)&(c>=0)
    if "generation_valid" in df:
        gen_ok &= df.generation_valid.eq(1).to_numpy()
    row_ok=gen_ok&np.isfinite(v)&(v>=0)&(v<=45)
    targets=np.array([t for t in range(20,len(df)) if gen_ok[t] and row_ok[t-20:t].all()],dtype=int)
    windows=np.array([np.column_stack([c[t-20:t],v[t-20:t]]) for t in targets])
    dates=df.index[targets]; y=c[targets]
    tr=np.flatnonzero(dates<pd.Timestamp("2024-07-01"))
    va=np.flatnonzero((dates>=pd.Timestamp("2024-07-01"))&(dates<pd.Timestamp("2025-01-01")))
    te=np.flatnonzero((dates>=pd.Timestamp("2025-01-01"))&(dates<pd.Timestamp("2026-01-01")))
    return df,targets,windows,y,dates,tr,va,te


def tabular(w,dates):
    cols=[f"{kind}_lag{20-i}" for i in range(20) for kind in ("generation","next_day_forecast")]
    x=pd.DataFrame(w.reshape(-1,40),columns=cols)
    c=w[:,:,0]
    x["mean7"]=c[:,-7:].mean(axis=1); x["std7"]=c[:,-7:].std(axis=1)
    x["mean20"]=c.mean(axis=1); x["std20"]=c.std(axis=1)
    denominator=w[:,-8:-1,1].sum(axis=1)
    rule=np.divide(c[:,-7:].sum(axis=1)*w[:,-1,1],denominator,
                   out=x.mean7.to_numpy().copy(),where=denominator>1e-6)
    x["rule_c"]=rule
    p=pd.DataFrame({"ds":dates,"irradiance":w[:,-1,1],"lag1":c[:,-1],"mean7":x.mean7,"rule_c":rule})
    bases={"Persistence":c[:,-1],"Mean7":x.mean7.to_numpy(),"RuleC":rule}
    return x,p,bases


def prepare(out):
    assert read(DATA/"verification.json")["passed"]
    assert read(DATA/"validation.json")["training_files"]==46
    catalog={p["plant_id"]:p for p in read(ROOT/"datasets/multi_plant/catalog.json")["plants"]}
    admitted=[]; excluded=[]
    for plant in read(DATA/"plant_mapping.json"):
        path=DATA/"training"/(plant["plant_id"]+".csv")
        if not path.exists() or plant["generation_status"] in ("review_only","raw_only_not_daily_training"):
            excluded.append(dict(plant,reason="upstream_quality_or_non_daily_generation")); continue
        df,t,w,y,dates,tr,va,te=make_data(path)
        counts={"train":len(tr),"validation":len(va),"test":len(te),"all":len(y)}
        if len(tr)<365 or len(va)<90 or len(te)<240 or np.mean(y==0)>.25:
            excluded.append(dict(plant,reason="insufficient_valid_calendar_windows_or_excess_zeros",counts=counts)); continue
        extra=catalog.get(plant["plant_id"],{})
        admitted.append(dict(plant,source_sha256=sha(path),counts=counts,
                             capacity_kw=extra.get("capacity_kw",55. if plant["plant_id"]=="15043409_u1" else None),
                             source=str(path.relative_to(ROOT))))
    # Start with the primary teaching/demo plant; others stay independent.
    admitted.sort(key=lambda p:(p["plant_id"]!="15043409_u1",p["plant_id"]))
    dump(out/"screening.json",{"created_utc":now(),"admitted":admitted,"excluded":excluded})
    dump(out/"protocol.json",{"created_utc":now(),"github_main":read(out/"github_review.json")["origin/main"]["commit"],
        "contract":CONTRACT,"input":"20 rows: generation[d] and JMA MSM previous_day1 radiation for d+1; target T uses volume[T-1]",
        "train":"valid targets before 2024-07-01","validation":"2024-07-01..2024-12-31","test":"2025-01-01..2025-12-31",
        "missing":"No interpolation/backfill; require 20 consecutive valid calendar rows and valid target generation. Target gen never enters window.",
        "models":"LSTM teaching 32-32-16-Dense16-1 (20,2); XGB six settings; Prophet three settings; simplex ensembles",
        "lstm":"seed42, Adam .001, 120 full validation epochs, restore best validation-loss weights; refit for chosen fixed epochs",
        "evaluation_bundle":"refit train+validation only, frozen through test, valid for historical 2025 replay",
        "release_bundle":"scratch refit all available valid targets through <=2026-02-28 with frozen settings; historical test metrics do not measure this refit",
        "scaler":"fit on training windows plus training labels only; separate paired scaler for each scratch model version; fine-tuning must reuse it",
        "selection":"Freeze model configs, epochs and ensemble weights before test; keep LSTM primary interface even if a comparator wins",
        "limitations":["Archive previous_day1 contains hourly leads, not a verified single issue before 20:00. publication_cutoff_verified=false",
                       "Regional coordinates are proxies, not exact individual plant sites","Daily energy only, not hourly settlement accuracy",
                       "One seed per site, one calendar test; publication availability and live field performance unverified",
                       "Current GitHub HTTP schema caps generation at1320kWh and has no plant ID; large-site HTTP integration remains separate",
                       "No Production promotion or automatic AIOps policy connection in this model-first task"]})
    sources=[Path(__file__).resolve(),Path(__file__).with_name("bundle.py").resolve()]
    hashes={str(p.relative_to(ROOT)):sha(p) for p in sources}
    for p in sources:
        target=out/"source_snapshot"/p.relative_to(ROOT);target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,target)
    dump(out/"training_code_hashes.json",hashes)
    dump(out/"environment.json",{"python":sys.version,"packages":{k:importlib.metadata.version(k) for k in
         ["numpy","pandas","tensorflow","keras","xgboost","scikit-learn","prophet","mlflow-skinny","protobuf"]}})
    print("ADMITTED",len(admitted),"EXCLUDED",len(excluded),flush=True)
    return admitted


def train(out,pid):
    from tensorflow import keras
    from xgboost import XGBRegressor
    from prophet import Prophet
    from prophet.serialize import model_to_json
    tf.config.threading.set_intra_op_parallelism_threads(2)
    tf.config.threading.set_inter_op_parallelism_threads(1)
    tf.config.experimental.enable_op_determinism()
    reviewed_project=out/"github_snapshot/main/project"
    sys.path.insert(0,str(reviewed_project))
    from serving_app.lstm_model import build_model
    from data.features import HAICScaler
    plant=next(p for p in read(out/"screening.json")["admitted"] if p["plant_id"]==pid)
    source=ROOT/plant["source"]; assert sha(source)==plant["source_sha256"]
    df,targets,w,y,dates,tr,va,te=make_data(source)
    x,p,bases=tabular(w,dates)
    dest=out/"plants"/pid;dest.mkdir(parents=True,exist_ok=True)
    val={k:v[va] for k,v in bases.items()}; test={k:v[te] for k,v in bases.items()}
    def split(ix):
        return {"n":len(ix),"first":str(dates[ix[0]].date()),"last":str(dates[ix[-1]].date())}
    splits={k:split(ix) for k,ix in [("train",tr),("validation",va),("test",te)]}
    pd.DataFrame({"date":dates,"split":["train" if d<pd.Timestamp('2024-07-01') else 'validation' if d<pd.Timestamp('2025-01-01') else 'test' if d<pd.Timestamp('2026-01-01') else 'post_test' for d in dates],"raw_target_row":targets}).to_csv(dest/"split_manifest.csv",index=False)
    bestx=None; searchx=[]
    for depth in [2,3,5]:
        for lr in [.03,.08]:
            cfg=dict(max_depth=depth,learning_rate=lr,min_child_weight=5,reg_lambda=5.,subsample=.9,colsample_bytree=.9,
                     objective="reg:squarederror",tree_method="hist",n_jobs=2,random_state=42)
            m=XGBRegressor(**cfg,n_estimators=800,early_stopping_rounds=40)
            m.fit(x.iloc[tr],y[tr],eval_set=[(x.iloc[va],y[va])],verbose=False)
            pred=np.maximum(m.predict(x.iloc[va]),0)
            row=dict(config=cfg,rounds=int(m.best_iteration+1),**metrics(y[va],pred));searchx.append(row)
            if bestx is None or row['rmse_kwh']<bestx['rmse_kwh']: bestx,val['XGBoost']=row,pred
    def fit_prophet(cps,fitix,ix):
        m=Prophet(changepoint_prior_scale=cps,yearly_seasonality=5,weekly_seasonality=False,daily_seasonality=False,
                  seasonality_prior_scale=1.,uncertainty_samples=0)
        for col in ['irradiance','lag1','mean7','rule_c']:m.add_regressor(col,prior_scale=1.,standardize=True)
        m.fit(p.iloc[fitix].assign(y=y[fitix]),seed=42)
        return m,np.maximum(m.predict(p.iloc[ix]).yhat.to_numpy(),0)
    bestp=None;searchp=[]
    for cps in [.01,.05,.2]:
        m,pred=fit_prophet(cps,tr,va);row=dict(cps=cps,**metrics(y[va],pred));searchp.append(row)
        if bestp is None or row['rmse_kwh']<bestp['rmse_kwh']:bestp,val['Prophet']=row,pred
    def fit_lstm(fitix,ix,epochs,validate):
        keras.backend.clear_session();keras.utils.set_random_seed(42)
        scaler=HAICScaler()
        scaler.close_min=float(min(w[fitix,:,0].min(),y[fitix].min()))
        scaler.close_max=float(max(w[fitix,:,0].max(),y[fitix].max()))
        scaler.volume_min=float(w[fitix,:,1].min());scaler.volume_max=float(w[fitix,:,1].max())
        lo=np.array([scaler.close_min,scaler.volume_min]);ranges=np.array([scaler.close_max-scaler.close_min,scaler.volume_max-scaler.volume_min])
        assert (ranges>0).all()
        xx=((w-lo)/ranges).astype('float32');yy=((y-lo[0])/ranges[0]).astype('float32')
        callbacks=[keras.callbacks.EarlyStopping(patience=120,restore_best_weights=True)] if validate else []
        class Progress(keras.callbacks.Callback):
            def on_epoch_end(self,epoch,logs=None):
                if (epoch+1)%30==0:print(pid,'validation' if validate else 'refit',epoch+1,logs,flush=True)
        m=build_model()
        history=m.fit(xx[fitix],yy[fitix],validation_data=(xx[ix],yy[ix]) if validate else None,
                      epochs=epochs,batch_size=32,shuffle=False,verbose=0,callbacks=callbacks+[Progress()]).history
        pred=np.maximum(m.predict(xx[ix],verbose=0).ravel()*ranges[0]+lo[0],0)
        return m,scaler,pred,history
    m,s,val['LSTM'],hist=fit_lstm(tr,va,120,True)
    epochs=int(np.argmin(hist['val_loss'])+1);dump(dest/'validation_history.json',hist)
    matrix=np.column_stack([val[k] for k in ['LSTM','XGBoost','Prophet']])
    grid=[[i/10,j/10,(10-i-j)/10] for i in range(11) for j in range(11-i)]
    weights={}
    for kind,g in [('Ensemble',grid),('LSTM_Main_Ensemble',[g for g in grid if g[0]>=.5])]:
        weights[kind]=min(g,key=lambda a:metrics(y[va],matrix@a)['rmse_kwh']);val[kind]=matrix@weights[kind]
    vm={k:metrics(y[va],pred) for k,pred in val.items()};selected=min(vm,key=lambda k:vm[k]['rmse_kwh'])
    frozen=dict(frozen_utc=now(),selected_by_validation=selected,lstm_epochs=epochs,seed=42,xgb=bestx,prophet=bestp,
                weights_order=['LSTM','XGBoost','Prophet'],ensemble_weights=weights,validation_metrics=vm,search_xgb=searchx,search_prophet=searchp)
    dump(dest/'frozen_selection.json',frozen)
    pd.DataFrame({'date':dates[va],'actual_kwh':y[va],**val}).to_csv(dest/'validation_predictions.csv',index=False)
    # Test predictions use only train+validation weights. Release uses all data afterwards.
    replay_checks={};release_checks={}
    for role,fitix,ix in [('evaluation',np.r_[tr,va],te),('release',np.arange(len(y)),np.arange(max(0,len(y)-3),len(y)))]:
        folder=dest/role;folder.mkdir(exist_ok=True)
        preds={}
        m=XGBRegressor(**bestx['config'],n_estimators=bestx['rounds']);m.fit(x.iloc[fitix],y[fitix])
        preds['XGBoost']=np.maximum(m.predict(x.iloc[ix]),0);m.save_model(folder/'xgboost.ubj')
        m,preds['Prophet']=fit_prophet(bestp['cps'],fitix,ix)
        (folder/'prophet.json').write_text(model_to_json(m),encoding='utf-8')
        m,s,preds['LSTM'],hist=fit_lstm(fitix,ix,epochs,False)
        m.save(folder/'model.keras');s.save(str(folder/'scaler.pkl'))
        dump(folder/'scaler.json',s.__dict__);dump(dest/f'{role}_history.json',hist)
        mm=np.column_stack([preds[k] for k in ['LSTM','XGBoost','Prophet']])
        preds.update({k:mm@weight for k,weight in weights.items()})
        if role=='evaluation':
            test.update(preds)
            pd.DataFrame({'date':dates[te],'actual_kwh':y[te],**test}).to_csv(dest/'test_predictions.csv',index=False)
            scores={k:metrics(y[te],pred) for k,pred in test.items()}
        meta=dict(plant_id=pid,plant_name=plant['name'],region=plant['region'],capacity_kw=plant['capacity_kw'],
                  input_contract=CONTRACT,input_shape=[20,2],sequence_order='oldest_to_newest',
                  input_meanings=['generation_kwh[d]','jma_msm_shortwave_radiation_previous_day1[target=d+1]'],
                  source=plant['source'],source_sha256=plant['source_sha256'],role=role,
                  bundle_version=f'{pid}-forecast-{role}-20261007',trained_targets=split(fitix),splits=splits,
                  scaler=s.__dict__,lstm_seed=42,lstm_epochs=epochs,selected_by_validation=selected,
                  primary_serving_model='LSTM',ensemble_weights=weights,validation_metrics=vm,
                  heldout_evaluation_metrics=scores,metrics_apply_to='evaluation weights only, not release refit',
                  publication_cutoff_verified=False,created_utc=now(),github_main=read(out/'github_review.json')['origin/main']['commit'])
        dump(folder/'metadata.json',meta)
        files=['model.keras','scaler.pkl','scaler.json','xgboost.ubj','prophet.json','metadata.json']
        dump(folder/'bundle_hashes.json',{f:sha(folder/f) for f in files})
        loaded=ForecastModel(folder)
        np.testing.assert_allclose(loaded.predict_windows(w[ix]),preds['LSTM'],rtol=1e-6,atol=1e-3)
        loaded_scaler=HAICScaler.load(str(folder/'scaler.pkl'))
        xx=np.array([[loaded_scaler.transform_point(*point) for point in win] for win in w[ix]],dtype='float32')
        plain=keras.models.load_model(folder/'model.keras',compile=False)
        direct=np.maximum(np.array([loaded_scaler.inverse_close(float(z)) for z in plain.predict(xx,verbose=0).ravel()]),0)
        np.testing.assert_allclose(direct,preds['LSTM'],rtol=1e-6,atol=1e-3)
        xgb=XGBRegressor(n_jobs=2);xgb.load_model(folder/'xgboost.ubj')
        np.testing.assert_allclose(np.maximum(xgb.predict(x.iloc[ix]),0),preds['XGBoost'],rtol=1e-6,atol=1e-3)
        from prophet.serialize import model_from_json
        prophet=model_from_json((folder/'prophet.json').read_text(encoding='utf-8'))
        np.testing.assert_allclose(np.maximum(prophet.predict(p.iloc[ix]).yhat.to_numpy(),0),preds['Prophet'],rtol=1e-6,atol=1e-3)
        sample_index=int(ix[0]);raw_t=int(targets[sample_index])
        request={'sequence':[{'date':str(df.index[j].date()),'close':float(w[sample_index,j-(raw_t-20),0]),
                             'volume':float(w[sample_index,j-(raw_t-20),1])} for j in range(raw_t-20,raw_t)]}
        dump(dest/f'{role}_request.json',request)
        dump(dest/f'{role}_reload_check.json',{'passed':True,'verified_days':len(ix),'native_scaler_api_compatible':True,
            'first_prediction_kwh':float(preds['LSTM'][0]),'target_date':str(dates[sample_index].date()),
            'max_abs_error_kwh':float(np.max(np.abs(direct-preds['LSTM'])))})
        print('SAVED',pid,role,'epoch',epochs,flush=True)
    dump(dest/'result.json',dict(plant_id=pid,name=plant['name'],region=plant['region'],completed_utc=now(),splits=splits,
          selected_by_validation=selected,validation_metrics=vm,test_metrics=scores,roles=['evaluation','release'],reload_passed=True))
    print('COMPLETE',pid,'LSTM',scores['LSTM']['rmse_kwh'],flush=True)


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--out',default=DEFAULT);ap.add_argument('--plant');ap.add_argument('--prepare-only',action='store_true');ap.add_argument('--workers',type=int,default=3)
    args=ap.parse_args();out=ROOT/args.out;out.mkdir(parents=True,exist_ok=True)
    if args.plant:train(out,args.plant);return
    plants=read(out/'screening.json')['admitted'] if (out/'screening.json').exists() else prepare(out)
    if args.prepare_only:return
    expected=read(out/'training_code_hashes.json')
    assert all(sha(ROOT/rel)==h for rel,h in expected.items()),'Code changed; use a new output version'
    def worker(plant):
        pid=plant['plant_id']
        if (out/'plants'/pid/'result.json').exists():return pid,0
        with (out/f'{pid}.log').open('w',encoding='utf-8') as fp:
            process=subprocess.run([sys.executable,'-X','utf8','-B',str(Path(__file__).resolve()),'--out',args.out,'--plant',pid],cwd=ROOT/'project',stdout=fp,stderr=subprocess.STDOUT)
        return pid,process.returncode
    status=[]
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for future in as_completed([pool.submit(worker,p) for p in plants]):
            pid,code=future.result();status.append({'plant_id':pid,'exit_code':code});dump(out/'execution_status.json',status)
            print(now(),'DONE',len(status),'/',len(plants),pid,code,flush=True)
    unchanged=all(sha(ROOT/rel)==h for rel,h in expected.items())
    dump(out/'training_integrity.json',{'passed':unchanged,'checked_files':len(expected)})
    assert unchanged and all(r['exit_code']==0 for r in status),'Inspect failed plant logs'


if __name__=='__main__':main()
