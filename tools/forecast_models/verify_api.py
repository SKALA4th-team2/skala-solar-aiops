"""Exercise actual saved weights through the reviewed GitHub main FastAPI routes."""
import os
os.environ.setdefault('TF_ENABLE_ONEDNN_OPTS','0')
os.environ.setdefault('TF_CPP_MIN_LOG_LEVEL','2')
os.environ.setdefault('MLFLOW_DISABLE_AGENT_HINT','1')
import tensorflow as tf
tf.config.threading.set_intra_op_parallelism_threads(2)
tf.config.threading.set_inter_op_parallelism_threads(1)
import argparse
import json
from pathlib import Path
import sys
import numpy as np
import pandas as pd
from train import ROOT,DEFAULT,read,dump,make_data,sha
from bundle import ForecastModel


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--out',default=DEFAULT);args=ap.parse_args()
    out=ROOT/args.out;pid='15043409_u1';dest=out/'plants'/pid;folder=dest/'evaluation'
    github=out/'github_snapshot/main/project';sys.path.insert(0,str(github))
    from fastapi.testclient import TestClient
    from serving_app import model_loader
    from serving_app.main import app
    from data.features import HAICScaler
    from serving_app.routers.data import validate_csv
    model_loader.LOCAL_MODEL_PATH=str(folder/'model.keras')
    model_loader.SCALER_PATH=str(folder/'scaler.pkl')
    model_loader._model_cache=None
    request=read(dest/'evaluation_request.json')
    expected=read(dest/'evaluation_reload_check.json')
    results={'github_main':read(out/'github_review.json')['origin/main']['commit'],'real_weights':True}
    with TestClient(app) as client:
        response=client.post('/predict',json=request)
        assert response.status_code==200,response.text
        assert response.json()['target_date']==expected['target_date']
        assert abs(response.json()['predicted_close']-expected['first_prediction_kwh'])<.011
        results['unmodified_native_loader']=response.json()
        # This is the actual model bundle, not a mock prediction function.
        actual=ForecastModel(folder);model_loader._model_cache=actual
        response=client.post('/predict',json=request);assert response.status_code==200,response.text
        assert response.json()['model_version']==actual.version
        results['versioned_bundle_loader']=response.json()
        results['health']=client.get('/health').json()
        df,targets,w,y,dates,tr,va,te=make_data(ROOT/read(folder/'metadata.json')['source'])
        # A contiguous 41-day historical replay with all 21 targets after the fit cutoff.
        start=pd.Timestamp('2024-12-12');days=pd.date_range(start,periods=41)
        gen=df.gen_kwh.reindex(days).to_numpy()
        forecasts=df.shortwave_radiation_previous_day1.reindex(days+pd.Timedelta(days=1)).to_numpy()
        assert np.isfinite(gen).all() and np.isfinite(forecasts).all()
        batch={'dates':[str(d.date()) for d in days],'prices':gen.tolist(),'volumes':forecasts.tolist(),'expected':[None]*41}
        response=client.post('/predict/batch-test',json=batch);assert response.status_code==200,response.text
        assert len(response.json()['predictions'])==21
        assert response.json()['drift_check']['status']=='skipped'
        assert response.json()['drift_check']['reason']=='aiops_not_configured'
        batchwindows=np.array([np.column_stack([gen[i:i+20],forecasts[i:i+20]]) for i in range(21)])
        np.testing.assert_allclose(response.json()['predictions'],actual.predict_windows(batchwindows),rtol=1e-6,atol=1e-3)
        results['batch']=response.json();dump(dest/'replay_batch_request.json',batch)
        csv=pd.DataFrame({'Date':batch['dates'],'Close':gen,'Volume':forecasts}).to_csv(index=False)
        assert len(validate_csv(csv))==41
        (dest/'replay_upload.csv').write_text(csv,encoding='utf-8')
    # Warm-start capability: update a disposable model on training-only windows.
    scaler=HAICScaler.load(str(folder/'scaler.pkl'))
    s_hash=sha(folder/'scaler.pkl');m_hash=sha(folder/'model.keras')
    warm=tf.keras.models.load_model(folder/'model.keras',compile=False)
    warm.compile(optimizer=tf.keras.optimizers.Adam(1e-4),loss='mse')
    ix=tr[-4:];xx=actual.transform(w[ix]);yy=np.array([scaler.scale_close(v) for v in y[ix]],dtype='float32')
    before=[v.copy() for v in warm.get_weights()]
    warm.train_on_batch(xx,yy)
    changed=any(not np.array_equal(a,b) for a,b in zip(before,warm.get_weights()))
    assert changed and sha(folder/'scaler.pkl')==s_hash and sha(folder/'model.keras')==m_hash
    results['warm_start_smoke']={'passed':True,'training_examples':4,'steps':1,'weights_changed_in_disposable_copy':True,
                                 'saved_model_and_scaler_unchanged':True,'automatic_retraining_tested':False}
    results['passed']=True;results['aiops_policy_connected']=False
    dump(out/'github_api_integration.json',results)
    print(json.dumps(results,ensure_ascii=False))


if __name__=='__main__':main()
