"""Real hourly models: API boundaries, all approved sites and durable native AIOps lifecycle."""
import os
os.environ['SOLAR_MODEL_CONTRACT']='solar_hourly_24_jma_day2_v1';os.environ['TF_ENABLE_ONEDNN_OPTS']='0';os.environ['TF_CPP_MIN_LOG_LEVEL']='3'
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];os.environ['SOLAR_STATE_DIR']=str(ROOT/'project/data/runtime-hourly')
import sys
sys.path.insert(0,str(ROOT/'project'))
from serving_app.hourly.app import app
from serving_app import runtime as rt,model_loader,registry
from serving_app.hourly.data import sample,arrays,COLUMNS
from serving_app.hourly import policy
from serving_app.hourly.worker import step
from fastapi.testclient import TestClient
import csv,io,json,shutil,uuid
from datetime import datetime,timedelta
import numpy as np
EVIDENCE=ROOT/'docs/proposal/evidence/hourly_20261007'
def main():
    checks=[];client=TestClient(app)
    for pid in rt.catalog()['plants']:
        body=sample(pid)['prediction'];r=client.post('/predict',json=body);assert r.status_code==200,r.text;d=r.json()
        assert len(d['predictions'])==24 and all(0<=v['predicted_kwh']<=rt.plant(pid)['capacity_kw'] for v in d['predictions'])
        assert abs(sum(v['predicted_kwh'] for v in d['predictions'])-d['total_kwh'])<1e-6
        assert client.get('/ui/energy',params={'plant_id':pid}).status_code==200
        checks.append(dict(plant_id=pid,model_version=d['model_version'],hours=24))
    original=sample('hadong-sewage')['prediction']
    for mutate in [lambda b:b['history'].pop(),lambda b:b['forecast'].pop(),lambda b:b['history'][0].update(timestamp='2026-02-26T00:00:00'),lambda b:b['history'][1].update(timestamp=b['history'][0]['timestamp']),lambda b:b['history'][0].update(generation_kwh=56),lambda b:b['forecast'][0].update(shortwave_radiation=-1),lambda b:b.update(plant_id='15043395-u1')]:
        body=json.loads(json.dumps(original));mutate(body);assert client.post('/predict',json=body).status_code==422
    body=json.loads(json.dumps(original))
    for r in body['forecast']:r['shortwave_radiation']=0
    assert all(r['predicted_kwh']==0 for r in client.post('/predict',json=body).json()['predictions'])
    assert client.post('/predict',json={'sequence':[]}).status_code==422
    assert client.get('/ui/energy?plant_id=15043395-u1').status_code==404
    assert client.get('/logs/not-a-log').status_code==404
    portfolio=client.post('/portfolios/all-approved/predict',json={'inputs':{pid:sample(pid)['prediction'] for pid in rt.catalog()['plants']}})
    assert portfolio.status_code==200 and portfolio.json()['complete'],portfolio.text
    partial=client.post('/portfolios/all-approved/predict',json={'inputs':{'hadong-sewage':original}}).json()
    assert not partial['complete'] and partial['predictions'] is None
    # Isolate every mutation from the production runtime.
    production=rt.root();isolated=EVIDENCE/('runtime-verify-'+uuid.uuid4().hex[:8]);isolated.mkdir()
    pids=['hadong-sewage',next(p for p in rt.catalog()['plants'] if p!='hadong-sewage')]
    catalog=dict(plants={p:rt.plant(p) for p in pids},portfolios={},contract=rt.CONTRACT)
    rt.write(isolated/'catalog.json',catalog);os.environ['SOLAR_STATE_DIR']=str(isolated);model_loader.clear_cache()
    with rt.lock():
        for pid in pids:
            pointer=rt.read(production/'models'/pid/'current.json');folder=production/'models'/pid/'versions'/pointer['version'];meta=rt.read(folder/'manifest.json')
            import tensorflow as tf
            keras=tf.keras.models.load_model(folder/'model.keras',compile=False)
            metadata={k:v for k,v in meta.items() if k not in ['version','hashes','gate','run_id','created_at','model_name','contract']}
            result=registry.register(keras,folder/'scaler.pkl',metadata,np.zeros((1,24,9),dtype='float32'),gate=meta['gate'],kind='hourly-verification-seed');registry.activate(pid,result['version'])
            target=isolated/'history'/f'{pid}.csv';target.parent.mkdir(exist_ok=True);shutil.copy2(production/'history'/f'{pid}.csv',target)
    pid='hadong-sewage';m=model_loader.get_model(pid);base=m.version;other=rt.current(pids[1]);scaler_sha=rt.sha(rt.version_dir(pid,base)/'scaler.pkl')
    rows=sample(pid)['batch']['rows'];assert len(rows)==696
    # Controlled future labels verify plumbing, never reported as forecast performance.
    start=datetime.fromisoformat(rows[0]['timestamp']);future=datetime(2027,6,1,tzinfo=start.tzinfo)
    for i,r in enumerate(rows):r['timestamp']=(future+timedelta(hours=i)).isoformat()
    x,_,_=arrays(rows,m.scaler['capacity_kw']);pred=m.predict_x(x)
    for i,v in enumerate(pred.ravel(),24):rows[i]['generation_kwh']=float(v*.9)
    job=policy.enqueue(pid,rows,m,'synthetic-lifecycle');duplicate=policy.enqueue(pid,rows,m,'synthetic-lifecycle');assert job['id']==duplicate['id']
    changed=json.loads(json.dumps(rows));changed[-1]['generation_kwh']+=.01
    try:policy.enqueue(pid,changed,m,'synthetic-lifecycle');raise AssertionError('Expected immutable conflict')
    except ValueError:pass
    assert step()
    completed=rt.get_job(job['id']);assert completed['status']=='succeeded',completed
    result=completed['result']
    assert result['promoted'],result
    version=result['version'];assert rt.sha(rt.version_dir(pid,version)/'scaler.pkl')==scaler_sha;assert rt.current(pids[1])==other
    assert registry.rollback(pid,base)['version']==base;model_loader.clear_cache()
    m=model_loader.get_model(pid)
    rejected=registry.register(m._keras_model,rt.version_dir(pid,base)/'scaler.pkl',dict(m.manifest),np.zeros((1,24,9),dtype='float32'),gate=dict(passed=False,rmse_kwh=1000,limit_kwh=1),kind='controlled-gate-failure')
    assert not rejected['promoted'] and rt.current(pid)['version']==base
    # API uploads use the new CSV contract and produce monitoring records.
    raw=io.StringIO();writer=csv.DictWriter(raw,fieldnames=COLUMNS);writer.writeheader();writer.writerows(sample(pid)['batch']['rows'])
    upload=client.post('/data/upload',data={'plant_id':pid},files={'file':('hourly.csv',raw.getvalue().encode(),'text/csv')});assert upload.status_code==200,upload.text
    assert client.get('/data/status',params={'plant_id':pid}).json()['rows']==696
    # Facility hold, short-window skip and normal checks use independently controlled references.
    regular=sample(pid)['batch']['rows']
    for r in regular:r['generation_kwh']=min(55,r['shortwave_radiation']*m.scaler['radiation_coefficient'])
    assert policy.inspect(regular,m)[0]['state']=='normal'
    assert policy.inspect(regular[-48:],m)[0]['state']=='skipped'
    # Automatic drift enqueue and worker rejection are also real queue transitions.
    for i,r in enumerate(regular):
        r['timestamp']=(future+timedelta(days=40,hours=i)).isoformat()
        r['generation_kwh']*=.5
    drift=policy.monitor(pid,regular,m)['monitor'];assert drift['state']=='queued',drift
    assert step();drift_job=rt.get_job(drift['job']['id']);assert drift_job['status'] in ['succeeded','rejected'],drift_job
    for r in regular[-168:]:r['generation_kwh']=0
    assert policy.inspect(regular,m)[0]['state']=='held'
    report=dict(all_sites=checks,api_invalid_cases=9,night_zero=True,complete_and_partial_portfolio=True,isolated_runtime=str(isolated),native_retrain=result,worker_job=completed,automatic_drift_job=drift_job,scaler_preserved=True,other_plant_unchanged=True,rollback=True,gate_failure_no_promote=True,immutable_duplicate=True,upload=upload.json(),facility_hold=True,insufficient_skip=True,normal=True,synthetic_scope='AIOps functional controls only; not forecast quality')
    rt.write(EVIDENCE/'verification.json',report);print('VERIFIED',len(checks),'sites, native retrain, rollback, gate failure, CSV, monitoring')
if __name__=='__main__':main()
