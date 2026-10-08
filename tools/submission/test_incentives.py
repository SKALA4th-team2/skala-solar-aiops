"""Independent numerical examples for the pinned incentive scenario."""
import unittest,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'project'))
from serving_app.hourly.incentives import evaluate

def row(actual,predicted,**kw):return dict(timestamp='2026-02-01T12:00:00+09:00',actual=actual,predicted=predicted,**kw)
class Incentives(unittest.TestCase):
    def test_boundaries_and_eligible_denominator(self):
        r=evaluate([row(10,14),row(10,16),row(10,16.001),row(9.999,9.999)],100)
        self.assertEqual([x['band'] for x in r['rows']],['le4','le6','gt6','excluded'])
        self.assertEqual((r['eligible_hours'],r['excluded_hours'],r['le4_hours'],r['le6_hours']),(3,1,1,2))
        self.assertAlmostEqual(r['le6_pct'],200/3);self.assertEqual(r['scenario_krw'],70)
    def test_absolute_errors_before_averaging(self):
        r=evaluate([row(50,40,predicted_second=60)],100)
        self.assertEqual(r['mean_error_pct'],10);self.assertEqual(r['scenario_krw'],0)
        self.assertEqual(r['forecast_basis'],'two_forecasts')
    def test_no_eligible_hours_is_not_perfect_accuracy(self):
        r=evaluate([row(0,0),row(5,5)],100)
        self.assertIsNone(r['mean_error_pct']);self.assertIsNone(r['le6_pct']);self.assertEqual(r['scenario_krw'],0)
    def test_external_exclusions_and_unavailable_capacity(self):
        r=evaluate([row(50,50,curtailed=True),row(50,50,unavailable=True),row(0,0,valid_capacity_kw=0)],100)
        self.assertEqual(r['excluded_hours'],3);self.assertEqual(r['scenario_krw'],0)
    def test_valid_capacity_is_denominator(self):
        r=evaluate([row(10,13,valid_capacity_kw=50)],100)
        self.assertEqual(r['rows'][0]['error_pct'],6);self.assertEqual(r['scenario_krw'],30)
    def test_coefficient_and_single_forecast_disclosure(self):
        r=evaluate([row(50,50)],100,.5)
        self.assertEqual(r['scenario_krw'],100);self.assertEqual(r['second_forecast_proxy_hours'],1)
        self.assertFalse(r['settlement_confirmed']);self.assertEqual(r['forecast_basis'],'single_forecast_proxy')
    def test_invalid_inputs_fail(self):
        for capacity in [0,-1,float('inf')]:
            with self.assertRaises(ValueError):evaluate([row(10,10)],capacity)
        for r in [row(-1,1),row(1,float('nan')),row(1,1,valid_capacity_kw=101)]:
            with self.assertRaises(ValueError):evaluate([r],100)
        with self.assertRaises(ValueError):evaluate([row(10,10)],100,2)
    def test_24_hour_money_reconciliation(self):
        r=evaluate([row(0,0)]*12+[row(40,44)]*6+[row(40,45)]*6,100)
        self.assertEqual(r['eligible_hours'],12);self.assertEqual(r['scenario_krw'],1680)
        self.assertEqual(r['scenario_krw'],sum(x['scenario_krw'] for x in r['rows']))
if __name__=='__main__':unittest.main()
