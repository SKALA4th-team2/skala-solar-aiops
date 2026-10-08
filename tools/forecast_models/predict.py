"""Run a saved plant bundle against 20 dated, unscaled API input rows."""
import os
os.environ.setdefault('TF_ENABLE_ONEDNN_OPTS', '0')
os.environ.setdefault('TF_CPP_MIN_LOG_LEVEL', '2')
import tensorflow as tf
tf.config.threading.set_intra_op_parallelism_threads(2)
tf.config.threading.set_inter_op_parallelism_threads(1)
import argparse
from datetime import date, timedelta
import json
import numpy as np
import pandas as pd
from bundle import ForecastModel
from train import ROOT, DEFAULT, read, tabular


def predict(directory, request, model_name='LSTM'):
    bundle = ForecastModel(directory)
    sequence = request['sequence']
    if len(sequence) != 20:
        raise ValueError('Exactly 20 daily rows required')
    days = [date.fromisoformat(r['date']) for r in sequence]
    if any(b-a != timedelta(days=1) for a,b in zip(days,days[1:])):
        raise ValueError('Dates must be consecutive and oldest first')
    target = days[-1] + timedelta(days=1)
    window = np.array([[[r['close'],r['volume']] for r in sequence]], dtype=float)
    # Validate units and ranges for every model, including the comparators.
    bundle.transform(window)
    requested = bundle.metadata['selected_by_validation'] if model_name == 'selected' else model_name
    x,p,bases = tabular(window,pd.DatetimeIndex([target]))
    values = {key:float(v[0]) for key,v in bases.items()}
    values['LSTM'] = bundle.predict_one(sequence)
    if requested not in values:
        from xgboost import XGBRegressor
        from prophet.serialize import model_from_json
        xgb = XGBRegressor(n_jobs=2)
        xgb.load_model(bundle.directory/'xgboost.ubj')
        values['XGBoost'] = float(max(xgb.predict(x)[0],0))
        prophet = model_from_json((bundle.directory/'prophet.json').read_text(encoding='utf-8'))
        values['Prophet'] = float(max(prophet.predict(p).yhat.iloc[0],0))
        for key,weights in bundle.metadata['ensemble_weights'].items():
            values[key] = sum(values[name]*weight for name,weight in zip(['LSTM','XGBoost','Prophet'],weights))
    if requested not in values:
        raise ValueError(f'Unknown model: {requested}')
    return dict(plant_id=bundle.metadata['plant_id'],role=bundle.metadata['role'],model=requested,
                model_version=bundle.version,target_date=str(target),predicted_kwh=values[requested])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out',default=DEFAULT)
    parser.add_argument('--plant',default='15043409_u1')
    parser.add_argument('--role',choices=['evaluation','release'],default='evaluation')
    parser.add_argument('--model',choices=['LSTM','XGBoost','Prophet','Ensemble','LSTM_Main_Ensemble','Persistence','Mean7','RuleC','selected'],default='LSTM')
    parser.add_argument('--input',help='JSON file with 20 dated sequence rows; defaults to saved example')
    args = parser.parse_args()
    plant = ROOT/args.out/'plants'/args.plant
    request = read(args.input or plant/f'{args.role}_request.json')
    print(json.dumps(predict(plant/args.role,request,args.model),ensure_ascii=False))


if __name__ == '__main__':
    main()
