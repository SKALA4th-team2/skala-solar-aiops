"""Fault injection only into the isolated runtime made by verify.py."""
import os,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];EVIDENCE=ROOT/'docs/proposal/evidence/hourly_20261007'
evidence=json.loads((EVIDENCE/'verification.json').read_text(encoding='utf-8'));isolated=Path(evidence['isolated_runtime']).resolve()
assert isolated.is_relative_to(EVIDENCE.resolve()) and isolated.name.startswith('runtime-verify-')
os.environ['SOLAR_STATE_DIR']=str(isolated);os.environ['SOLAR_MODEL_CONTRACT']='solar_hourly_24_jma_day2_v1';os.environ['TF_ENABLE_ONEDNN_OPTS']='0';os.environ['TF_CPP_MIN_LOG_LEVEL']='3'
sys.path.insert(0,str(ROOT/'project'))
from serving_app.hourly.worker import recover
from serving_app import runtime as rt,model_loader,registry
pid='hadong-sewage'
original=rt.current(pid);cached=model_loader.get_model(pid);bad=rt.version_dir(pid,'2')/'model.keras';content=bad.read_bytes()
try:
    bad.write_bytes(content[:-16]+b'broken-model-zip!')
    rt.write(rt.plant_dir(pid)/'current.json',dict(original,version='2'))
    assert model_loader.get_model(pid) is cached
    model_loader.clear_cache()
    try:model_loader.get_model(pid);raise AssertionError('Corrupted bundle loaded')
    except ValueError:pass
finally:
    bad.write_bytes(content);rt.write(rt.plant_dir(pid)/'current.json',original);model_loader.clear_cache()
registry.client().set_registered_model_alias(rt.model_name(pid),'champion','1')
ids=[evidence['worker_job']['id'],evidence['automatic_drift_job']['id']]
with rt.db() as conn:
    conn.execute("UPDATE jobs SET status='running',attempts=1 WHERE id=?",(ids[0],))
    conn.execute("UPDATE jobs SET status='running',attempts=2 WHERE id=?",(ids[1],))
recover()
assert rt.get_job(ids[0])['status']=='queued' and rt.get_job(ids[1])['status']=='failed'
assert str(registry.client().get_model_version_by_alias(rt.model_name(pid),'champion').version)==str(original['version'])
with rt.lock('worker'):
    try:
        with rt.lock('worker'):raise AssertionError('Two workers acquired lock')
    except RuntimeError:pass
rt.write(EVIDENCE/'recovery.json',dict(isolated_runtime=str(isolated),corruption_rejected=True,cached_previous_retained=True,registry_alias_reconciled=True,interrupted_job_requeued=True,max_attempts_stopped=True,single_worker_lock=True))
print('VERIFIED corruption fallback, cold-load rejection, recovery, max attempts, single worker, registry reconciliation')
