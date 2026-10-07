"""Independent ceiling, changepoint, daily alarm and leakage audit. Usage script.py ROOT."""
import sys,json
from pathlib import Path
import pandas as pd,numpy as np
R=Path(sys.argv[1]);P=Path(__file__).parent
raw=pd.read_csv(R/'datasets/raw/data_15043409.csv',encoding='cp949'); g=raw.assign(date=pd.to_datetime(raw['년월일'])).set_index('date').sort_index(); a=pd.read_csv(R/'datasets/hadong_daily_full.csv',parse_dates=['date']).set_index('date'); idx=a.index; x=a.gen_kwh;e=a.pi_expected_kwh; peak=g[[str(h) for h in range(1,25)]].max(axis=1).reindex(idx);doy=idx.dayofyear
stop=pd.Series(False,index=idx)
for s,t in [('2015-04-23','2015-05-06'),('2016-12-22','2016-12-27'),('2018-07-04','2018-08-01'),('2020-09-08','2020-09-08')]: stop.loc[s:t]=True
O={}
def env(s,t):
 m=(idx>=s)&(idx<=t)&~stop;dy=doy[m];pk=peak[m];z=np.empty(367);z[0]=np.nan
 for d in range(1,367):
  dist=np.abs(dy-d);dist=np.minimum(dist,366-dist);k=dist<=10
  if k.sum()<5:k=dist<=30
  z[d]=np.quantile(pk[k],.9)
 return z
for name,s,t in [('13_17','2013-01-01','2017-12-31'),('16_20','2016-01-01','2020-12-31'),('18_20','2018-08-02','2020-12-31')]:
 r=(peak/env(s,t)[doy]).where(~stop);O[name]={}
 for limit in [.9,.88]:
  f=(r.rolling(14,min_periods=10).max()<limit)&(r.rolling(14,min_periods=10).count()>=10)
  ff=f.loc['2021-05-13':'2021-09-10'];dd=ff.index[ff];q=f.loc['2018-08-02':'2021-05-12']; nn=q&~q.shift(1,fill_value=False)
  O[name][str(limit)]={'first':str(dd[0].date()) if len(dd) else None,'middle_episodes':int(nn.sum()),'middle_days':int(q.sum()),'lookahead_middle_days':int(((idx>=pd.Timestamp('2018-08-02'))&(idx<=pd.Timestamp('2021-05-12'))&(idx<=pd.Timestamp(t))).sum())}
 if name=='13_17':
  wx=pd.read_csv(R/'datasets/raw/wx_archive_daily.csv',parse_dates=['date']).set_index('date');sun=(wx.sunshine_duration/wx.daylight_duration).reindex(idx);ss=r.where(sun>=.85).loc['2021-03-01':'2021-07-31'].dropna(); scores={}
  for c in pd.date_range('2021-04-15','2021-06-20'):
   lo,hi=ss[ss.index<c],ss[ss.index>=c];scores[str(c.date())]=float(((lo-lo.mean())**2).sum()+((hi-hi.mean())**2).sum())
  mini=min(scores.values());rng=[k for k,z in scores.items() if z<=mini*(1+3.84/(len(ss)-2))];O['peak_changepoint']={'n':len(ss),'min':min(scores,key=scores.get),'descriptive_range':[min(rng),max(rng)],'ratio18':scores['2021-05-18']/mini}
# 30-day alarm on 39 starts, separate moving from per-start fixed baselines.
def gate(xx):
 o=(xx<=0)|((e>=30)&(xx<.3*e));low=o|((e>=80)&(xx<.7*e));h=low.astype(int).rolling(7,min_periods=1).sum()>=3
 return e.notna()&(e>0)&~o&~h
starts=pd.date_range('2025-03-08','2025-11-29',freq='7D');O['daily_injection']={};en=env('2023-11-07','2025-02-28')
for f in [1,.915,.86,.8,.7]:
 hit=[];hitfix=[];delays=[];peak_hits=[]
 for st in starts:
  xx=x.copy();xx.loc[st:]*=f;vv=gate(xx);gc=xx.clip(.5*e,1.5*e);n=gc.where(vv,0).rolling(30,min_periods=1).sum();d=e.where(vv,0).rolling(30,min_periods=1).sum();k=vv.astype(int).rolling(30,min_periods=1).sum();pi=(n/d).where(k>=21)
  bn=gc.where(vv,0).rolling(365,min_periods=200).sum().shift(30);bd=e.where(vv,0).rolling(365,min_periods=200).sum().shift(30);base=bn/bd
  z=(idx>=st-pd.Timedelta(days=365))&(idx<st)&vv;bf=gc[z].sum()/e[z].sum()
  flags=((pi/base-1<-.075).astype(int).rolling(3).sum()>=3);ff=flags.loc[st:st+pd.Timedelta(days=29)];hit.append(ff.any());dts=ff.index[ff]
  if len(dts):delays.append((dts[0]-st).days+1)
  flags=((pi/bf-1<-.075).astype(int).rolling(3).sum()>=3);hitfix.append(flags.loc[st:st+pd.Timedelta(days=29)].any())
  pk=peak.copy();pk.loc[st:]*=f;r=(pk/en[doy]).where(~stop);fl=(r.rolling(14,min_periods=10).max()<.9)&(r.rolling(14,min_periods=10).count()>=10);peak_hits.append(fl.loc[st:st+pd.Timedelta(days=29)].any())
 O['daily_injection'][str(f)]={'n':len(starts),'moving_pct':float(100*np.mean(hit)),'per_start_frozen_pct':float(100*np.mean(hitfix)),'moving_delay_median':float(np.median(delays)) if delays else None,'ceiling_pct':float(100*np.mean(peak_hits))}
(P/'t5_ceiling_results.json').write_text(json.dumps(O,indent=2));print(json.dumps(O,indent=2))
