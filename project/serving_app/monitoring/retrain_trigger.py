"""Persist plant-specific decisions and immutable deduplicated jobs."""
import json
import logging
import uuid
from serving_app import runtime as rt
from serving_app.monitoring.policy import assess
def evaluate(*,plant_id=rt.DEFAULT_PLANT,rows,predictions,model_version):
    entry=rt.plant(plant_id)
    if entry.get('legacy'):return dict(status='skipped',reason='runtime_not_initialized',model_version=model_version)
    pointer=rt.current(plant_id)
    if str(pointer['version'])!=str(model_version):return dict(status='skipped',reason='model_version_changed',model_version=model_version)
    manifest=rt.read(rt.version_dir(plant_id,model_version)/'manifest.json');end=rows[-1]['date']
    with rt.db() as conn:
        conn.execute('BEGIN IMMEDIATE')
        old=conn.execute('SELECT end_date,payload FROM monitoring WHERE plant_id=?',(plant_id,)).fetchone()
        if old and end<=old['end_date']:
            if end==old['end_date']:
                window=conn.execute('SELECT payload FROM windows WHERE plant_id=?',(plant_id,)).fetchone()
                if window:
                    previous_hash=json.loads(window['payload']).get('input_hash')
                    if previous_hash and previous_hash!=rt.digest(rows):raise ValueError('같은 끝 날짜에 다른 자료가 이미 판정되었습니다. 기존 판정과 작업은 보존됩니다.')
                result=json.loads(old['payload'])
                if result['model_version']==str(model_version):return result
            return dict(status='skipped',reason='stale_or_already_evaluated',model_version=str(model_version))
        configuration=rt.read(rt.root()/'monitoring_config'/f'{plant_id}.json')
        if end<=configuration['baseline_end']:
            return dict(status='skipped',reason='window_not_after_baseline',model_version=str(model_version))
        baseline=configuration.get('baseline_pi')
        result=assess(rows,predictions,capacity_kw=entry['capacity_kw'],baseline=baseline,
                      reference_rmse=manifest['gate']['rmse_kwh'],model_version=model_version)
        if result.get('reason')=='retrain_eligible':
            selected=rows[-41:]
            if selected[20]['date']<=manifest['train_end']:result['reason']='window_overlaps_model_training'
            else:
                job_id=uuid.uuid4().hex
                payload=dict(rows=selected,base_version=str(model_version),reason='drift',data_sha256=rt.digest(selected))
                conn.execute('INSERT OR IGNORE INTO jobs(id,plant_id,kind,end_date,status,payload,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)',
                             (job_id,plant_id,'fine_tune',end,'queued',json.dumps(payload),rt.now(),rt.now()))
                job=conn.execute('SELECT id FROM jobs WHERE plant_id=? AND kind=? AND end_date=?',(plant_id,'fine_tune',end)).fetchone()
                result.update(status='retrain_triggered',job_id=job['id'],reason='queued')
        conn.execute('INSERT INTO monitoring VALUES(?,?,?) ON CONFLICT(plant_id) DO UPDATE SET end_date=excluded.end_date,payload=excluded.payload',
                     (plant_id,end,json.dumps(result)))
        if len(predictions)>=21:
            conn.execute('INSERT OR REPLACE INTO windows VALUES(?,?,?)',(plant_id,end,json.dumps(dict(predictions=predictions[-21:],rows=rows[-41:],baseline=baseline,input_hash=rt.digest(rows)))))
    if result['status']=='retrain_triggered':
        logging.getLogger('aiops').warning('[WARN] drift detected - triggering retrain plant=%s job=%s',plant_id,result['job_id'])
    elif result['status']=='facility_check':
        logging.getLogger('aiops').warning('[WARN] facility check required - retrain held plant=%s outage_days=%s hold_days=%s',plant_id,result.get('outage_days'),result.get('hold_days'))
    elif result['status']=='drift_alerted':
        logging.getLogger('aiops').info('[INFO] retrain waiting - input window not yet below limit plant=%s reason=%s',plant_id,result.get('reason'))
    elif result['status']=='input_anomaly':
        logging.getLogger('aiops').warning('[WARN] input anomaly suspected - rmse21=%s plant=%s',result['rmse21'],plant_id)
    rt.event(plant_id,'monitor',dict(result,end_date=end))
    return result
def check_and_trigger(recent_predictions):
    raise ValueError('Use evaluate() with dated solar rows, expected values and plant identity.')
