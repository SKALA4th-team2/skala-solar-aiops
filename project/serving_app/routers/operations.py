"""Headless plant, job, rollback and portfolio operations."""
from datetime import timedelta
import json
from fastapi import APIRouter,HTTPException
from pydantic import BaseModel,ConfigDict,Field
from serving_app import runtime as rt,model_loader
from serving_app.schemas import BatchTestRequest,PredictRequest,DailyPoint
from serving_app.routers.predict import get_ready_model
from serving_app.monitoring.policy import classify,performance_index

router=APIRouter()

def require_plant(pid):
    try:return rt.plant(pid)
    except KeyError:raise HTTPException(404,'등록되지 않은 발전소입니다.') from None

@router.get('/plants')
def plants():
    result=[]
    for pid,entry in rt.catalog()['plants'].items():
        try:version=rt.current(pid)['version']
        except FileNotFoundError:version=None
        result.append(dict(entry,ready=version is not None,model_version=version))
    return result

@router.post('/plants/{plant_id}/predict/latest')
def predict_latest(plant_id):
    require_plant(plant_id)
    from data.storage import latest_upload
    from serving_app.routers.data import validate_csv,UPLOAD_DIR
    from serving_app.routers.predict import predict
    from pathlib import Path
    try:
        path=latest_upload(UPLOAD_DIR,plant_id=plant_id)
        rows=validate_csv(Path(path).read_text(encoding='utf-8-sig'),plant_id)[-20:]
    except FileNotFoundError:raise HTTPException(409,'해당 발전소의 업로드가 없습니다.') from None
    except ValueError as exc:raise HTTPException(409,str(exc)) from exc
    return predict(PredictRequest(plant_id=plant_id,sequence=[dict(date=r['Date'],close=r['Close'],volume=r['Volume']) for r in rows]))

@router.get('/plants/{plant_id}/status')
def plant_status(plant_id):
    entry=require_plant(plant_id)
    try:pointer=rt.current(plant_id);manifest=rt.read(rt.version_dir(plant_id,pointer['version'])/'manifest.json')
    except FileNotFoundError:pointer=None;manifest=None
    with rt.db() as conn:
        monitor=conn.execute('SELECT payload FROM monitoring WHERE plant_id=?',(plant_id,)).fetchone()
        jobs=[rt.job_view(r) for r in conn.execute('SELECT * FROM jobs WHERE plant_id=? ORDER BY created_at DESC LIMIT 10',(plant_id,))]
    from serving_app.routers.data import status
    return dict(**entry,current=pointer,model=manifest,upload=status(plant_id),monitor=json.loads(monitor['payload']) if monitor else None,jobs=jobs)

@router.get('/jobs')
def jobs():
    with rt.db() as conn:return [rt.job_view(r) for r in conn.execute('SELECT * FROM jobs ORDER BY created_at DESC LIMIT 100')]

@router.get('/jobs/{job_id}')
def job(job_id):
    try:return rt.get_job(job_id)
    except KeyError:raise HTTPException(404,'작업을 찾을 수 없습니다.') from None

@router.post('/plants/{plant_id}/retrain',status_code=202)
def retrain(plant_id,request: BatchTestRequest):
    entry=require_plant(plant_id)
    if request.plant_id!=plant_id:raise HTTPException(422,'본문과 경로의 plant_id가 다릅니다.')
    model=get_ready_model(plant_id)
    if len(request.dates)<41:raise HTTPException(422,'최소 41행이 필요합니다.')
    rows=[dict(date=str(d),close=c,volume=v,expected=e) for d,c,v,e in zip(request.dates,request.prices,request.volumes,request.expected)][-41:]
    if not all(f['valid'] for f in classify(rows,entry['capacity_kw'])):raise HTTPException(409,'설비 정지·보류 또는 기대 발전량 결측으로 재학습을 보류합니다.')
    if rows[20]['date']<=model.manifest['train_end']:raise HTTPException(409,'모델 학습 기간과 재학습 대상일이 겹칩니다.')
    return rt.enqueue(plant_id,rows,model.version,'manual')

class RollbackRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    version:int=Field(ge=1)

@router.post('/plants/{plant_id}/rollback')
def rollback(plant_id,request:RollbackRequest):
    require_plant(plant_id)
    from serving_app.registry import rollback
    try:return rollback(plant_id,request.version)
    except FileNotFoundError:raise HTTPException(404,'저장된 모델 버전이 없습니다.') from None
    except (RuntimeError,ValueError):raise HTTPException(409,'현재 작업 또는 모델 검증 상태 때문에 변경할 수 없습니다.') from None

@router.post('/plants/{plant_id}/baseline')
def baseline(plant_id,request:BatchTestRequest):
    entry=require_plant(plant_id)
    if request.plant_id!=plant_id:raise HTTPException(422,'본문과 경로의 plant_id가 다릅니다.')
    if len(request.dates)<365:raise HTTPException(422,'기준선 재설정에는 최소 365일이 필요합니다.')
    if not entry.get('capacity_kw'):raise HTTPException(409,'설비용량 확인 후 기준선을 설정할 수 있습니다.')
    rows=[dict(date=str(d),close=c,expected=e) for d,c,e in zip(request.dates,request.prices,request.expected)][-365:]
    pi,n=performance_index(rows,classify(rows,entry['capacity_kw']))
    if n<180 or pi is None:raise HTTPException(409,'기준선의 유효한 관측 일수가 부족합니다.')
    try:
        with rt.lock():
            path=rt.root()/'monitoring_config'/f'{plant_id}.json';config=rt.read(path)
            config.update(baseline_pi=pi,baseline_valid_days=n,baseline_start=rows[0]['date'],baseline_end=rows[-1]['date'])
            rt.write(path,config)
    except RuntimeError:raise HTTPException(409,'다른 운영 작업이 진행 중입니다.') from None
    except FileNotFoundError:raise HTTPException(409,'초기 기준선 구성이 없습니다.') from None
    rt.event(plant_id,'baseline_reset',config)
    return config

class PortfolioRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    sequences:dict[str,list[DailyPoint]]=Field(max_length=200)

@router.post('/portfolios/{portfolio_id}/predict')
def portfolio_predict(portfolio_id,request:PortfolioRequest):
    portfolio=rt.catalog()['portfolios'].get(portfolio_id)
    if portfolio is None:raise HTTPException(404,'등록되지 않은 포트폴리오입니다.')
    if any(pid not in portfolio['members'] for pid in request.sequences):raise HTTPException(422,'구성원이 아닌 발전소가 포함되었습니다.')
    target=None;results=[];missing=[];total=0.;known_capacity=0.;included_capacity=0.
    for pid in portfolio['members']:
        entry=rt.plant(pid);known_capacity+=entry.get('capacity_kw') or 0
        if pid not in request.sequences:missing.append(dict(plant_id=pid,reason='input_missing'));continue
        try:
            req=PredictRequest(plant_id=pid,sequence=request.sequences[pid])
        except ValueError as exc:raise HTTPException(422,str(exc)) from exc
        day=req.sequence[-1].date+timedelta(days=1)
        if target is not None and day!=target:raise HTTPException(422,'구성원의 예측 대상일이 같아야 합니다.')
        target=day
        try:model=get_ready_model(pid)
        except HTTPException as exc:missing.append(dict(plant_id=pid,reason='model_unavailable',status_code=exc.status_code));continue
        value=model.predict_one([dict(close=p.close,volume=p.volume) for p in req.sequence]);total+=value;included_capacity+=entry['capacity_kw']
        results.append(dict(plant_id=pid,predicted_kwh=value,model_version=model.version))
    complete=not missing
    quality=rt.root()/'portfolio_quality.json'
    quality=rt.read(quality).get(portfolio_id) if quality.exists() else None
    verified=bool(complete and quality is not None and quality['passed']
        and quality['composition_version']==portfolio['version']
        and set(quality['model_versions'])==set(portfolio['members'])
        and all(quality['model_versions'].get(r['plant_id'])==r['model_version'] for r in results))
    return dict(portfolio_id=portfolio_id,composition_version=portfolio['version'],target_date=target,
                status='complete' if complete else 'partial',complete=complete,total_predicted_kwh=total if complete else None,
                partial_predicted_kwh=total,capacity_coverage=included_capacity/known_capacity if known_capacity else None,
                capacity_unknown=[pid for pid in portfolio['members'] if not rt.plant(pid).get('capacity_kw')],
                members=results,missing=missing,quality_verified=verified,virtual=True)

@router.get('/portfolios/{portfolio_id}/monitor')
def portfolio_monitor(portfolio_id):
    p=rt.catalog()['portfolios'].get(portfolio_id)
    if p is None:raise HTTPException(404,'등록되지 않은 포트폴리오입니다.')
    with rt.db() as conn:windows={r['plant_id']:dict(r) for r in conn.execute('SELECT * FROM windows')}
    missing=[pid for pid in p['members'] if pid not in windows]
    if missing:return dict(complete=False,missing=missing,reason='monitoring_window_missing')
    if len({windows[pid]['end_date'] for pid in p['members']})!=1:return dict(complete=False,reason='dates_misaligned')
    payloads=[json.loads(windows[pid]['payload']) for pid in p['members']]
    dates=[r['date'] for r in payloads[0]['predictions']]
    if any([r['date'] for r in w['predictions']]!=dates for w in payloads):return dict(complete=False,reason='dates_misaligned')
    from serving_app.monitoring.policy import metrics
    actual=[sum(w['predictions'][i]['actual'] for w in payloads) for i in range(21)]
    predicted=[sum(w['predictions'][i]['predicted'] for w in payloads) for i in range(21)]
    expected_valid=all(w['baseline'] and all(r.get('expected') is not None and r['expected']>0 for r in w['predictions']) for w in payloads)
    deviation=None
    valid_indices=[]
    if expected_valid and all(len(w.get('rows',[]))==41 for w in payloads):
        flags=[classify(w['rows'],rt.plant(pid)['capacity_kw'])[-21:] for pid,w in zip(p['members'],payloads)]
        valid_indices=[i for i in range(21) if all(f[i]['valid'] for f in flags)]
    if len(valid_indices)>=15:
        selected=[(w,w['predictions'][i]) for w in payloads for i in valid_indices]
        denominator=sum(r['expected']*w['baseline'] for w,r in selected)
        numerator=sum(min(max(r['actual'],.5*r['expected']),1.5*r['expected']) for w,r in selected)
        deviation=100*(numerator/denominator-1)
    return dict(complete=True,end_date=dates[-1],metrics=metrics(actual,predicted),deviation_pct=deviation,valid_days=len(valid_indices),
                scope='same-date sum, post-observation monitoring; not settlement accuracy')
