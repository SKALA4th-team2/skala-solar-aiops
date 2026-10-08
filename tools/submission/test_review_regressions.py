"""Review regressions: durable duplicate jobs and per-period training overlap."""
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'project'))
from serving_app import runtime as rt
from serving_app.hourly import policy
from serving_app.hourly.data import replay_scope
import numpy as np

class ReviewRegressions(unittest.TestCase):
    def test_existing_job_status_and_immutable_payload(self):
        start = datetime.fromisoformat('2027-07-11T00:00:00+09:00')
        rows = [dict(timestamp=(start+timedelta(hours=i)).isoformat(), generation_kwh=1) for i in range(696)]
        model = SimpleNamespace(version='1', manifest={'train_end':'2026-02-27T23:00:00+09:00'})
        def inspected(*args):
            return dict(state='drift',reason='forecast_conditioned_drop_and_error'),np.zeros(672),np.zeros(672),[r['timestamp'] for r in rows[24:]]
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'SOLAR_STATE_DIR':tmp}), patch.object(policy,'inspect',side_effect=inspected):
            first = policy.monitor('test',rows,model)
            job_id = first['monitor']['job']['id']
            for status in ['queued','running','succeeded','rejected','failed']:
                with self.subTest(status=status):
                    with rt.db() as conn:conn.execute('UPDATE jobs SET status=? WHERE id=?',(status,job_id))
                    report = policy.monitor('test',rows,model)['monitor']
                    self.assertEqual(report['state'],status)
                    self.assertEqual(report['job']['id'],job_id)
                    if status not in ['queued','running']:self.assertEqual(report['reason'],'existing_job_terminal')
                    with rt.db() as conn:self.assertEqual(conn.execute('SELECT count(*) FROM jobs').fetchone()[0],1)
            altered=[dict(r) for r in rows];altered[30]['generation_kwh']=2
            with self.assertRaisesRegex(ValueError,'different immutable data'):policy.enqueue('test',altered,model,'hourly_drift')

    def test_training_overlap_all_mixed_and_none(self):
        rows=[{'timestamp':f'2026-02-{day}T12:00:00+09:00'} for day in [26,27,28]]
        for end,expected in [('2026-02-28T23:00:00+09:00',3),('2026-02-27T23:00:00+09:00',2),('2026-02-25T23:00:00+09:00',0)]:
            r=replay_scope(rows,end)
            self.assertEqual(r['training_overlap_hours'],expected)
            self.assertEqual(r['total_hours'],3)
        self.assertEqual(replay_scope(rows[-1:],'2026-02-27T23:00:00+09:00')['training_overlap_hours'],0)

if __name__ == '__main__':unittest.main()
