"""Forecast-conditioned monitoring. This is not an observed-weather facility diagnosis."""
import json,uuid
import numpy as np
from serving_app import runtime as rt
from serving_app.hourly.data import arrays

def inspect(rows,model):
    x,y,times=arrays(rows,model.scaler['capacity_kw']);pred=model.predict_x(x)
    recent=y[-7:];forecast=x[-7:,:,1]*1000
    expected=np.clip(forecast*model.scaler['radiation_coefficient'],0,model.scaler['capacity_kw'])
    mask=forecast>=20;n=int(mask.sum())
    rmse=float(np.sqrt(np.mean((pred[-7:]-recent)**2)))
    ratio=float(recent[mask].sum()/expected[mask].sum()) if n and expected[mask].sum()>0 else None
    # A substantial near-zero daytime run is held for inspection instead of learned.
    outage=((forecast>=150)&(recent<=.1*expected)).ravel();run=0;held=False
    for flag in outage:
        run=run+1 if flag else 0
        if run>=3:held=True
    limit=model.manifest['evaluation']['limit_kwh']
    reason='normal';state='normal'
    if held:state='held';reason='daytime_near_zero_check_data_or_facility'
    elif len(y)<7 or n<48:state='skipped';reason='need_7_complete_days_and_48_daylight_hours'
    elif ratio is not None and ratio<.85 and rmse>limit:
        state='drift';reason='forecast_conditioned_drop_and_error'
    return dict(state=state,reason=reason,rmse_kwh=rmse,daylight_hours=n,reference_ratio=ratio,
                limit_kwh=limit,scope='forecast-conditioned residual; not observed-weather diagnosis'),pred,y,times

def enqueue(pid,rows,model,reason):
    if len(rows)<696:raise ValueError('Retraining needs 29 complete consecutive days (696 hours)')
    rows=rows[-696:]
    if rows[24]['timestamp']<=model.manifest['train_end']:raise ValueError('Retraining targets overlap model training period')
    report,_,_,_=inspect(rows,model)
    if report['state']=='held':raise ValueError('Possible outage: retraining held')
    end=rows[-1]['timestamp'];payload=dict(rows=rows,base_version=model.version,reason=reason,data_sha256=rt.digest(rows))
    with rt.db() as conn:
        old=conn.execute('SELECT * FROM jobs WHERE plant_id=? AND kind=? AND end_date=?',(pid,'hourly_fine_tune',end)).fetchone()
        if old and json.loads(old['payload'])['data_sha256']!=payload['data_sha256']:raise ValueError('Same end timestamp already has different immutable data')
        if not old:
            conn.execute('INSERT INTO jobs(id,plant_id,kind,end_date,status,payload,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)',(uuid.uuid4().hex,pid,'hourly_fine_tune',end,'queued',json.dumps(payload),rt.now(),rt.now()))
        return rt.job_view(conn.execute('SELECT * FROM jobs WHERE plant_id=? AND kind=? AND end_date=?',(pid,'hourly_fine_tune',end)).fetchone())

def monitor(pid,rows,model):
    report,pred,y,times=inspect(rows,model);report.update(plant_id=pid,end_timestamp=times[-1],model_version=model.version)
    if report['state']=='drift':
        try:
            report['job'] = enqueue(pid, rows, model, 'hourly_drift')
            report['state'] = report['job']['status']
            if report['state'] not in ('queued', 'running'):
                report['reason'] = 'existing_job_terminal'
        except ValueError as exc:report['state']='held';report['reason']=str(exc)
    with rt.db() as conn:
        old=conn.execute('SELECT end_date FROM monitoring WHERE plant_id=?',(pid,)).fetchone()
        if old is None or times[-1]>=old['end_date']:
            conn.execute('INSERT OR REPLACE INTO monitoring VALUES(?,?,?)',(pid,times[-1],json.dumps(report)))
    rt.event(pid,'hourly_monitor',report)
    return dict(plant_id=pid,model_version=model.version,predictions=pred.ravel().tolist(),actual=y.ravel().tolist(),timestamps=times,monitor=report)
