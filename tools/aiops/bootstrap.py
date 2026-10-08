"""Import evaluated forecast LSTMs into the isolated operational registry."""
import os
os.environ.setdefault('TF_ENABLE_ONEDNN_OPTS','0')
os.environ.setdefault('TF_CPP_MIN_LOG_LEVEL','3')
os.environ.setdefault('MLFLOW_DISABLE_AGENT_HINT','1')
import tensorflow as tf
tf.config.threading.set_intra_op_parallelism_threads(2)
tf.config.threading.set_inter_op_parallelism_threads(1)
import argparse
from datetime import timedelta
from pathlib import Path
import sys
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'project'))
from data.features import HAICScaler
from serving_app import runtime as rt, registry
from serving_app.monitoring.policy import initial_gate,classify,performance_index


def monitoring_data(source,capacity):
    pid=source['plant_id']
    if pid=='15043409_u1':
        path=ROOT/'datasets/hadong_daily_full.csv';obs=pd.read_csv(path)
        obs=obs.rename(columns={'gy_gsr_obs':'gsr_mj_m2'})
    else:
        path=ROOT/'datasets/multi_plant/daily'/f'{pid}.csv';obs=pd.read_csv(path)
    obs['date']=pd.to_datetime(obs.date);obs=obs.set_index('date').sort_index()
    good=obs.gen_kwh.notna() & (obs.gen_kwh>0) & obs.gsr_mj_m2.notna() & (obs.gsr_mj_m2>1)
    if 'generation_valid' in obs:good &= obs.generation_valid.eq(1)
    fit=obs[good & (obs.index>=pd.Timestamp('2022-01-01')) & (obs.index<pd.Timestamp('2024-01-01'))]
    if len(fit)<180:raise ValueError(f'Insufficient observed-weather calibration: {pid}')
    slope,intercept=np.linalg.lstsq(np.column_stack([fit.gsr_mj_m2,np.ones(len(fit))]),fit.gen_kwh,rcond=None)[0]
    if slope<=0:raise ValueError('Expected-output model must increase with irradiance')
    expected=pd.Series(np.maximum(slope*obs.gsr_mj_m2+intercept,0),index=obs.index)
    baseline_rows=[]
    for day in pd.date_range('2024-01-02','2024-12-31'):
        if day not in obs.index:continue
        row=obs.loc[day];e=expected.loc[day]
        if not np.isfinite(row.gen_kwh) or not np.isfinite(e):continue
        if 'generation_valid' in obs and row.generation_valid!=1:continue
        baseline_rows.append(dict(date=str(day.date()),close=float(row.gen_kwh),expected=float(e)))
    flags=classify(baseline_rows,capacity);baseline,n=performance_index(baseline_rows,flags)
    if n<180:baseline=None
    forecast=pd.read_csv(ROOT/Path(source['source'].replace('\\','/')),parse_dates=['target_date']).set_index('target_date').sort_index()
    history=[]
    for day,row in forecast.iterrows():
        tomorrow=day+pd.Timedelta(days=1)
        if tomorrow not in forecast.index or not np.isfinite(row.gen_kwh):continue
        if 'generation_valid' in forecast and row.generation_valid!=1:continue
        volume=forecast.loc[tomorrow,'shortwave_radiation_previous_day1']
        if not np.isfinite(volume) or not 0<=volume<=45 or not 0<=row.gen_kwh<=capacity*24:continue
        e=expected.get(day,float('nan'))
        history.append(dict(date=str(day.date()),close=float(row.gen_kwh),volume=float(volume),expected=float(e) if np.isfinite(e) else None))
    return history,dict(baseline_pi=baseline,baseline_valid_days=n,baseline_start='2024-01-02',baseline_end='2024-12-31',
                        expected_model=dict(slope=float(slope),intercept=float(intercept),fit_end='2023-12-31',n=len(fit),
                                            source_sha256=rt.sha(path),source=str(path.relative_to(ROOT)),type='post_observation_regional_ASOS_linear'))


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--evidence',default='docs/proposal/evidence/forecast_models_20261007');ap.add_argument('--plant');args=ap.parse_args()
    evidence=ROOT/args.evidence;screen=rt.read(evidence/'screening.json')['admitted']
    plants={}
    for source in screen:
        pid='hadong-sewage' if source['plant_id']=='15043409_u1' else source['plant_id'].replace('_','-')
        plants[pid]=dict(plant_id=pid,source_id=source['plant_id'],name=source['name'],capacity_kw=source['capacity_kw'],
                        region=source['region'],capacity_basis='source catalog; not settlement registered capacity')
    catalog={'plants':plants,'portfolios':{'virtual-vpp':{'version':'20261007','members':list(plants),'virtual':True}},'created_at':rt.now()}
    with rt.lock():
        if (rt.root()/'catalog.json').exists():
            previous=rt.catalog()
            if previous['plants']!=plants:raise ValueError('Catalog differs; use a new SOLAR_STATE_DIR')
        else:rt.write(rt.root()/'catalog.json',catalog)
        receipt=rt.read(rt.root()/'bootstrap.json') if (rt.root()/'bootstrap.json').exists() else {}
        for source in screen:
            pid='hadong-sewage' if source['plant_id']=='15043409_u1' else source['plant_id'].replace('_','-')
            if args.plant and pid!=args.plant:continue
            if pid in receipt:continue
            if not source['capacity_kw']:
                receipt[pid]={'promoted':False,'reason':'capacity_unknown'}
                rt.write(rt.root()/'bootstrap.json',receipt)
                print('BOOTSTRAP',pid,'capacity unknown; serving held',flush=True)
                continue
            folder=evidence/'plants'/source['plant_id']/'evaluation'
            for f,h in rt.read(folder/'bundle_hashes.json').items():
                if rt.sha(folder/f)!=h:raise ValueError('Source bundle integrity failure')
            meta=rt.read(folder/'metadata.json');scores=rt.read(folder.parent/'result.json')['test_metrics'];gate=initial_gate(scores)
            history,monitor=monitoring_data(source,source['capacity_kw']);rt.write(rt.root()/'history'/f'{pid}.json',history)
            rt.write(rt.root()/'monitoring_config'/f'{pid}.json',monitor)
            manifest=dict(plant_id=pid,source_bundle_id=source['plant_id'],train_end=meta['trained_targets']['last'],
                 baseline_pi=monitor['baseline_pi'],monitoring_config=monitor,source_sha256=source['source_sha256'],
                 evaluation_period=meta['splits']['test'],replay_only=True,
                 quality_note='Offline 2025 gate; historical replay does not establish point-in-time deployment availability.')
            model=tf.keras.models.load_model(folder/'model.keras',compile=False);scaler=HAICScaler.load(folder/'scaler.pkl')
            sample=rt.read(folder.parent/'evaluation_request.json')['sequence']
            example=np.array([[scaler.transform_point(r['close'],r['volume']) for r in sample]],dtype='float32')
            result=registry.register(model,folder/'scaler.pkl',manifest,example,gate=gate,kind='bootstrap-evaluation')
            if gate['passed']:
                registry.activate(pid,result['version']);result['promoted']=True
            receipt[pid]=result;rt.write(rt.root()/'bootstrap.json',receipt)
            print('BOOTSTRAP',pid,'approved' if result['promoted'] else 'gate rejected',flush=True)
            tf.keras.backend.clear_session()
        print('COMPLETE',len(receipt),'approved',sum(r['promoted'] for r in receipt.values()),flush=True)


if __name__=='__main__':main()
