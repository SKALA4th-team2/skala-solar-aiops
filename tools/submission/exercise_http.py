"""HTTP evidence against a real, isolated API + worker (also used inside Docker CI)."""
import argparse,json,time,urllib.request,urllib.error,csv,io
from datetime import datetime,timedelta
from pathlib import Path
def main():
    p=argparse.ArgumentParser();p.add_argument('--base',default='http://127.0.0.1:8078');p.add_argument('--out',type=Path,required=True);p.add_argument('--check-existing',action='store_true');a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
    def call(path,body=None):
        req=urllib.request.Request(a.base+path,data=json.dumps(body).encode() if body is not None else None,headers={'Content-Type':'application/json'})
        with urllib.request.urlopen(req,timeout=120) as r:return json.load(r)
    def save(name,data):(a.out/name).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    def wait_ready():
        for attempt in range(180):
            try:
                d=call('/health')
                if d['worker_alive'] and d['plants']==31:return d
            except (OSError,ValueError):pass
            time.sleep(2)
        raise RuntimeError('API/worker did not become ready')
    health=wait_ready();save('health.json',health)
    if a.check_existing:
        before=json.loads((a.out/'before.json').read_text(encoding='utf-8'));stored=call('/predictions/'+before['prediction_id'])
        assert stored['response']==before
        save('restart-persistence.json',dict(preserved=True,prediction_id=before['prediction_id'],health=health));print('RESTART PERSISTENCE VERIFIED');return
    assert health['demo_mode'],'Do not inject synthetic drift into production'
    items=call('/plants');assert len(items)==31
    for entry in items:
        pid=entry['plant_id'];s=call('/ui/sample?plant_id='+pid);r=call('/predict',s['prediction']);assert len(r['predictions'])==24
        inc=call('/ui/incentives?plant_id='+pid);assert inc['total_hours']==24 and inc['eligible_hours']+inc['excluded_hours']==24 and not inc['settlement_confirmed']
        assert abs(sum(row['scenario_krw'] for row in inc['rows'])-inc['scenario_krw'])<.011
    pid='hadong-sewage';s=call('/ui/sample?plant_id='+pid);rows=s['batch']['rows'];assert len(rows)==696
    manifest=call('/preview-api/dashboard/current?plant_id='+pid);capacity=manifest['capacity_kw'];coef=manifest['radiation_coefficient']
    start=datetime.fromisoformat('2027-07-11T00:00:00+09:00')
    for i,r in enumerate(rows):r['timestamp']=(start+timedelta(hours=i)).isoformat();r['generation_kwh']=min(capacity,r['shortwave_radiation']*coef)*.5
    request=dict(plant_id=pid,history=[{k:r[k] for k in ['timestamp','generation_kwh']} for r in rows[-48:-24]],forecast=[{k:v for k,v in r.items() if k!='generation_kwh'} for r in rows[-24:]])
    save('input.json',request);before=call('/predict',request);save('before.json',before)
    detail=call('/predictions/'+before['prediction_id']);assert detail['request']==request and detail['response']==before
    try:call('/predict',dict(plant_id=pid,history=request['history'][:-1],forecast=request['forecast']));raise AssertionError('Expected 422')
    except urllib.error.HTTPError as exc:assert exc.code==422;save('invalid-422.json',json.load(exc))
    detected=call('/predict/batch-test',dict(plant_id=pid,rows=rows));save('drift.json',detected);assert detected['monitor']['state']=='queued',detected['monitor']
    job_id=detected['monitor']['job']['id']
    for attempt in range(180):
        job=call('/jobs/'+job_id)
        if job['status'] not in ['queued','running']:break
        time.sleep(2)
    save('job.json',job);assert job['status']=='succeeded',job
    after=call('/predict',request);save('after.json',after);assert before['model_version']!=after['model_version']
    save('registry-history.json',call('/preview-api/dashboard/history?plant_id='+pid))
    save('alerts.json',call('/preview-api/dashboard/alerts?plant_id='+pid));save('worker-log.json',call('/logs/aiops-hourly.log'))
    assert 'hourly_job_finished' in call('/logs/aiops-hourly.log')['content']
    rolled=call('/plants/'+pid+'/rollback',{'version':int(before['model_version'])});save('rollback.json',rolled)
    restored=call('/predict',request);save('restored.json',restored);assert restored['model_version']==before['model_version'] and restored['predictions']==before['predictions']
    save('prediction-history.json',call('/predictions?plant_id='+pid))
    raw=io.StringIO();w=csv.DictWriter(raw,fieldnames=list(s['batch']['rows'][0]));w.writeheader();w.writerows(rows);(a.out/'synthetic-control.csv').write_text(raw.getvalue(),encoding='utf-8')
    save('summary.json',dict(passed=True,scope='isolated synthetic AIOps functionality, not forecast performance',plants_checked=31,before_version=before['model_version'],after_version=after['model_version'],rollback_version=restored['model_version'],prediction_persisted=True,invalid_422=True,worker_log=True,execution_unit=health['execution_unit']))
    print('HTTP LIFECYCLE PASSED',health['execution_unit'],before['model_version'],'->',after['model_version'],'->',restored['model_version'])
if __name__=='__main__':main()
