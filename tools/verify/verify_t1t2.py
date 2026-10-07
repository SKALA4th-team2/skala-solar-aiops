"""Independent T1/T2 audit. Read-only inputs; no project imports/network.
Run: python verify_t1t2.py --repo /path/to/repo --output /tmp/result.json
Requires numpy, pandas, scikit-learn. Labels/ASOS are derived, not ground truth.
"""
import argparse, hashlib, json
from pathlib import Path
from decimal import Decimal, ROUND_HALF_UP, ROUND_DOWN
import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge

ap = argparse.ArgumentParser()
ap.add_argument('--repo', type=Path, required=True)
ap.add_argument('--output', type=Path, required=True)
a = ap.parse_args(); root = a.repo
rawp = root/'datasets/raw/data_15043409.csv'
raw = pd.read_csv(rawp, encoding='cp949', dtype=str)
raw.index = pd.to_datetime(raw['년월일']); raw = raw.sort_index()
h = raw[[str(i) for i in range(1,25)]].astype(float)
y = raw['총량(kw)'].astype(float); peak = h.max(axis=1)
full = pd.read_csv(root/'datasets/hadong_daily_full.csv', index_col='date', parse_dates=True)
up = pd.read_csv(root/'datasets/hadong_upload.csv', index_col='Date', parse_dates=True)
ev = pd.read_csv(root/'docs/research/merged/files/T2-history-outage/equipment_events_final.csv', index_col='date', parse_dates=True)
out = {'limits': ['ASOS original station rows absent; full CSV is a derived source.', 'Event labels are retrospective hypotheses, not verified maintenance records.', 'No LSTM retraining: errors recalculated from stored predictions.']}
out['hashes'] = {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in [rawp, root/'datasets/hadong_daily_full.csv', root/'datasets/hadong_upload.csv']}
out['raw'] = dict(rows=len(raw), start=str(raw.index.min().date()), end=str(raw.index.max().date()), missing=len(pd.date_range(raw.index.min(),raw.index.max()).difference(raw.index)), duplicate=int(raw.index.duplicated().sum()), units=sorted(raw['호기'].unique()), sum_max_diff=float((y-h.sum(axis=1)).abs().max()), peak_max_diff=float((raw['최대(kw)'].astype(float)-peak).abs().max()), minimum_max_diff=float((raw['최소(kw)'].astype(float)-h.min(axis=1)).abs().max()), positive_cells=int((h>0).sum().sum()), maximum_hour=float(h.to_numpy().max()), above50_hours=int((h>50).sum().sum()), above50_days=int((h>50).any(axis=1).sum()), above55=int((h>55).sum().sum()), mean=float(y.mean()), median=float(y.median()), maximum_total=float(y.max()), maximum_total_date=str(y.idxmax().date()), zero_days=int((y==0).sum()), small_positive=int(((y>0)&(y<1)).sum()), full_gen_diff=float((full.gen_kwh-y).abs().max()), full_peak_diff=float((full.peak_kw-peak).abs().max()), neighbor_copy_totals={str(d.date()): float(y[d]) for d in pd.date_range('2016-12-27','2016-12-29')})
dec_hours = [[Decimal(v) for v in row] for row in raw[h.columns].to_numpy()]
rules = []
for start,end in [('2013-01-01','2017-02-28'),('2017-03-01','2020-07-31'),('2020-08-01','2022-06-30'),('2022-07-01','2023-03-31'),('2023-04-01','2026-02-28')]:
 ids = np.flatnonzero((raw.index>=start)&(raw.index<=end)); z=[min([v for v in dec_hours[i] if v>0],default=Decimal(0)) for i in ids]
 v=[Decimal(raw.iloc[i]['최소(시간별_kw)']) for i in ids]
 rules.append(dict(start=start,end=end,n=len(ids),exact=sum(x==t for x,t in zip(z,v)),truncate2=sum(x.quantize(Decimal('.01'),rounding=ROUND_DOWN)==t for x,t in zip(z,v)),round1=sum(x.quantize(Decimal('.1'),rounding=ROUND_HALF_UP)==t for x,t in zip(z,v))))
out['minimum_hourly_rules']=rules
mx=[max(v) for v in dec_hours]; mv=[Decimal(v) for v in raw['최대(시간별_kw)']]
out['maximum_hourly']={'exact':sum(x==v for x,v in zip(mx,mv)),'non_exact':sum(x!=v for x,v in zip(mx,mv)),'all_nonexact_truncate2':all(x.quantize(Decimal('.01'),rounding=ROUND_DOWN)==v for x,v in zip(mx,mv) if x!=v)}
out['copy_and_ticks']={'positive_duplicates': [[str(d.date()) for d in grp.index] for _,grp in raw[y>0].groupby(list(raw.columns[2:]),dropna=False) if len(grp)>1], 'non006':[(str(raw.index[i].date()),k+1,str(v)) for i,row in enumerate(dec_hours) for k,v in enumerate(row) if v>0 and v%Decimal('.006')!=0]}
# Independent vector form of the published daily isotropic tilt calculation.
f=full.loc[:'2025-12-31'];doy=f.index.dayofyear.to_numpy(); phi=np.radians(34.94)
delta=.409*np.sin(2*np.pi*doy/365-1.39); dr=1+.033*np.cos(2*np.pi*doy/365)
ws=np.arccos(np.clip(-np.tan(phi)*np.tan(delta),-1,1))
den=np.cos(phi)*np.cos(delta)*np.sin(ws)+ws*np.sin(phi)*np.sin(delta)
h0=24*60/np.pi*.082*dr*den; g=f.gy_gsr_obs.to_numpy();kt=np.clip(g/h0,.01,.85)
fd1=np.where(kt<.715,1-.2727*kt+2.4495*kt**2-11.9514*kt**3+9.3879*kt**4,.143)
fd2=np.where(kt<.722,1+.2832*kt-2.5557*kt**2+.8448*kt**3,.175)
fd=np.where(ws<=np.radians(81.4),fd1,fd2); corrs={}
for tilt in [27,30]:
 b=np.radians(tilt);wsp=np.minimum(ws,np.arccos(np.clip(-np.tan(phi-b)*np.tan(delta),-1,1)))
 rb=(np.cos(phi-b)*np.cos(delta)*np.sin(wsp)+wsp*np.sin(phi-b)*np.sin(delta))/den
 gt=g*(1-fd)*rb+fd*g*(1+np.cos(b))/2+.2*g*(1-np.cos(b))/2
 masks={'train':(f.index<='2022-12-31')&(f.gen_kwh>0)&np.isfinite(g),'test':(f.index>='2023-01-01')&(f.gen_kwh>0)&np.isfinite(g)}
 corrs[str(tilt)]={name:{'n':int(m.sum()),'r':float(np.corrcoef(gt[m],f.gen_kwh[m])[0,1])} for name,m in masks.items()}
out['tilt_correlations']=corrs
out['annual_cf55']={str(yr): float(vals.sum()/(55*24*len(vals))*100) for yr,vals in y.loc[:'2025-12-31'].groupby(y.loc[:'2025-12-31'].index.year)}
out['eligible55']={'mean_hours':float((h>=5.5).sum(axis=1).mean()),'energy_percent':float(h.where(h>=5.5,0).sum().sum()/y.sum()*100)}
out['uploads']={'rows':len(up),'close_diff':float((up.Close-y.reindex(up.index)).abs().max()), 'missing':[str(d.date()) for d in raw.index.difference(up.index)],'stop43':int(up.Stop.sum()), 'extra_vs_D1_40':[str(d.date()) for d in up.index[(up.Stop==1)&~up.index.isin(ev.index[ev.in_D1_40==1])]]}
out['events']={'rows':len(ev),'by_category':ev.category.value_counts().to_dict(),'stored_gen_diff':float((ev.gen_kwh-y.reindex(ev.index)).abs().max())}
seq=np.arange(20,len(up)); cut=int(len(seq)*.8)
sample_masks={}
for name,days in [('zero24', y.index[y==0]),('stop43',up.index[up.Stop==1]),('stop50',ev.index[ev.stop_50==1]),('all65',ev.index),('test16',ev.index[ev.index>=up.index[seq[cut]]])]:
 mask=np.array([bool(up.index[t-20:t+1].isin(days).any()) for t in seq])
 sample_masks[name]={'total':int(mask.sum()),'train':int(mask[:cut].sum()),'test':int(mask[cut:].sum())}
out['sample_overlap']={'test_start':str(up.index[seq[cut]].date()),'test_end':str(up.index[-1].date()),'test_n':len(seq)-cut,'masks':sample_masks}
# Fixed capacity normalization is a positive rescaling of MAE: identical ordering.
idx=np.arange(20,len(y)); split=int(len(idx)*.8)
x=np.stack([y.to_numpy()[i-20:i] for i in idx])/380
model=Ridge(alpha=1).fit(x[:split],y.iloc[idx[:split]])
p=model.predict(x); actual=y.iloc[idx].to_numpy(); mae=np.abs(p[split:]-actual[split:]).mean()
out['ridge']={'mae':float(mae),'daily_capacity55_percent':float(mae/1320*100),'test_start':str(y.index[idx[split]].date()),'test_n':len(idx)-split}
train_end=idx[split-1]; share={}
for m in range(1,13):
 hh=h.iloc[:train_end+1]; hh=hh[(hh.index.month==m)&(y.iloc[:train_end+1]>0)]
 share[m]=hh.sum().to_numpy()/hh.sum().sum()
ph=p[:,None]*np.stack([share[d.month] for d in y.index[idx]])
aa=h.iloc[idx].to_numpy(); eligible=aa[split:]>=5.5
errors=np.abs(ph[split:]-aa[split:])/55*100
day_rates=[float(e[m].mean()) for e,m in zip(errors,eligible) if m.any()]
out['hourly_proxy']={'pooled_hour_mean':float(errors[eligible].mean()),'equal_day_mean':float(np.mean(day_rates)),'eligible_hours':int(eligible.sum()),'caution':'One forecast, reconstructed monthly shape; not settlement (two submissions, daily rules).'}
# Derived expected-generation diagnostic: no forecast-time availability claim.
e=full.pi_expected_kwh; gy=full.gy_gsr_obs; valid=full.pi_valid==1
def level(lo,hi):
 d=full.loc[lo:hi]; d=d[(d.pi_valid==1)&~d.index.isin(ev.index)&d.pi_expected_kwh.notna()]
 return float(d.gen_kwh.sum()/d.pi_expected_kwh.sum())
pairs={'2015_drop':('2014-01-04','2014-04-22','2015-01-04','2015-04-22'),'2015_recovery_season_confounded':('2015-01-04','2015-04-22','2015-05-16','2015-08-31'),'2021_year':('2020-05-19','2021-05-12','2021-05-19','2022-05-12'),'2021_sixweeks':('2021-04-01','2021-05-12','2021-05-19','2021-06-30'),'2024_year':('2023-03-23','2024-03-21','2024-03-23','2025-03-22'),'2024_vs_before2021':('2020-05-19','2021-05-12','2024-03-23','2025-03-22')}
out['pi_changes']={k:{'before':level(a,b),'after':level(c,d),'change_percent':(level(c,d)/level(a,b)-1)*100,'periods':v} for k,v in pairs.items() for a,b,c,d in [v]}
stop=(y<1)|((y<5)&(y.shift(1)<5))|((e>=30)&(y<.3*e))
low=(e>=80)&(y<.6*e)&~stop
hold=~stop&~low&(e.isna()|(e<80))
out['detector']={'counts_until2025':{'stop':int(stop.loc[:'2025-12-31'].sum()),'low':int(low.loc[:'2025-12-31'].sum()),'hold':int(hold.loc[:'2025-12-31'].sum())},'label_hit':{cat:{'n':len(rows),'hit':int((stop|low).reindex(rows.index).sum())} for cat,rows in ev.groupby('category')},'false_positive_limit':'Cannot independently verify negatives/exclusions: original neighboring-station calendar absent.'}
pred_out={}
for f in sorted((root/'docs/research/merged/files/T2-history-outage/lstm').glob('*_pred.csv')):
 d=pd.read_csv(f,index_col='date',parse_dates=True); vv={}
 for c in d.columns:
  if c.startswith('pred'):
   er=d[c]-d.actual; keep=~d.index.isin(ev.index)
   vv[c]={'rmse_all':float(np.sqrt((er**2).mean())),'rmse_without_events':float(np.sqrt((er[keep]**2).mean())),'event_sse_percent':float((er[~keep]**2).sum()/(er**2).sum()*100)}
 pred_out[f.name]=vv
out['stored_prediction_metrics']=pred_out
# Independently check full PI expected diagnostics and raw hourly signature on event date.
out['march2024']={str(d.date()):{'total':float(y[d]),'zero_hours':[int(c) for c in h.columns[h.loc[d]==0]]} for d in pd.date_range('2024-03-21','2024-03-23')}
out['march2025_demo']={str(d.date()):{'actual':float(y[d]),'expected':float(e[d]),'ratio':float(y[d]/e[d])} for d in pd.date_range('2025-03-31','2025-04-01')}
a.output.parent.mkdir(parents=True,exist_ok=True)
a.output.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({k:out[k] for k in ['raw','uploads','sample_overlap','ridge','hourly_proxy','pi_changes','detector']},ensure_ascii=False,indent=2))
