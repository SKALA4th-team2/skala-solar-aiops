"""Hourly production API and its same-origin operational dashboard."""
import os
os.environ.setdefault('TF_ENABLE_ONEDNN_OPTS','0');os.environ.setdefault('TF_CPP_MIN_LOG_LEVEL','3')
import tensorflow as tf
tf.config.threading.set_intra_op_parallelism_threads(2);tf.config.threading.set_inter_op_parallelism_threads(1)
from datetime import datetime,timezone
from collections import deque
import json,logging,time,math
from pathlib import Path
from fastapi import FastAPI,HTTPException,UploadFile,File,Form,Query
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from serving_app import runtime as rt,model_loader,registry
from serving_app.hourly.schemas import Predict,Batch,Rollback,Portfolio
from serving_app.hourly.data import parse_csv,rows_for,arrays,sample,replay_scope
from serving_app.hourly.policy import monitor,enqueue
from serving_app.hourly.model import CONTRACT
from serving_app.hourly.incentives import evaluate as evaluate_incentives
import numpy as np

if rt.CONTRACT!=CONTRACT:raise RuntimeError('Set SOLAR_MODEL_CONTRACT='+CONTRACT)
LOG_DIR=rt.configure_logging()
logger=logging.getLogger('aiops');logger.setLevel(logging.INFO)
app=FastAPI(title='SOLAR OPS · 시간별 LSTM',description='전날 실적 24시간 + 대상일 예보 24시간 → 시간별 발전량 24개. KST 구간 시작 시각.')
requests=deque(maxlen=10000)

@app.exception_handler(RequestValidationError)
async def invalid(request,exc):
    return JSONResponse(status_code=422,content={'detail':jsonable_encoder(exc.errors(),custom_encoder={float:lambda v:v if math.isfinite(v) else str(v)})})

@app.middleware('http')
async def measure(request,call_next):
    start=time.perf_counter();response=await call_next(request);requests.append((time.time(),(time.perf_counter()-start)*1000,response.status_code));return response

def plant(pid):
    try:return rt.plant(pid)
    except KeyError:raise HTTPException(404,'등록되지 않았거나 검증에서 제외된 발전소입니다.') from None

def model(pid):
    plant(pid)
    try:return model_loader.get_model(pid)
    except Exception as exc:
        logger.exception('Model unavailable plant=%s',pid)
        raise HTTPException(503,'검증된 시간별 모델을 불러올 수 없습니다.') from exc

@app.get('/plants')
def plants():
    return [dict(p,model_version=rt.current(pid)['version'],ready=True) for pid,p in rt.catalog()['plants'].items()]

@app.get('/health')
def health():
    with rt.db() as conn:row=conn.execute("SELECT * FROM heartbeat WHERE name='worker'").fetchone()
    age=(datetime.now(timezone.utc)-datetime.fromisoformat(row['updated_at'])).total_seconds() if row else None
    alive=age is not None and age<120
    return dict(status='ok' if alive else 'degraded',contract=CONTRACT,interval='1h',forecast_hours=24,worker_alive=alive,worker_heartbeat=dict(row) if row else None,plants=len(rt.catalog()['plants']),execution_unit=os.getenv('EXECUTION_UNIT','local'),demo_mode=os.getenv('SOLAR_DEMO_MODE','0')=='1')

@app.post('/predict')
@app.post('/preview-api/dashboard/predict')
def predict(body:Predict):
    m=model(body.plant_id);d=body.model_dump(mode='json');p=m.predict(d['history'],d['forecast'])
    result=dict(plant_id=body.plant_id,model_version=m.version,contract=CONTRACT,unit='kWh per 1-hour interval',timezone='Asia/Seoul',origin=d['forecast'][0]['timestamp'],predictions=[dict(timestamp=r['timestamp'],predicted_kwh=v) for r,v in zip(d['forecast'],p)],total_kwh=sum(p),forecast_lead_hours=48,publication_cutoff_verified=False)
    return rt.record_prediction(body.plant_id,m.version,d,result)

@app.get('/predictions')
def prediction_history(plant_id:str=rt.DEFAULT_PLANT,limit:int=Query(50,ge=1,le=500)):
    plant(plant_id)
    with rt.db() as conn:
        return [dict(r) for r in conn.execute('SELECT id,plant_id,model_version,kind,origin,input_sha256,created_at FROM predictions WHERE plant_id=? ORDER BY created_at DESC LIMIT ?',(plant_id,limit))]

@app.get('/predictions/{prediction_id}')
def prediction_detail(prediction_id:str):
    with rt.db() as conn:r=conn.execute('SELECT * FROM predictions WHERE id=?',(prediction_id,)).fetchone()
    if r is None:raise HTTPException(404,'저장된 예측이 없습니다.')
    result=dict(r);result['request']=json.loads(result['request']);result['response']=json.loads(result['response']);return result

@app.post('/predict/batch-test')
def batch(body:Batch):
    data=body.model_dump(mode='json');result=monitor(body.plant_id,data['rows'],model(body.plant_id))
    return rt.record_prediction(body.plant_id,result['model_version'],data,result,'retrospective_batch')

@app.get('/ui/sample')
def ui_sample(plant_id:str=rt.DEFAULT_PLANT):
    plant(plant_id)
    try:return sample(plant_id)
    except (ValueError,FileNotFoundError) as exc:raise HTTPException(409,str(exc)) from exc

@app.post('/portfolios/{portfolio_id}/predict')
def portfolio_predict(portfolio_id:str,body:Portfolio):
    portfolio=rt.catalog()['portfolios'].get(portfolio_id)
    if portfolio is None:raise HTTPException(404,'등록되지 않은 포트폴리오입니다.')
    if any(pid not in portfolio['members'] or req.plant_id!=pid for pid,req in body.inputs.items()):raise HTTPException(422,'포트폴리오 구성원과 입력 식별자가 일치해야 합니다.')
    origins={req.forecast[0].timestamp for req in body.inputs.values()}
    if len(origins)!=1:raise HTTPException(422,'모든 개소의 대상 24시간이 같아야 합니다.')
    results=[];missing=[]
    for pid in portfolio['members']:
        if pid not in body.inputs:missing.append(pid);continue
        try:results.append(predict(body.inputs[pid]))
        except HTTPException:missing.append(pid)
    total=[dict(timestamp=r['timestamp'],predicted_kwh=sum(p['predictions'][i]['predicted_kwh'] for p in results)) for i,r in enumerate(results[0]['predictions'])] if results else []
    return dict(portfolio_id=portfolio_id,composition_version=portfolio['version'],complete=not missing,missing=missing,predictions=total if not missing else None,partial_predictions=total,members=results,virtual=True,scope='동일 대상시간 발전량 합계; 시장 제출·정산 검증 아님')

@app.get('/ui/energy')
def energy(plant_id:str=rt.DEFAULT_PLANT):
    m=model(plant_id)
    try:rows,source=rows_for(plant_id,192)
    except (ValueError,FileNotFoundError) as exc:raise HTTPException(409,str(exc)) from exc
    x,y,times=arrays(rows,m.scaler['capacity_kw']);p=m.predict_x(x)
    records=[dict(date=t,timestamp=t,actual=float(a),predicted=float(b),irradiance=float(r['shortwave_radiation'])) for t,a,b,r in zip(times,y.ravel(),p.ravel(),rows[24:])]
    return dict(plant=plant(plant_id),records=records,model_version=m.version,forecast=[dict(timestamp=r['timestamp'],predicted_kwh=r['predicted']) for r in records[-24:]],forecast_total_kwh=sum(r['predicted'] for r in records[-24:]),source=source,quality_scope=replay_scope(records,m.manifest['train_end'])['label'],training_scope=replay_scope(records,m.manifest['train_end']),heldout=m.manifest['evaluation'],incentives={str(hours):dict(evaluate_incentives(records[-hours:],plant(plant_id)['capacity_kw']),training_scope=replay_scope(records[-hours:],m.manifest['train_end'])) for hours in (24,72,168)})

@app.get('/ui/incentives')
def incentives(plant_id:str=rt.DEFAULT_PLANT,hours:int=Query(24,ge=24,le=168),coefficient:float=Query(1)):
    if hours not in (24,72,168) or coefficient not in (1,.5):raise HTTPException(422,'hours: 24/72/168; coefficient: 1/0.5')
    data=energy(plant_id)
    report=evaluate_incentives(data['records'][-hours:],data['plant']['capacity_kw'],coefficient)
    report['training_scope']=data['incentives'][str(hours)]['training_scope']
    return dict(report,plant_id=plant_id,model_version=data['model_version'],data_source=data['source'],quality_scope=report['training_scope']['label'])

@app.post('/data/upload')
async def upload(plant_id:str=Form(...),file:UploadFile=File(...)):
    plant(plant_id);raw=await file.read(5*1024*1024+1)
    if len(raw)>5*1024*1024:raise HTTPException(413,'최대 5MB입니다.')
    try:rows=parse_csv(raw.decode('utf-8-sig'),plant_id)
    except (ValueError,UnicodeError) as exc:raise HTTPException(422,str(exc)) from exc
    path=rt.root()/'uploads'/plant_id/'latest.json'
    try:
        with rt.lock('upload-'+plant_id):
            old=rt.read(path) if path.exists() else None
            if old and rows[-1]['timestamp']<old['rows'][-1]['timestamp']:raise HTTPException(409,'더 오래된 업로드로 교체할 수 없습니다.')
            if old and rows[-1]['timestamp']==old['rows'][-1]['timestamp'] and rt.digest(rows)!=old['sha256']:raise HTTPException(409,'동일 종료 시각의 다른 데이터는 교체할 수 없습니다.')
            rt.write(path,dict(rows=rows,sha256=rt.digest(rows),uploaded_at=rt.now()))
    except RuntimeError:raise HTTPException(409,'다른 업로드가 진행 중입니다.') from None
    result=monitor(plant_id,rows,model(plant_id))
    return dict(plant_id=plant_id,rows=len(rows),start=rows[0]['timestamp'],end=rows[-1]['timestamp'],monitor=result['monitor'])

@app.get('/data/status')
def data_status(plant_id:str=rt.DEFAULT_PLANT):
    plant(plant_id);p=rt.root()/'uploads'/plant_id/'latest.json'
    if not p.exists():return dict(uploaded=False,rows=0)
    d=rt.read(p);return dict(uploaded=True,rows=len(d['rows']),start=d['rows'][0]['timestamp'],end=d['rows'][-1]['timestamp'],uploaded_at=d['uploaded_at'])

@app.get('/jobs')
def jobs(plant_id:str|None=None):
    if plant_id:plant(plant_id)
    with rt.db() as conn:
        return [rt.job_view(r) for r in conn.execute('SELECT * FROM jobs WHERE (? IS NULL OR plant_id=?) ORDER BY created_at DESC LIMIT 100',(plant_id,plant_id))]

@app.get('/jobs/{job_id}')
def job(job_id:str):
    try:return rt.get_job(job_id)
    except KeyError:raise HTTPException(404,'작업이 없습니다.') from None

@app.post('/plants/{plant_id}/retrain',status_code=202)
def retrain(plant_id:str,body:Batch):
    if plant_id!=body.plant_id:raise HTTPException(422,'plant_id mismatch')
    try:return enqueue(plant_id,body.model_dump(mode='json')['rows'],model(plant_id),'manual')
    except ValueError as exc:raise HTTPException(409,str(exc)) from exc

@app.post('/plants/{plant_id}/rollback')
def rollback(plant_id:str,body:Rollback):
    plant(plant_id)
    try:return registry.rollback(plant_id,body.version)
    except FileNotFoundError:raise HTTPException(404,'저장된 버전이 없습니다.') from None
    except (ValueError,RuntimeError) as exc:raise HTTPException(409,str(exc)) from exc

@app.get('/plants/{plant_id}/status')
def status(plant_id:str):
    m=model(plant_id)
    with rt.db() as conn:r=conn.execute('SELECT payload FROM monitoring WHERE plant_id=?',(plant_id,)).fetchone()
    return dict(plant=plant(plant_id),current=rt.current(plant_id),model=m.manifest,monitor=json.loads(r['payload']) if r else None,jobs=jobs(plant_id),upload=data_status(plant_id))

@app.get('/preview-api/operations')
def operations(plant_id:str=rt.DEFAULT_PLANT):return dict(health=health(),plant=status(plant_id),checkedAt=rt.now())

@app.get('/preview-api/dashboard/{resource}')
def dashboard(resource:str,plant_id:str=rt.DEFAULT_PLANT):
    m=model(plant_id)
    if resource=='current':return m.manifest
    if resource=='predictions':return prediction_history(plant_id,50)
    if resource=='history':return [rt.read(p) for p in sorted((rt.plant_dir(plant_id)/'versions').glob('*/manifest.json'),key=lambda p:int(p.parent.name),reverse=True)]
    if resource=='alerts':
        with rt.db() as conn:return [dict(r) for r in conn.execute('SELECT * FROM events WHERE plant_id=? ORDER BY id DESC LIMIT 30',(plant_id,))]
    if resource=='dataset':
        rows,source=rows_for(plant_id);return dict(source=source,rows=len(rows),start=rows[0]['timestamp'],end=rows[-1]['timestamp'],columns=list(rows[0]))
    if resource=='info':return dict(contract=CONTRACT,history_hours=24,forecast_hours=24,timezone='Asia/Seoul',forecast_lead_hours=48,monitor_window_hours=168,retrain_rows=696,weather='regional JMA forecast; observed hourly weather not supplied',live_ingestion=False)
    if resource in ('metrics','timeseries'):
        values=list(requests);return dict(requests=len(values),errors=sum(r[2]>=400 for r in values),mean_latency_ms=sum(r[1] for r in values)/len(values) if values else None,recent=values[-60:])
    raise HTTPException(404,'지원하지 않는 조회입니다.')

@app.get('/logs')
def logs():return ['aiops-hourly.log']

@app.get('/logs/{filename}')
def log(filename:str):
    if filename!='aiops-hourly.log':raise HTTPException(404)
    return dict(filename=filename,content=(LOG_DIR/'aiops-hourly.log').read_text(encoding='utf-8')[-30000:])

app.mount('/',StaticFiles(directory=Path(__file__).resolve().parents[1]/'static',html=True),name='static')
