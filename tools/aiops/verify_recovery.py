"""Isolated crash-recovery, interprocess locking and aggregate screening checks."""
import os
os.environ.setdefault('TF_ENABLE_ONEDNN_OPTS','0')
os.environ.setdefault('TF_CPP_MIN_LOG_LEVEL','3')
from pathlib import Path
import sys,tempfile,subprocess,json
from datetime import date,timedelta
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'project'))
from serving_app import runtime as rt

def main():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        os.environ['SOLAR_STATE_DIR']=tmp
        from serving_app.monitoring.worker import recover
        rt.write(rt.root()/'catalog.json',{'plants':{'test-plant':{'plant_id':'test-plant','capacity_kw':55}},'portfolios':{'test-vpp':{'version':'1','members':['test-plant']}}})
        a=rt.enqueue('test-plant',[{'date':'2025-01-01'}],'1')
        b=rt.enqueue('test-plant',[{'date':'2025-01-02'}],'1')
        with rt.db() as conn:
            conn.execute("UPDATE jobs SET status='running',attempts=1 WHERE id=?",(a['id'],))
            conn.execute("UPDATE jobs SET status='running',attempts=2 WHERE id=?",(b['id'],))
        with rt.lock():recover()
        assert rt.get_job(a['id'])['status']=='queued'
        assert rt.get_job(b['id'])['status']=='failed'
        code="from serving_app import runtime as rt\nwith rt.lock('worker'): print('acquired')"
        with rt.lock('worker'):
            child=subprocess.run([sys.executable,'-X','utf8','-c',code],cwd=ROOT/'project',capture_output=True,text=True,encoding='utf-8')
            assert child.returncode!=0 and 'Another worker' in child.stderr
        child=subprocess.run([sys.executable,'-X','utf8','-c',code],cwd=ROOT/'project',capture_output=True,text=True,encoding='utf-8')
        assert child.returncode==0,child.stderr
        from serving_app.routers.operations import portfolio_monitor
        rows=[dict(date=str(date(2025,1,1)+timedelta(days=i)),close=100.,expected=100.) for i in range(41)]
        def save():
            predictions=[dict(date=r['date'],actual=r['close'],predicted=100.,expected=100.) for r in rows[-21:]]
            with rt.db() as conn:conn.execute('INSERT OR REPLACE INTO windows VALUES(?,?,?)',('test-plant',rows[-1]['date'],json.dumps(dict(rows=rows,predictions=predictions,baseline=1.))))
        save();result=portfolio_monitor('test-vpp');assert result['valid_days']==21 and result['deviation_pct']==0
        for r in rows[-10:]:r['close']=0
        save();result=portfolio_monitor('test-vpp');assert result['valid_days']<15 and result['deviation_pct'] is None
        rt.write(ROOT/'docs/proposal/evidence/aiops_backend_20261007/recovery.json',dict(passed=True,interrupted_job_retry=True,retry_limit=True,interprocess_lock=True,aggregate_facility_screen=True))
        print('RECOVERY AND AGGREGATE CHECKS PASSED')
if __name__=='__main__':main()
