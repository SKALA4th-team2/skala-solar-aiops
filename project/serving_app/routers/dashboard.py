"""Live Solar Ops read models. Historical samples are labeled, never auto-submitted."""
from collections import deque
from datetime import date,datetime,timedelta,timezone
import json,time
from fastapi import APIRouter,HTTPException,Query
from serving_app import runtime as rt
from serving_app.routers.predict import get_ready_model,predict
from serving_app.schemas import PredictRequest
from serving_app.routers.data import status,validate_csv,UPLOAD_DIR
from data.storage import latest_upload
from pathlib import Path

router=APIRouter();requests=deque(maxlen=10000)

def rows_for(pid):
    try:rt.plant(pid)
    except KeyError:raise HTTPException(404,'등록되지 않은 발전소입니다.') from None
    try:
        path=latest_upload(UPLOAD_DIR,plant_id=pid)
        rows=[dict(date=r['Date'],close=r['Close'],volume=r['Volume'],expected=r.get('Expected')) for r in validate_csv(Path(path).read_text(encoding='utf-8-sig'),pid)]
        source='uploaded'
    except FileNotFoundError:
        path=rt.root()/'history'/f'{pid}.json'
        if not path.exists():raise HTTPException(409,'사용 가능한 실적 자료가 없습니다.') from None
        rows=rt.read(path);source='historical_replay'
    # Use the latest complete interval; never stitch across calendar gaps.
    segments=[];segment=[]
    for row in rows:
        if segment and date.fromisoformat(row['date'])-date.fromisoformat(segment[-1]['date'])!=timedelta(days=1):
            segments.append(segment);segment=[]
        segment.append(row)
    segments.append(segment)
    valid=[s for s in segments if len(s)>=41]
    if not valid:raise HTTPException(409,'연속 41일 자료가 없습니다.')
    return valid[-1],source

@router.get('/ui/sample')
def sample(plant_id:str=rt.DEFAULT_PLANT):
    rows,source=rows_for(plant_id);rows=rows[-41:]
    return dict(source=source,plant_id=plant_id,batch=dict(plant_id=plant_id,dates=[r['date'] for r in rows],prices=[r['close'] for r in rows],volumes=[r['volume'] for r in rows],expected=[r.get('expected') for r in rows]),prediction=dict(plant_id=plant_id,sequence=[{k:r[k] for k in ['date','close','volume']} for r in rows[-20:]]))

@router.get('/ui/energy')
def energy(plant_id:str=rt.DEFAULT_PLANT):
    rows,source=rows_for(plant_id);rows=rows[-110:];model=get_ready_model(plant_id)
    predictions=model.predict_many([rows[i-20:i] for i in range(20,len(rows))])
    records=[dict(date=r['date'],measured=r['close'],predicted=p,forecastIrradiance=rows[i-1]['volume']) for i,(r,p) in enumerate(zip(rows[20:],predictions),20)]
    tomorrow=dict(date=str(date.fromisoformat(rows[-1]['date'])+timedelta(days=1)),predicted=model.predict_one(rows[-20:]),forecastIrradiance=rows[-1]['volume'])
    return dict(plant=rt.plant(plant_id),records=records,tomorrow=tomorrow,replayDate=rows[-1]['date'],model_version=model.version,source=source,quality_scope='current-model retrospective predictions; not a held-out performance evaluation')

@router.get('/preview-api/operations')
def operations(plant_id:str=rt.DEFAULT_PLANT):
    from serving_app.routers.health import health
    start=time.perf_counter();h=health(plant_id);u=status(plant_id)
    return dict(checkedAt=rt.now(),health=dict(ok=True,modelLoaded=h['model_loaded'],latencyMs=round((time.perf_counter()-start)*1000)),upload=dict(ok=True,exists=u['exists'],rows=u.get('rows'),startDate=u.get('start_date'),endDate=u.get('end_date')),worker_updated_at=h['worker_updated_at'])

@router.post('/preview-api/dashboard/predict')
def prediction(body:PredictRequest):return predict(body)

@router.get('/preview-api/dashboard/{resource}')
def dashboard(resource:str,plant_id:str=rt.DEFAULT_PLANT,window_sec:int=Query(300,ge=1,le=86400)):
    try:entry=rt.plant(plant_id)
    except KeyError:raise HTTPException(404,'등록되지 않은 발전소입니다.') from None
    if resource=='dataset':return status(plant_id)
    pointer=rt.current(plant_id);manifest=rt.read(rt.version_dir(plant_id,pointer['version'])/'manifest.json')
    if resource=='current':return dict(version=pointer['version'],source='mlflow',name=rt.model_name(plant_id),stage='Production',rmse=manifest['gate']['rmse_kwh'],created_at=manifest['created_at'])
    if resource=='info':return dict(seq_len=20,rmse_gate=manifest['gate']['limit_kwh'],drift_window_size=21,drift_decline_pct=-7.5,fine_tune_epochs=10,fine_tune_lr=.0001,model_source='mlflow',loading_mode='lazy',capacity_kw=entry['capacity_kw'])
    if resource=='history':
        return [dict(version=m['version'],created_at=m['created_at'],mode='fine_tune' if m.get('parent_version') else 'initial',rmse=m['gate']['rmse_kwh'],stage='Production' if m['version']==pointer['version'] else 'Archived') for m in [rt.read(p) for p in sorted((rt.plant_dir(plant_id)/'versions').glob('*/manifest.json'))]]
    if resource=='alerts':
        with rt.db() as conn:events=list(conn.execute('SELECT * FROM events WHERE plant_id=? ORDER BY id DESC LIMIT 100',(plant_id,)))
        return [dict(ts=r['created_at'],level='INFO',message=r['kind']+' · '+r['payload']) for r in events]
    if resource in ['metrics','timeseries']:
        cutoff=time.time()-window_sec;selected=[r for r in list(requests) if r[0]>=cutoff]
        result=dict(request_count=len(selected),avg_latency_ms=sum(r[1] for r in selected)/len(selected) if selected else 0,error_rate=sum(r[2]>=400 for r in selected)/len(selected) if selected else 0,scope='current API process; bounded recent requests')
        return [result] if resource=='timeseries' else result
    raise HTTPException(404,'지원하지 않는 조회 항목입니다.')
