"""Re-register portable native model seeds in the current runtime filesystem."""
import os
os.environ.setdefault('TF_ENABLE_ONEDNN_OPTS','0');os.environ.setdefault('TF_CPP_MIN_LOG_LEVEL','3')
import tensorflow as tf
tf.config.threading.set_intra_op_parallelism_threads(2)
tf.config.threading.set_inter_op_parallelism_threads(1)
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
import shutil
from data.features import HAICScaler
from serving_app import runtime as rt,registry
def main():
    hourly=rt.CONTRACT=='solar_hourly_24_jma_day2_v1'
    seed=rt.PROJECT/('serving_app/models/hourly-seed' if hourly else 'serving_app/models/runtime-seed')
    with rt.lock():
        if not (rt.root()/'catalog.json').exists():rt.write(rt.root()/'catalog.json',rt.read(seed/'catalog.json'))
        if hourly and (seed/'portfolio_quality.json').exists():
            rt.write(rt.root()/'portfolio_quality.json',rt.read(seed/'portfolio_quality.json'))
        for folder in sorted((seed/'models').iterdir()):
            pid=folder.name
            if (rt.plant_dir(pid)/'current.json').exists():continue
            metadata=rt.read(folder/'manifest.json')
            for file,digest in metadata['hashes'].items():
                if rt.sha(folder/file)!=digest:raise ValueError('Seed integrity failure')
            if not hourly:scaler=HAICScaler.load(folder/'scaler.pkl')
            model=tf.keras.models.load_model(folder/'model.keras',compile=False)
            example=np.zeros((1,24,9) if hourly else (1,20,2),dtype='float32');gate=metadata['gate']
            meta={k:v for k,v in metadata.items() if k not in ['version','hashes','gate','run_id','created_at','model_name','contract']}
            result=registry.register(model,folder/'scaler.pkl',meta,example,gate=gate,kind='portable-seed')
            if hourly:
                target=rt.root()/'history'/f'{pid}.csv';target.parent.mkdir(exist_ok=True);shutil.copy2(seed/'history'/f'{pid}.csv',target)
            else:rt.write(rt.root()/'monitoring_config'/f'{pid}.json',meta['monitoring_config'])
            registry.activate(pid,result['version'],archive=False)
            print('SEEDED',pid,result['version'],flush=True)
            tf.keras.backend.clear_session()
if __name__=='__main__':main()

