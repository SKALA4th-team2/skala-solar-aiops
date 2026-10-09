"""Paired immutable hourly scaler and 24-output LSTM bundle."""
import pickle
from datetime import datetime
import numpy as np
from serving_app import runtime as rt
CONTRACT='solar_hourly_24_jma_day2_v1'
FEATURES=['lag24_generation_fraction','radiation_kw_m2','temperature_40c','cloud_fraction','wind_30kmh','hour_sin','hour_cos','year_sin','year_cos']

def features(history,forecast,capacity):
    if len(history)!=24 or len(forecast)!=24:raise ValueError('24 history and forecast hours required')
    result=[]
    for h,w in zip(history,forecast):
        stamp=datetime.fromisoformat(w['timestamp']);hour=stamp.hour+.5;year=stamp.timetuple().tm_yday
        result.append([h['generation_kwh']/capacity,w['shortwave_radiation']/1000,w['temperature_2m']/40,w['cloud_cover']/100,w['wind_speed_10m']/30,np.sin(2*np.pi*hour/24),np.cos(2*np.pi*hour/24),np.sin(2*np.pi*year/365.25),np.cos(2*np.pi*year/365.25)])
    values=np.asarray(result,dtype='float32')
    if not np.isfinite(values).all():raise ValueError('Nonfinite input')
    return values

class HourlyModel:
    def __init__(self,model,scaler,manifest):
        import tensorflow as tf
        self._keras_model=model;self.scaler=scaler;self.manifest=manifest;self.version=str(manifest['version']);self.source='mlflow'
        # Trace once per immutable model version, allowing any batch length.
        self._infer=tf.function(lambda x:model(x,training=False),input_signature=[tf.TensorSpec((None,24,9),tf.float32)])
    def predict_x(self,x):
        x=np.asarray(x,dtype='float32');values=self._infer(x).numpy().reshape(-1,24)*self.scaler['capacity_kw']
        values=np.clip(values,0,self.scaler['capacity_kw']);values[x[:,:,1]<=.001]=0
        if not np.isfinite(values).all():raise ValueError('Nonfinite output')
        return values
    def predict(self,history,forecast):return self.predict_x([features(history,forecast,self.scaler['capacity_kw'])])[0].tolist()

def load_bundle(pid,version):
    from tensorflow import keras
    from serving_app.model_store import ensure_local
    directory=ensure_local(pid,version);m=rt.read(directory/'manifest.json')
    if m['plant_id']!=pid or m['contract']!=CONTRACT or str(m['version'])!=str(version) or m['model_name']!=rt.model_name(pid):raise ValueError('Hourly bundle identity mismatch')
    for name in ['model.keras','scaler.pkl']:
        if rt.sha(directory/name)!=m['hashes'][name]:raise ValueError('Hourly bundle integrity mismatch')
    with (directory/'scaler.pkl').open('rb') as f:s=pickle.load(f)
    if s['contract']!=CONTRACT or s['features']!=FEATURES or s['capacity_kw']!=rt.plant(pid)['capacity_kw']:raise ValueError('Hourly scaler mismatch')
    model=keras.models.load_model(directory/'model.keras',compile=False)
    if model.input_shape[1:]!=(24,9) or model.output_shape[1:]!=(24,1):raise ValueError('Expected hourly 24x9 -> 24x1 model')
    result=HourlyModel(model,s,m);result.predict_x(np.zeros((1,24,9),dtype='float32'));return result

def build_model(coefficient):
    from tensorflow import keras
    inputs=keras.Input(shape=(24,9));base=keras.layers.Dense(1,use_bias=False,trainable=False,name='radiation_reference')
    initial=base(inputs);weights=np.zeros((9,1),dtype='float32');weights[1,0]=coefficient;base.set_weights([weights])
    hidden=keras.layers.LSTM(24,return_sequences=True)(inputs)
    hidden=keras.layers.Dense(12,activation='tanh')(hidden)
    residual=keras.layers.Dense(1,kernel_initializer='zeros',bias_initializer='zeros')(hidden)
    output=keras.layers.ReLU(max_value=1.)(keras.layers.Add()([initial,residual]))
    model=keras.Model(inputs,output);model.compile(optimizer=keras.optimizers.Adam(.002),loss='mse');return model
