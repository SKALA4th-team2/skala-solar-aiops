"""Same-date aggregate evaluation; never sum individual RMSEs."""
from pathlib import Path
import sys
import pandas as pd
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'project'))
from serving_app import runtime as rt
from serving_app.monitoring.policy import metrics

def main():
    cat=rt.catalog();receipt=rt.read(rt.root()/'bootstrap.json')
    approved=[p for p,r in receipt.items() if r['promoted']]
    cat['portfolios']['approved-vpp']={'version':'20261007-approved','members':approved,'virtual':True}
    cat['portfolios']['hadong-demo']={'version':'20261007-hadong','members':[p for p in approved if p in ['hadong-sewage','15043404-u1','15043405-u1','15043406-u1','15043408-u1']],'virtual':True}
    output={}
    for name,portfolio in cat['portfolios'].items():
        if any(p not in approved for p in portfolio['members']):continue
        frames=[]
        for pid in portfolio['members']:
            source=cat['plants'][pid]['source_id']
            frame=pd.read_csv(ROOT/'docs/proposal/evidence/forecast_models_20261007/plants'/source/'test_predictions.csv').set_index('date')
            frames.append(frame[['actual_kwh','LSTM','Mean7']])
        dates=sorted(set.intersection(*[set(f.index) for f in frames]))
        combined=sum((f.loc[dates] for f in frames))
        model=metrics(combined.actual_kwh.tolist(),combined.LSTM.tolist());base=metrics(combined.actual_kwh.tolist(),combined.Mean7.tolist())
        output[name]=dict(passed=len(dates)>=180 and model['rmse_kwh']<=.8*base['rmse_kwh'] and abs(model['bias_pct'])<=10,
                          model=model,mean7=base,first=dates[0],last=dates[-1],members=len(frames),
                          model_versions={p:rt.current(p)['version'] for p in portfolio['members']},composition_version=portfolio['version'])
    with rt.lock():rt.write(rt.root()/'catalog.json',cat);rt.write(rt.root()/'portfolio_quality.json',output)
    evidence=ROOT/'docs/proposal/evidence/aiops_backend_20261007';rt.write(evidence/'portfolio_quality.json',output)
    print({name:(r['members'],r['passed'],r['model']['rmse_kwh']) for name,r in output.items()})
if __name__=='__main__':main()
