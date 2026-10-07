"""Independent standard-library audit of the saved comparison artifacts.

Recompute errors from daily predictions, verify target/forecast alignment,
ensemble arithmetic, scaler cutoffs, frozen selection and unchanged input hashes.
Does not train or import the serving app or the benchmark implementation.
"""
import csv
import hashlib
import json
import math
from datetime import datetime
from pathlib import Path
import argparse

ROOT = Path(__file__).resolve().parents[2]


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--out',default='docs/proposal/evidence/model_benchmark_20261007')
    args=ap.parse_args(); out=ROOT/args.out
    def read(name):
        with (out/name).open(encoding='utf-8',newline='') as f:
            return list(csv.DictReader(f))
    def js(name):
        return json.loads((out/name).read_text(encoding='utf-8'))
    def close(a,b):
        assert math.isclose(float(a),float(b),rel_tol=1e-7,abs_tol=2e-5),(a,b)
    checks=[]
    manifest=read('split_manifest.csv')
    groups={k:[r['date'] for r in manifest if r['split']==k] for k in ['train','validation','test']}
    assert [len(v) for v in groups.values()]==[772,180,365]
    assert max(groups['train'])<min(groups['validation'])
    assert max(groups['validation'])<min(groups['test'])
    dates=[datetime.fromisoformat(r['date']) for r in manifest]
    assert all((b-a).days==1 for a,b in zip(dates,dates[1:]))
    checks.append('Three ordered, disjoint target splits and 1317 consecutive target dates')
    with (ROOT/'datasets/hadong_upload_forecast_jma.csv').open(encoding='utf-8-sig') as f:
        source=list(csv.DictReader(f))
    positions={r['Date']:i for i,r in enumerate(source)}
    for r in manifest:
        t=positions[r['date']]
        close(r['target_forecast_mj'],source[t-1]['Volume'])
    checks.append('All target forecasts use Volume[T-1], never Volume[T]')
    final=read('test_predictions.csv')
    assert [r['date'] for r in final]==groups['test']
    for r in final:
        t=positions[r['date']]
        close(r['actual_kwh'],source[t]['Close'])
        expected=sum(float(source[j]['Close']) for j in range(t-7,t))
        denominator=sum(float(source[j-1]['Volume']) for j in range(t-7,t))
        close(r['RuleC'],expected/denominator*float(source[t-1]['Volume']))
    checks.append('Test labels and independently recomputed RuleC match source by date')
    for r in read('test_metrics.csv'):
        actual=[float(q['actual_kwh']) for q in final]
        pred=[float(q[r['model']]) for q in final]
        assert all(math.isfinite(v) and v>=0 for v in pred)
        error=[a-b for a,b in zip(pred,actual)]
        close(r['rmse_kwh'],math.sqrt(sum(e*e for e in error)/len(error)))
        close(r['mae_kwh'],sum(abs(e) for e in error)/len(error))
        close(r['wape_pct'],100*sum(abs(e) for e in error)/sum(actual))
        close(r['bias_pct'],100*sum(error)/sum(actual))
        assert int(r['n'])==365
    checks.append('All reported test metrics independently recomputed from daily forecasts')
    frozen=js('frozen_selection.json')
    freeze=datetime.fromisoformat(frozen['frozen_kst']).timestamp()
    for family in ['LSTM','XGBoost','Prophet']:
        assert freeze<=(out/f'test_{family}.csv').stat().st_mtime
    assert frozen['validation_selected_model']==min(read('validation_metrics.csv'),key=lambda r:float(r['rmse_kwh']))['model']
    for name,w in frozen['ensemble_weights'].items():
        close(sum(w),1);assert min(w)>=0
        for row in final:
            close(row[name],sum(a*float(row[b]) for a,b in zip(w,frozen['weights_order'])))
    seeds=[read(f'test_LSTM_seed{s}.csv') for s in [42,43,44]]
    for j,r in enumerate(final):
        # Keras predictions and their saved mean are float32; summing three
        # separately rounded CSV values in float64 can differ by a few ULPs.
        expected=sum(float(z[j]['prediction_kwh']) for z in seeds)/3
        assert math.isclose(float(r['LSTM']),expected,rel_tol=5e-7,abs_tol=1e-4)
    checks.append('Selection predates final model forecasts; seed averages and frozen ensemble weights match')
    records=js('runtime_lstm.json')
    cut=max(groups['validation']);last=positions[cut]
    c=[float(z['Close']) for z in source[:last+1]]
    v=[float(z['Volume']) for z in source[:last]]
    for r in records:
        assert r['scaler_last_generation_date']==cut
        assert r['scaler_last_forecast_row']==source[last-1]['Date']
        for observed,expected in zip(r['scaler_min'],[min(c),min(v)]):close(observed,expected)
        for observed,expected in zip(r['scaler_range'],[max(c)-min(c),max(v)-min(v)]):close(observed,expected)
    checks.append('Final LSTM scalers fit only pre-test generation and forecast rows')
    for p,h in js('input_hashes.json').items():
        assert hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h,p
    checks.append('All snapshotted original app/data files unchanged')
    result={'status':'PASS','checks':checks,'checked_input_files':len(js('input_hashes.json'))}
    (out/'independent_audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
