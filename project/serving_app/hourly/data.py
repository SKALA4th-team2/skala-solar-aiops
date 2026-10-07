"""Read complete contiguous hourly days; uploads and immutable reference data stay separate."""
import csv,io
from datetime import datetime,timedelta
from serving_app import runtime as rt
from serving_app.hourly.schemas import Batch
from serving_app.hourly.model import features
import numpy as np

COLUMNS=['timestamp','generation_kwh','shortwave_radiation','temperature_2m','cloud_cover','wind_speed_10m']

def parse_csv(text,pid):
    reader=csv.DictReader(io.StringIO(text.lstrip('\ufeff')))
    if reader.fieldnames!=COLUMNS:raise ValueError('CSV columns must be: '+','.join(COLUMNS))
    rows=list(reader)
    return Batch(plant_id=pid,rows=rows).model_dump(mode='json')['rows']

def rows_for(pid,limit=696):
    rt.plant(pid);upload=rt.root()/'uploads'/pid/'latest.json'
    if upload.exists():return rt.read(upload)['rows'][-limit:],'uploaded'
    path=rt.root()/'history'/f'{pid}.csv'
    rows=list(csv.DictReader(path.open(encoding='utf-8-sig')))
    # Break at the most recent gap; never concatenate nonadjacent days.
    start=len(rows)-1
    while start>0 and datetime.fromisoformat(rows[start]['timestamp'])-datetime.fromisoformat(rows[start-1]['timestamp'])==timedelta(hours=1):start-=1
    rows=rows[max(start,len(rows)-limit):]
    return Batch(plant_id=pid,rows=rows).model_dump(mode='json')['rows'],'historical_replay'

def arrays(rows,capacity):
    x=[];y=[];times=[]
    for i in range(24,len(rows),24):
        x.append(features(rows[i-24:i],rows[i:i+24],capacity));y.append([r['generation_kwh'] for r in rows[i:i+24]]);times.extend(r['timestamp'] for r in rows[i:i+24])
    return np.asarray(x,dtype='float32'),np.asarray(y),times

def sample(pid):
    rows,source=rows_for(pid)
    history=[{k:r[k] for k in ('timestamp','generation_kwh')} for r in rows[-48:-24]]
    forecast=[{k:v for k,v in r.items() if k!='generation_kwh'} for r in rows[-24:]]
    return dict(plant_id=pid,prediction=dict(plant_id=pid,history=history,forecast=forecast),batch=dict(plant_id=pid,rows=rows),source=source)
