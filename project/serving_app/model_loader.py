"""Verified per-plant bundles; replace cache only after successful loading."""
from collections import OrderedDict
import logging
import math
import os
from pathlib import Path
import threading
from data.features import HAICScaler
from serving_app import runtime as rt
LOCAL_MODEL_PATH='serving_app/models/haic_v1.keras'
SCALER_PATH='serving_app/models/scaler.pkl'
MLFLOW_MODEL_URI='models:/HAIC_Predictor/Production'
_model_cache=None
_models=OrderedDict()
_lock=threading.RLock()

class LoadedModel:
    def __init__(self,keras_model,scaler,version='local',source='local',manifest=None):
        self._keras_model=keras_model;self.scaler=scaler;self.version=str(version);self.source=source;self.manifest=manifest or {}
    def predict_many(self,sequences):
        import numpy as np
        x=np.array([[self.scaler.transform_point(p['close'],p['volume']) for p in seq] for seq in sequences],dtype='float32')
        if x.ndim!=3 or x.shape[1:]!=(20,2) or not np.isfinite(x).all():raise ValueError('Expected finite (N,20,2) input')
        values=self._keras_model(x,training=False).numpy().ravel()
        result=[max(0.,self.scaler.inverse_close(float(z))) for z in values]
        if not all(math.isfinite(z) for z in result):raise ValueError('Nonfinite model prediction')
        return result
    def predict_one(self,sequence):return self.predict_many([sequence])[0]

def load_bundle(plant_id,version):
    if rt.CONTRACT=='solar_hourly_24_jma_day2_v1':
        from serving_app.hourly.model import load_bundle as hourly_bundle
        return hourly_bundle(plant_id,version)
    directory=rt.version_dir(plant_id,version);manifest=rt.read(directory/'manifest.json')
    if manifest['plant_id']!=plant_id or str(manifest['version'])!=str(version) or manifest['contract']!=rt.CONTRACT:
        raise ValueError('Model identity/input contract mismatch')
    if manifest['model_name']!=rt.model_name(plant_id):raise ValueError('Model name mismatch')
    for f in ['model.keras','scaler.pkl']:
        if rt.sha(directory/f)!=manifest['hashes'][f]:raise ValueError('Model/scaler integrity mismatch')
    from tensorflow import keras
    model=keras.models.load_model(directory/'model.keras',compile=False)
    if model.input_shape[1:]!=(20,2):raise ValueError('Model shape mismatch')
    scaler=HAICScaler.load(directory/'scaler.pkl')
    if not all(math.isfinite(v) for v in scaler.__dict__.values()):raise ValueError('Invalid scaler')
    result=LoadedModel(model,scaler,version,'mlflow',manifest)
    result.predict_one([{'close':scaler.close_min,'volume':scaler.volume_min}]*20)
    return result

def _load_from_local():
    for p in [LOCAL_MODEL_PATH,SCALER_PATH]:
        if not Path(p).is_file():raise FileNotFoundError(p)
    from tensorflow import keras
    return LoadedModel(keras.models.load_model(LOCAL_MODEL_PATH,compile=False),HAICScaler.load(SCALER_PATH),'v1-local')
def _load_from_mlflow():
    import mlflow.tensorflow
    return LoadedModel(mlflow.tensorflow.load_model(MLFLOW_MODEL_URI),HAICScaler.load(SCALER_PATH),'legacy-production','mlflow')
def _load_model():return _load_from_mlflow() if os.getenv('MODEL_SOURCE')=='mlflow' else _load_from_local()
def get_model(plant_id=rt.DEFAULT_PLANT):
    global _model_cache
    entry=rt.plant(plant_id)
    with _lock:
        if entry.get('legacy'):
            if _model_cache is None:_model_cache=_load_model()
            return _model_cache
        pointer=rt.current(plant_id);key=(str(rt.root()),plant_id);cached=_models.get(key)
        if cached is None or cached.version!=str(pointer['version']):
            try:new=load_bundle(plant_id,pointer['version'])
            except Exception:
                if cached is None:raise
                logging.getLogger('aiops').exception('plant=%s reload failed; retaining version=%s',plant_id,cached.version)
                return cached
            _models[key]=new
        _models.move_to_end(key)
        while len(_models)>64:_models.popitem(last=False)
        result=_models[key]
        if plant_id==rt.DEFAULT_PLANT:_model_cache=result
        return result
def load_eager():return get_model()
def clear_cache():
    global _model_cache
    with _lock:_models.clear();_model_cache=None
