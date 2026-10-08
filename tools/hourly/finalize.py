"""Publish only completed hourly quality passes and build a portable verified seed."""
from pathlib import Path
import json,shutil,os
import pandas as pd
import numpy as np
ROOT=Path(__file__).resolve().parents[2]
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def write(p,d):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding='utf-8')
def main():
    evidence=Path(os.getenv('HOURLY_EVIDENCE_DIR',str(ROOT/'docs/proposal/evidence/hourly_20261007')));state=ROOT/'project/data/runtime-hourly';seed=ROOT/'project/serving_app/models/hourly-seed'
    source=read(ROOT/'datasets/hourly/screening.json');approved={};excluded=[]
    for p in source['included']:
        pid=p['plant_id'];result=read(evidence/'plants'/pid/'result.json');evaluation=read(evidence/'plants'/pid/'evaluation.json')
        if not result['gate']['passed']:
            excluded.append(dict(plant_id=pid,name=p['name'],reason='hourly_quality_gate_failed',evaluation=evaluation));continue
        approved[pid]=p;version=read(state/'models'/pid/'current.json')['version'];folder=state/'models'/pid/'versions'/version
        for filename in ['model.keras','scaler.pkl','manifest.json']:
            target=seed/'models'/pid/filename;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(folder/filename,target)
        for target in [state/'history'/f'{pid}.csv',seed/'history'/f'{pid}.csv']:
            target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/p['hourly_file'],target)
    portfolios={'all-approved':dict(version='hourly-20261007-v1',members=list(approved),virtual=True)}
    quality={}
    for name,portfolio in portfolios.items():
        frames=[pd.read_csv(evidence/'plants'/pid/'test_predictions.csv').set_index('timestamp')[['actual_kwh','predicted_kwh']] for pid in portfolio['members']]
        common=frames[0].index
        for frame in frames[1:]:common=common.intersection(frame.index)
        total=sum(frame.loc[common] for frame in frames);err=total.predicted_kwh-total.actual_kwh
        quality[name]=dict(composition_version=portfolio['version'],n_hours=len(common),rmse_kwh=float(np.sqrt(np.mean(err**2))),mae_kwh=float(abs(err).mean()),capacity_kw=sum(p['capacity_kw'] for p in approved.values()),model_versions={pid:read(state/'models'/pid/'current.json')['version'] for pid in approved},scope='2025 aligned hourly sum of held-out evaluation models; virtual portfolio; no settlement claim')
    catalog=dict(plants=approved,portfolios=portfolios,contract='solar_hourly_24_jma_day2_v1')
    write(state/'catalog.json',catalog);write(seed/'catalog.json',catalog)
    write(state/'portfolio_quality.json',quality);write(seed/'portfolio_quality.json',quality);write(evidence/'portfolio_quality.json',quality)
    write(evidence/'summary.json',dict(candidate_count=len(source['included']),approved_count=len(approved),approved=list(approved),excluded=excluded,data_excluded=source['excluded']))
    print('HOURLY APPROVED',len(approved),'EXCLUDED',len(excluded))
if __name__=='__main__':main()
