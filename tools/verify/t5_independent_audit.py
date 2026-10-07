"""Read-only independent T5 audit. Usage: python script.py REPO_ROOT."""
import sys,json
from pathlib import Path
import pandas as pd,numpy as np
R=Path(sys.argv[1]); OUT=Path(__file__).parent
raw=pd.read_csv(R/'datasets/raw/data_15043409.csv',encoding='cp949')
a=pd.read_csv(R/'datasets/hadong_daily_full.csv',parse_dates=['date']).set_index('date').sort_index()
g=raw.assign(date=pd.to_datetime(raw['년월일'])).set_index('date').sort_index()
x=a.gen_kwh; e=a.pi_expected_kwh; idx=a.index
O={}
def val(z): return float(z)
def gate(x):
 out=(x<=0)|((e>=30)&(x<.3*e)); low=out|((e>=80)&(x<.7*e)); hold=low.astype(int).rolling(7,min_periods=1).sum()>=3
 return out,hold,e.notna()&(e>0)&~out&~hold
out,hold,v=gate(x); gc=x.clip(.5*e,1.5*e)
O['raw_check']={'n_raw':len(g),'n_full':len(a),'sum_max_error':val((x-g['총량(kw)']).abs().max()),'peak_max_error':val((a.peak_kw-g[[str(h) for h in range(1,25)]].max(axis=1)).abs().max()),'valid_mismatch':int((v!=a.pi_valid.astype(bool)).sum()),'outage':int(out.sum()),'hold':int(hold.sum())}
# Independently reconstruct published linear expectation from stored inputs and coefficients.
w=2*np.pi*idx.dayofyear/365.25; s1,c1,s2,c2=np.sin(w),np.cos(w),np.sin(2*w),np.cos(2*w)
gsr,ss,ta=a.gy_gsr_obs,a.gy_ss_obs.where(a.gy_ss_obs<=a.gy_ssdur+.05),a.gy_max_ta
F=np.column_stack([gsr,gsr*s1,gsr*c1,gsr*s2,gsr*c2,ss,ss*s1,ss*c1,ss*s2,ss*c2,s1,c1,s2,c2,ta,gsr*ta]); model=json.loads((R/'tools/build_asos_upload/pi_expected_model.json').read_text())
calc=F@np.array(model['coef'])+model['intercept']; O['expected_reconstruction_max_error']=val(np.nanmax(np.abs(calc-e)))
def pi(start,end,clip=True,valid=v,xx=x):
 m=(idx>=pd.Timestamp(start))&(idx<=pd.Timestamp(end))&valid
 z=xx.clip(.5*e,1.5*e) if clip else xx
 return (val(z[m].sum()/e[m].sum()) if e[m].sum()>0 else float("nan")),int(m.sum())
O['baselines']={t:{'clipped':pi(pd.Timestamp(t)-pd.Timedelta(days=364),t),'raw':pi(pd.Timestamp(t)-pd.Timedelta(days=364),t,False)} for t in ['2020-12-31','2021-04-01','2021-04-06','2025-02-28']}
base=O['baselines']['2021-04-01']['clipped'][0]
O['batches']={f'{s}/{t}':{'pi':pi(s,t),'deviation_pct':100*(pi(s,t)[0]/base-1)} for s,t in [('2021-04-22','2021-05-12'),('2021-04-27','2021-05-17'),('2021-06-02','2021-06-22'),('2021-06-07','2021-06-27'),('2021-06-09','2021-06-29')]}
def rollingpi(n,xx=x,valid=v):
 z=xx.clip(.5*e,1.5*e); nn=z.where(valid,0).rolling(n,min_periods=1).sum(); dd=e.where(valid,0).rolling(n,min_periods=1).sum(); k=valid.astype(int).rolling(n,min_periods=1).sum()
 return (nn/dd).where(k>=np.ceil(.7*n))
p30=rollingpi(30); bmove=gc.where(v,0).rolling(365,min_periods=200).sum().shift(30)/e.where(v,0).rolling(365,min_periods=200).sum().shift(30)
def episodes(fl,start,end):
 t=fl.loc[start:end].fillna(False); starts=t&~t.shift(1,fill_value=False)
 return {'episodes':int(starts.sum()),'days':int(t.sum()),'first':str(t.index[t][0].date()) if t.any() else None}
O['baseline_comparison']={}
for name,b in [('moving_shift30',bmove),('frozen_20210401',base),('fixed1',1.0)]:
 dev=p30/b-1; down=(dev<-.075).astype(int).rolling(3).sum()>=3; up=(dev>.075).astype(int).rolling(3).sum()>=3
 O['baseline_comparison'][name]={'event120':episodes(down,'2021-05-13','2021-09-10'),'later2025':episodes(down,'2025-03-01','2025-12-31'),'winter_up2015_2025':episodes(up,'2015-01-01','2025-12-31')}
O['2021_daily']=a.loc['2021-05-13':'2021-05-22',['gy_sun_frac','gen_kwh','pi_expected_kwh']].assign(pi=x/e).round(6).reset_index().astype({'date':str}).to_dict('records')
# Search two-level change point, deliberately only a descriptive post-event calculation.
s=(x/e).where(v).loc['2021-03-01':'2021-07-31'].dropna(); cands=pd.date_range('2021-04-15','2021-06-20'); scores={}
for c in cands:
 lo=s[s.index<c]; hi=s[s.index>=c]; scores[str(c.date())]=val(((lo-lo.mean())**2).sum()+((hi-hi.mean())**2).sum())
mini=min(scores.values()); rng=[k for k,z in scores.items() if z<=mini*(1+3.84/(len(s)-2))]; O['changepoint']={'n':len(s),'min':min(scores,key=scores.get),'descriptive_approx_range':[min(rng),max(rng)],'ratio13':scores['2021-05-13']/mini,'ratio18':scores['2021-05-18']/mini}
# Raw hourly envelope, reproduce declared day-of-year circular convention.
d3=pd.Series(False,index=idx)
for start,end in [('2015-04-23','2015-05-06'),('2016-12-22','2016-12-27'),('2018-07-04','2018-08-01'),('2020-09-08','2020-09-08')]:d3.loc[start:end]=True
peak=g[[str(h) for h in range(1,25)]].max(axis=1).reindex(idx); doy=idx.dayofyear
m=(idx>='2013-01-01')&(idx<='2017-12-31')&~d3; en={}
for d in range(1,367):
 dist=np.abs(doy[m]-d); dist=np.minimum(dist,366-dist); en[d]=np.quantile(peak[m][dist<=10],.9)
r=(peak/np.array([en[d] for d in doy])).where(~d3)
O['change_sizes']=[]
for days,post in [(42,42),(42,49),(365,365)]:
 ref=pd.Timestamp('2021-05-18'); p0=pi(ref-pd.Timedelta(days=days),ref-pd.Timedelta(days=1))[0];p1=pi(ref,ref+pd.Timedelta(days=post-1))[0]
 q0=r.loc[ref-pd.Timedelta(days=days):ref-pd.Timedelta(days=1)].quantile(.9);q1=r.loc[ref:ref+pd.Timedelta(days=post-1)].quantile(.9)
 O['change_sizes'].append({'pre':days,'post':post,'pi_pct':100*(p1/p0-1),'peak_pct':100*(q1/q0-1)})
O['recovery']=[]
for label,s0,t0,s1_,t1_ in [('summer','2023-06-01','2023-08-31','2024-06-01','2024-08-31'),('spring','2023-03-01','2023-04-30','2024-03-01','2024-04-30'),('warm','2023-05-01','2023-09-30','2024-05-01','2024-09-30'),('fall','2023-10-01','2023-12-31','2024-10-01','2024-12-31'),('year','2023-03-28','2024-03-27','2024-03-28','2025-03-27')]:
 p0,p1=pi(s0,t0)[0],pi(s1_,t1_)[0];q0,q1=r.loc[s0:t0].quantile(.9),r.loc[s1_:t1_].quantile(.9)
 O['recovery'].append({'period':label,'pi_pct':100*(p1/p0-1),'peak_pct':100*(q1/q0-1)})
O['july2024']=pd.DataFrame({'ratio':x/e,'outage':out,'hold':hold,'valid':v}).loc['2024-07-10':'2024-07-22'].reset_index().astype({'date':str}).to_dict('records')
O['stop_difference']={'D3':int(d3.sum()),'ASOS':int(a.stop_day.sum()),'intersection':int((d3&a.stop_day.astype(bool)).sum()),'D3_only':[str(d.date()) for d in idx[d3&~a.stop_day.astype(bool)]]}
# Injection scan: compare per-start frozen baseline with baseline fixed before entire evaluation.
starts=pd.date_range('2025-03-08','2025-11-15',freq='7D'); trainbase=O['baselines']['2025-02-28']['clipped'][0]
O['injection']={}
for f in [1,.915,.86,.8,.7]:
 dr=[];dt=[];nvalid=[]
 for st in starts:
  xx=x.copy();xx.loc[st:]*=f;oo,hh,vv=gate(xx); p,n=pi(st+pd.Timedelta(days=20),st+pd.Timedelta(days=40),True,vv,xx); bs=pi(st-pd.Timedelta(days=365),st-pd.Timedelta(days=1),True,vv,xx)[0]
  nvalid.append(n);dr.append(p/bs-1 if n>=15 else np.nan);dt.append(p/trainbase-1 if n>=15 else np.nan)
 O['injection'][str(f)]={'n':len(starts),'hold_pct':100*np.mean(np.array(nvalid)<15),'per_start_baseline_detect_pct':100*np.mean(np.array(dr)<-.075),'frozen_train_baseline_detect_pct':100*np.mean(np.array(dt)<-.075),'median_per_start_pct':100*np.nanmedian(dr)}
# Summary recomputation is not a new LSTM fit; original fit CSV is a frozen research artifact.
D=pd.concat([pd.read_csv(p) for p in (R/'docs/research/merged/files/T5-drift-demo').glob('t5_02_ft_seed*.csv')]); O['fit_artifact_summary']={}
for f,q in D.groupby('factor'):
 O['fit_artifact_summary'][str(f)]={'n':len(q),'before_rmse':val(q.next_rmse_frozen.mean()),'after_rmse':val(q.next_rmse_ft.mean()),'before_bias_pct':val(q.next_bias_pct_frozen.mean()),'after_bias_pct':val(q.next_bias_pct_ft.mean()),'gate5_ft_percentiles':np.percentile(q.gate5_ft,[5,50,95]).tolist(),'gate45_pass_pct':100*val((q.gate5_ft<=45).mean()),'correlation_before_before':val(q[['gate5_before','next_rmse_frozen']].corr().iloc[0,1]),'correlation_after_after':val(q[['gate5_ft','next_rmse_ft']].corr().iloc[0,1]),'rmse1.3_rate':100*val((q.batch_rmse/q.train_rmse>1.3).mean())}
q=D[(D.start=='2025-06-21')&(D.factor==.86)];O['selected_demo_fit']={'before_rmse':val(q.next_rmse_frozen.mean()),'after_rmse':val(q.next_rmse_ft.mean()),'bias_before':q.next_bias_pct_frozen.tolist(),'bias_after':q.next_bias_pct_ft.tolist()}
candidates=[]
for st in starts:
 ds=[]
 for f in [1,.86]:
  xx=x.copy();xx.loc[st:]*=f;oo,hh,vv=gate(xx); pp,nn=pi(st+pd.Timedelta(days=20),st+pd.Timedelta(days=40),True,vv,xx);bs=pi(st-pd.Timedelta(days=365),st-pd.Timedelta(days=1),True,vv,xx)[0];ds.append(pp/bs-1 if nn>=15 else np.nan)
 q=D[(D.start==str(st.date()))&(D.factor==.86)];q0=D[(D.start==str(st.date()))&(D.factor==1.)]
 if abs(ds[0])<=.075 and ds[1]<-.075 and (q.batch_rmse/q.train_rmse<=1.3).all() and (q0.batch_rmse/q0.train_rmse<=1.3).all() and (q.next_bias_pct_ft.abs()<q.next_bias_pct_frozen.abs()).all() and (q.next_rmse_ft<q.next_rmse_frozen).all():candidates.append(str(st.date()))
O['demo_candidates']={'n_evaluated':len(starts),'n_selected':len(candidates),'dates':candidates}
O['forecast_file_check']={}
pr=pd.read_csv(R/'datasets/raw/wx_prevruns_daily.csv',parse_dates=['date']).set_index('date')['shortwave_radiation_previous_day1']
u=pd.read_csv(R/'datasets/hadong_upload_forecast_jma.csv',parse_dates=['Date'])
z=pr.dropna(); O['forecast_file_check']={'nonmissing_n':len(z),'start':str(z.index.min().date()),'end':str(z.index.max().date()),'upload_n':len(u),'shift_max_error':val(np.nanmax(np.abs(u.Volume.values-pr.reindex(u.Date+pd.Timedelta(days=1)).values)))}
(OUT/'t5_audit_results.json').write_text(json.dumps(O,ensure_ascii=False,indent=2)); print(json.dumps(O,ensure_ascii=False,indent=2))
