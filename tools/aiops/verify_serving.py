"""Read-only verification of every approved plant against saved test predictions."""
import os
os.environ.setdefault('TF_ENABLE_ONEDNN_OPTS','0');os.environ.setdefault('TF_CPP_MIN_LOG_LEVEL','3')
import tensorflow as tf
tf.config.threading.set_intra_op_parallelism_threads(2);tf.config.threading.set_inter_op_parallelism_threads(1)
from pathlib import Path
import sys,math,copy
from datetime import date,timedelta
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'project'))
from serving_app import runtime as rt,registry
from serving_app.main import app
from fastapi.testclient import TestClient

def main():
    checks=[];cat=rt.catalog();receipt=rt.read(rt.root()/'bootstrap.json');client=registry.client();requests={}
    with TestClient(app) as api:
        assert len(api.get('/plants').json())==len(cat['plants'])
        for pid,entry in cat['plants'].items():
            source=ROOT/'docs/proposal/evidence/forecast_models_20261007/plants'/entry['source_id']
            body=rt.read(source/'evaluation_request.json');body['plant_id']=pid;requests[pid]=body['sequence']
            response=api.post('/predict',json=body)
            if receipt[pid]['promoted']:
                assert response.status_code==200,(pid,response.text)
                expected=rt.read(source/'evaluation_reload_check.json')['first_prediction_kwh']
                assert math.isclose(response.json()['predicted_close'],expected,abs_tol=.011),(pid,response.text,expected)
                current=rt.current(pid)['version'];assert response.json()['model_version']==current
                versions=client.search_model_versions(f"name='{rt.model_name(pid)}'")
                assert [str(v.version) for v in versions if v.current_stage=='Production']==[current]
                checks.append(dict(plant_id=pid,served=True,version=current))
            else:
                assert response.status_code==503,(pid,response.text)
                checks.append(dict(plant_id=pid,served=False,reason=receipt[pid].get('reason')))
        body=copy.deepcopy(body);body['plant_id']='unknown-plant';assert api.post('/predict',json=body).status_code==404
        body=rt.read(ROOT/'docs/proposal/evidence/forecast_models_20261007/plants/15043409_u1/evaluation_request.json')
        body['sequence'][0]['close']=1320.1;assert api.post('/predict',json=body).status_code==422
        # Portfolio requests must refer to one common target day; all first test dates are aligned here.
        members=cat['portfolios']['approved-vpp']['members']
        target=date.fromisoformat(rt.read(rt.root()/'portfolio_quality.json')['approved-vpp']['first'][:10])
        for pid in members:
            history={r['date']:r for r in rt.read(rt.root()/'history'/f'{pid}.json')}
            requests[pid]=[{k:history[str(target-timedelta(days=lag))][k] for k in ['date','close','volume']} for lag in range(20,0,-1)]
        response=api.post('/portfolios/approved-vpp/predict',json={'sequences':{pid:requests[pid] for pid in members}})
        assert response.status_code==200,response.text
        complete=response.json();assert complete['complete'] and complete['quality_verified']
        assert math.isclose(complete['total_predicted_kwh'],sum(m['predicted_kwh'] for m in complete['members']))
        response=api.post('/portfolios/approved-vpp/predict',json={'sequences':{members[0]:requests[members[0]]}})
        partial=response.json();assert not partial['complete'] and partial['total_predicted_kwh'] is None
        result=dict(passed=True,plants=checks,approved=sum(r['served'] for r in checks),complete_portfolio=complete,partial_portfolio=partial)
        rt.write(ROOT/'docs/proposal/evidence/aiops_backend_20261007/serving.json',result)
        print('SERVING VERIFIED',len(checks),'approved',result['approved'])
if __name__=='__main__':main()
