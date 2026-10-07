"""Read-only independent T6/T7 audit. Usage: python t6t7_independent.py REPO."""
from pathlib import Path
import argparse
import hashlib
import json
import numpy as np
import pandas as pd

ap = argparse.ArgumentParser()
ap.add_argument('repo', type=Path)
args = ap.parse_args()
raw = args.repo / 'datasets/raw/data_15043409.csv'
daily = args.repo / 'datasets/hadong_daily_full.csv'
d = pd.read_csv(raw, encoding='cp949').sort_values('년월일')
idx = pd.to_datetime(d['년월일'])
h = d[[str(i) for i in range(1, 25)]].to_numpy(float)
total = h.sum(axis=1)
years = idx.dt.year.to_numpy()
out = {'source_sha256': {str(x.relative_to(args.repo)): hashlib.sha256(x.read_bytes()).hexdigest() for x in (raw, daily)}}
out['raw'] = {'rows': len(d), 'max_hour': float(h.max()), 'hours_gt_50': int((h > 50).sum()), 'hours_gt_55': int((h > 55).sum()), 'missing_dates': int(len(pd.date_range(idx.min(), idx.max()))-idx.nunique())}
full = (years >= 2013) & (years <= 2025)
out['upper_bound'] = {'annual_total_kwh_2013_2025': float(total[full].sum()/13), 'annual_eligible_kwh_55': float(h[full][h[full] >= 5.5].sum()/13), 'annual_eligible_max_won_55': float(h[full][h[full] >= 5.5].sum()/13*4), 'share_upper_boundary_pct':55/20000*100, 'strictly_below_boundary_when_aggregate_gt_20mw':True}
valid = total >= 1
out['time_shares'] = {'days_ge_1kwh': int(valid.sum()), 'weighted_pct': {str(t):float(h[valid,:t].sum()/h[valid].sum()*100) for t in (9,10,14,16,17,19,20)}}
train=(idx<'2023-05-31').to_numpy()&valid
test=((idx>='2023-05-31')&(idx<='2025-12-31')).to_numpy()
months=idx.dt.month.to_numpy()
out['partial_total_estimation']={}
for t in (9,14,16,17,19,20):
    coeff=np.array([h[train&(months==m),:t].sum()/h[train&(months==m)].sum() for m in range(1,13)])
    pred=h[:,:t].sum(axis=1)/coeff[months-1]
    error=(pred-total)[test]
    out['partial_total_estimation'][str(t)]={'rmse_kwh':float(np.sqrt(np.mean(error**2))),'wape_pct':float(np.abs(error).sum()/total[test].sum()*100),'monthly_coefficients':coeff.tolist()}
prices = lambda e: np.where(e<=4,4., np.where(e<=6,3.,0.))
for name,start,end in [('T6_asos','2023-05-31','2025-12-31'),('T6_d2','2023-07-17','2026-02-28'),('T7','2023-10-01','2026-02-28')]:
    mask=(idx>=start)&(idx<=end)
    pred=np.vstack([np.full(24,np.nan),h[:-1]])
    elig=mask.to_numpy()[:,None]&(h>=5.5)
    e=np.abs(pred-h)/55*100
    ds=pd.Series(total)
    daily_metrics={}
    for kind,p in [('persist',ds.shift(1)),('ma7',ds.shift(1).rolling(7).mean()),('ma20',ds.shift(1).rolling(20).mean()),('constant',pd.Series(np.repeat(ds[idx<start].mean(),len(ds))))]:
        er=(p.to_numpy()-total)[mask]
        daily_metrics[kind]={'rmse_kwh':float(np.sqrt(np.mean(er**2))),'cap24_pct':float(np.abs(er).mean()/55/24*100),'wape_pct':float(np.abs(er).sum()/total[mask].sum()*100)}
    unit0=float((h[elig]*prices(e[elig])).sum()/h[elig].sum())
    out[name]={'days':int(mask.sum()),'daily':daily_metrics,'hour_fer_pct':float(e[elig].mean()),'single_prediction_unit_won':unit0,'single_prediction_shift1_pct':float(((h[elig]*prices(e[elig]+1)).sum()/h[elig].sum()/unit0-1)*100)}
v=pd.read_csv(daily,parse_dates=['date']).set_index('date')
v=v[v.pi_valid==1]
pre=v.loc['2020-05-18':'2021-05-17']
base=pre.gen_kwh.sum()/pre.pi_expected_kwh.sum()
out['pi_counterfactual']={'base_level':float(base),'periods':{}}
for a,b in [('2021-05-18','2022-05-17'),('2021-05-18','2024-03-27')]:
    x=v.loc[a:b]
    expected=x.pi_expected_kwh.sum()*base
    out['pi_counterfactual']['periods'][f'{a}:{b}']={'valid_days':len(x),'actual_kwh':float(x.gen_kwh.sum()),'counterfactual_difference_kwh':float(expected-x.gen_kwh.sum()),'relative_pct':float((x.gen_kwh.sum()/expected-1)*100)}
# Same error mean, incompatible settlement sensitivities. Equal-energy hours.
out['same_mean_counterexamples']=[]
for errors in ([5.71,5.71],[0.,11.42]):
    a=np.array(errors)
    out['same_mean_counterexamples'].append({'constructed_errors_pct':errors,'mean_error_pct':float(a.mean()),'unit_won':float(prices(a).mean()),'unit_after_add_1pp_won':float(prices(a+1).mean()),'relative_loss_pct':float((prices(a+1).mean()/prices(a).mean()-1)*100),'is_empirical':False})
print(json.dumps(out,ensure_ascii=False,indent=2))
