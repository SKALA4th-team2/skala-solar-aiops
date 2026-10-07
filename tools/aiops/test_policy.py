"""Deterministic policy/state boundary checks; these are not performance evidence."""
from pathlib import Path
import sys,tempfile,os,json
from datetime import date,timedelta
import unittest
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'project'))
from serving_app.monitoring.policy import assess,classify,initial_gate
from serving_app import runtime as rt

def rows(factor=1.,n=41):return [dict(date=str(date(2025,1,1)+timedelta(days=i)),close=100*factor,volume=10.,expected=100.) for i in range(n)]
def check(data,prediction=100.):
    pred=[dict(date=r['date'],actual=r['close'],predicted=prediction,expected=r['expected']) for r in data[20:]]
    return assess(data,pred,capacity_kw=55,baseline=1.,reference_rmse=10.,model_version='1')

class PolicyTests(unittest.TestCase):
    def test_normal(self):self.assertEqual(check(rows())['status'],'ok')
    def test_persistent_decline(self):self.assertEqual(check(rows(.86))['reason'],'retrain_eligible')
    def test_head_waiting(self):
        r=rows();r[20:]=rows(.86)[20:];self.assertEqual(check(r)['reason'],'input_window_not_yet_below_limit')
    def test_facility_blocks(self):
        r=rows();r[-1]['close']=0;self.assertEqual(check(r)['status'],'facility_check')
    def test_missing_expected(self):
        r=rows()
        for item in r:item['expected']=None
        self.assertEqual(check(r)['status'],'skipped')
    def test_rmse_only_warns(self):self.assertEqual(check(rows(),200)['status'],'input_anomaly')
    def test_short_window(self):self.assertEqual(check(rows(n=40))['reason'],'insufficient_window')
    def test_capacity_scaled(self):
        flags=classify([dict(r,close=r['close']*10,expected=r['expected']*10) for r in rows(.86)],550)
        self.assertTrue(all(f['valid'] for f in flags))
    def test_gate_minimum_and_bias(self):
        scores=dict(LSTM=dict(n=180,rmse_kwh=20.,bias_pct=0.),Mean7=dict(rmse_kwh=40.),RuleC=dict(rmse_kwh=25.))
        self.assertTrue(initial_gate(scores)['passed']);scores['LSTM']['n']=179;self.assertFalse(initial_gate(scores)['passed'])
        scores['LSTM'].update(n=180,bias_pct=10.1);self.assertFalse(initial_gate(scores)['passed'])
    def test_job_dedup_and_payload_immutable(self):
        with tempfile.TemporaryDirectory() as tmp:
            old=os.environ.get('SOLAR_STATE_DIR');os.environ['SOLAR_STATE_DIR']=tmp
            try:
                a=rt.enqueue('hadong-sewage',rows(),'1');b=rt.enqueue('hadong-sewage',rows(.5),'2')
                self.assertEqual(a['id'],b['id'])
                with rt.db() as conn:payload=json.loads(conn.execute('SELECT payload FROM jobs').fetchone()['payload'])
                self.assertEqual(payload['base_version'],'1');self.assertEqual(payload['rows'][0]['close'],100)
            finally:
                if old is None:os.environ.pop('SOLAR_STATE_DIR')
                else:os.environ['SOLAR_STATE_DIR']=old
if __name__=='__main__':unittest.main(verbosity=2)
