"""Real LSTM + MLflow + durable worker lifecycle in an isolated runtime.

The injected labels/expected values below test control flow, not forecasting quality.
"""
import os
os.environ.setdefault('TF_ENABLE_ONEDNN_OPTS','0');os.environ.setdefault('TF_CPP_MIN_LOG_LEVEL','3')
import tensorflow as tf
tf.config.threading.set_intra_op_parallelism_threads(2);tf.config.threading.set_inter_op_parallelism_threads(1)
from pathlib import Path
from datetime import date,timedelta
import json,subprocess,sys,uuid
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'project'))
from serving_app import runtime as rt

def main():
    evidence=ROOT/'docs/proposal/evidence/aiops_backend_20261007';evidence.mkdir(exist_ok=True)
    state=evidence/('runtime-lifecycle-'+uuid.uuid4().hex[:8]);os.environ['SOLAR_STATE_DIR']=str(state)
    os.environ['SOLAR_UPLOAD_DIR']=str(state/'uploads')
    report={'synthetic_control_flow_only':True,'runtime':str(state),'steps':[]}
    def record(name,value):
        report['steps'].append(dict(name=name,result=value));rt.write(evidence/'lifecycle.json',report);print(name,value,flush=True)
    for pid in ['hadong-sewage','15043384-u1']:
        with (evidence/f'bootstrap-test-{pid}.log').open('w',encoding='utf-8') as log:
            subprocess.run([sys.executable,'-X','utf8','-B',str(Path(__file__).with_name('bootstrap.py')),'--plant',pid],cwd=ROOT/'project',stdout=log,stderr=subprocess.STDOUT,check=True)
    from fastapi.testclient import TestClient
    from serving_app.main import app
    from serving_app import model_loader,registry
    from serving_app.routers import data
    data.UPLOAD_DIR=str(state/'uploads')
    baseline=rt.read(state/'monitoring_config/hadong-sewage.json')['baseline_pi']
    def batch(start,factor=1.):
        return dict(plant_id='hadong-sewage',dates=[str(start+timedelta(days=i)) for i in range(41)],
                    prices=[140.*factor]*41,volumes=[10.]*41,expected=[140./baseline]*41)
    def worker(label):
        with (evidence/f'worker-{label}.log').open('w',encoding='utf-8') as log:
            subprocess.run([sys.executable,'-X','utf8','-B','-m','serving_app.monitoring.worker','--once','--no-scan'],cwd=ROOT/'project',stdout=log,stderr=subprocess.STDOUT,check=True,timeout=180)
    with TestClient(app) as api:
        normal=batch(date(2025,3,1));response=api.post('/predict/batch-test',json=normal);assert response.status_code==200,response.text
        assert response.json()['drift_check']['status']=='ok',response.text
        record('normal',response.json()['drift_check'])
        drift=batch(date(2025,7,1),.86);response=api.post('/predict/batch-test',json=drift);assert response.status_code==200,response.text
        check=response.json()['drift_check'];assert check['status']=='retrain_triggered',check;job_id=check['job_id']
        repeat=api.post('/predict/batch-test',json=drift).json()['drift_check'];assert repeat['job_id']==job_id
        changed=dict(drift,prices=[139.]*41)
        assert api.post('/predict/batch-test',json=changed).status_code==409
        assert len(api.get('/jobs').json())==1
        record('drift_and_duplicate',check)
        worker('passing')
        result=api.get('/jobs/'+job_id).json();record('real_warm_start_job',result)
        assert result['status']=='succeeded' and result['result']['promoted'],result
        request=dict(sequence=[dict(date=d,close=c,volume=v) for d,c,v in zip(drift['dates'][-20:],drift['prices'][-20:],drift['volumes'][-20:])])
        response=api.post('/predict',json=request);assert response.status_code==200,response.text
        version=response.json()['model_version'];assert version!='1';record('cache_switched',response.json())
        c=registry.client();versions=c.search_model_versions("name='solar-daily-hadong-sewage'")
        assert [str(v.version) for v in versions if v.current_stage=='Production']==[version]
        assert str(c.get_model_version_by_alias('solar-daily-hadong-sewage','champion').version)==version
        assert rt.current('15043384-u1')['version']=='1'
        old_scaler=rt.sha(rt.version_dir('hadong-sewage','1')/'scaler.pkl');new_scaler=rt.sha(rt.version_dir('hadong-sewage',version)/'scaler.pkl')
        assert old_scaler==new_scaler;record('paired_scaler_unchanged',True)
        bad=batch(date(2025,10,1),.86)
        bad['prices'][-5:]=[1000.]*5;bad['expected']=[x/baseline for x in bad['prices']]
        response=api.post('/plants/hadong-sewage/retrain',json=bad);assert response.status_code==202,response.text
        bad_id=response.json()['id'];worker('rejected');failure=api.get('/jobs/'+bad_id).json();record('gate_rejected',failure)
        assert failure['status']=='succeeded' and not failure['result']['promoted'],failure
        assert rt.current('hadong-sewage')['version']==version
        response=api.post('/plants/hadong-sewage/rollback',json={'version':1});assert response.status_code==200,response.text
        response=api.post('/predict',json=request);assert response.json()['model_version']=='1';record('rollback',response.json())
        facility=batch(date(2026,1,1));facility['prices'][-3:]=[0.,0.,0.]
        response=api.post('/predict/batch-test',json=facility);assert response.json()['drift_check']['status']=='facility_check',response.text
        record('facility_hold',response.json()['drift_check']);assert len(api.get('/jobs').json())==2
        # A corrupt alternate bundle must not replace the active model or registry stage.
        path=rt.version_dir('hadong-sewage',version)/'scaler.pkl';original=path.read_bytes();path.write_bytes(b'corrupt')
        try:
            response=api.post('/plants/hadong-sewage/rollback',json={'version':int(version)})
            assert response.status_code==409,response.text
            assert rt.current('hadong-sewage')['version']=='1'
        finally:path.write_bytes(original)
        record('corrupt_bundle_rejected',True)
        import csv,io
        uploaded=batch(date(2026,3,1));text=io.StringIO();writer=csv.writer(text);writer.writerow(['Date','Close','Volume','Expected'])
        writer.writerows(zip(uploaded['dates'],uploaded['prices'],uploaded['volumes'],uploaded['expected']))
        response=api.post('/data/upload',data={'plant_id':'hadong-sewage'},files={'file':('new.csv',text.getvalue(),'text/csv')})
        assert response.status_code==200,response.text
        with (evidence/'worker-upload.log').open('w',encoding='utf-8') as log:
            subprocess.run([sys.executable,'-X','utf8','-B','-m','serving_app.monitoring.worker','--once'],cwd=ROOT/'project',stdout=log,stderr=subprocess.STDOUT,check=True,timeout=180)
        response=api.get('/plants/hadong-sewage/status');assert response.json()['monitor']['status']=='ok',response.text
        assert response.json()['upload']['end_date']==uploaded['dates'][-1]
        record('upload_automatically_monitored',response.json()['monitor'])
    report['passed']=True;rt.write(evidence/'lifecycle.json',report)
    print('LIFECYCLE PASSED',flush=True)
if __name__=='__main__':main()
