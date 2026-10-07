"""Register native TensorFlow LSTM models with their paired scaler as extra files."""
import os
os.environ.setdefault('TF_ENABLE_ONEDNN_OPTS','0')
os.environ.setdefault('TF_CPP_MIN_LOG_LEVEL','2')
os.environ.setdefault('MLFLOW_DISABLE_AGENT_HINT','1')
import tensorflow as tf
tf.config.threading.set_intra_op_parallelism_threads(2)
tf.config.threading.set_inter_op_parallelism_threads(1)
import argparse
import importlib.metadata
import sys
from pathlib import Path
import numpy as np
import mlflow
import mlflow.tensorflow
from mlflow.tracking import MlflowClient
from mlflow.models import infer_signature
from bundle import ForecastModel, CONTRACT
from train import ROOT,DEFAULT,read,dump,sha,now


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--out',default=DEFAULT);ap.add_argument('--plant');args=ap.parse_args()
    out=ROOT/args.out;store=out/'mlflow';store.mkdir(exist_ok=True)
    uri='sqlite:///'+(store/'mlflow.db').as_posix();mlflow.set_tracking_uri(uri)
    client=MlflowClient();name='solar-forecast-native-lstm'
    existing=client.get_experiment_by_name(name)
    eid=existing.experiment_id if existing else client.create_experiment(name,artifact_location=(store/'artifacts').as_uri())
    requirements=[f'{k}=={importlib.metadata.version(k)}' for k in ['tensorflow','keras','numpy','cloudpickle']]
    index=read(out/'registry_index.json')['models'] if (out/'registry_index.json').exists() else []
    results=sorted((out/'plants').glob('*/result.json'))
    if args.plant:results=[p for p in results if p.parent.name==args.plant]
    for result_path in results:
        dest=result_path.parent;pid=dest.name;result=read(result_path)
        for role,alias in [('evaluation','replay'),('release','candidate')]:
            folder=dest/role;meta=read(folder/'metadata.json');fingerprint=sha(folder/'bundle_hashes.json')
            if any(r['plant_id']==pid and r['role']==role and r['bundle_sha256']==fingerprint for r in index):continue
            packaged=ForecastModel(folder);request=read(dest/f'{role}_request.json')
            window=np.array([[[r['close'],r['volume']] for r in request['sequence']]])
            scaled=packaged.transform(window)
            keras_model=tf.keras.models.load_model(folder/'model.keras',compile=False)
            expected=keras_model.predict(scaled,verbose=0)
            registered_name=f'SolarForecast_{pid}_LSTM'
            with mlflow.start_run(experiment_id=eid,run_name=f'{pid}-{role}') as run:
                mlflow.set_tags({'plant_id':pid,'role':role,'input_contract':CONTRACT,'publication_cutoff_verified':'false'})
                mlflow.log_params({'seed':42,'epochs':meta['lstm_epochs'],'trained_through':meta['trained_targets']['last'],
                                   'source_sha256':meta['source_sha256'],'github_main':meta['github_main']})
                if role=='evaluation':
                    mlflow.log_metrics({k:v for k,v in result['test_metrics']['LSTM'].items() if k!='n'})
                else:
                    mlflow.set_tag('evaluation_metrics_apply_to','separate replay version, not this all-data refit')
                for file in ['result.json','frozen_selection.json',f'{role}_reload_check.json']:
                    mlflow.log_artifact(str(dest/file),'evidence')
                logged=mlflow.tensorflow.log_model(keras_model,name='model',
                    signature=infer_signature(scaled,expected),input_example=scaled,pip_requirements=requirements,
                    extra_files=[str(folder/f) for f in ['scaler.pkl','scaler.json','metadata.json','bundle_hashes.json']],
                    metadata={'plant_id':pid,'role':role,'input_contract':CONTRACT,'input_space':'scaled','output_space':'scaled_generation'})
                version=mlflow.register_model(logged.model_uri,registered_name)
                client.set_model_version_tag(registered_name,version.version,'role',role)
                client.set_model_version_tag(registered_name,version.version,'bundle_sha256',fingerprint)
                client.set_registered_model_alias(registered_name,alias,version.version)
                model_uri=f'models:/{registered_name}/{version.version}'
                # Use the same native loader family that the team's fine_tune() uses.
                reloaded=mlflow.tensorflow.load_model(model_uri)
                actual=reloaded.predict(scaled,verbose=0)
                np.testing.assert_allclose(actual,expected,rtol=1e-6,atol=1e-6)
                record=dict(plant_id=pid,role=role,registered_name=registered_name,version=version.version,alias=alias,
                            model_uri=model_uri,run_id=run.info.run_id,bundle_sha256=fingerprint,
                            tensorflow_flavor=True,reload_passed=True,registered_utc=now())
                index.append(record);dump(out/'registry_index.json',{'tracking_uri':uri,'experiment_id':eid,'models':index,'production_promoted':False})
                print('REGISTERED',pid,role,version.version,flush=True)
                tf.keras.backend.clear_session()


if __name__=='__main__':main()
