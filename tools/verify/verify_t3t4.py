"""Read-only T3/T4 audit. Standard library only; no account, keys or ML reruns.
Run: python3 tools/verify/verify_t3t4.py --root /path/to/1007_AIOPs
Numbers from retained per-seed metrics are explicitly labeled secondary evidence.
"""
import argparse
import csv
import datetime as dt
import json
import math
import statistics as st
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument('--root', type=Path, required=True)
ROOT = p.parse_args().root

def read(path, key='date', encoding='utf-8'):
    with (ROOT / path).open(encoding=encoding, newline='') as f:
        return {r[key]: r for r in csv.DictReader(f)}

def val(r, k):
    return float(r[k]) if r and r.get(k) not in (None, '') else None

def dateadd(d, n):
    return (dt.date.fromisoformat(d) + dt.timedelta(days=n)).isoformat()

def report(name, obj):
    print(name, json.dumps(obj, ensure_ascii=False, sort_keys=True))

raw = read('datasets/raw/data_15043409.csv', '년월일', 'cp949')
full = read('datasets/hadong_daily_full.csv')
fc = read('datasets/raw/wx_prevruns_daily.csv')
arc = read('datasets/raw/wx_archive_daily.csv')
y = {d: val(r, '총량(kw)') for d, r in raw.items()}
report('raw', {'days': len(y), 'raw_full_maxdiff': max(abs(y[d]-val(full[d], 'gen_kwh')) for d in y),
    'hourly_sum_maxdiff': max(abs(y[d]-sum(val(r,str(i)) for i in range(1,25))) for d,r in raw.items()),
    'hourly_max': max(val(r,str(i)) for r in raw.values() for i in range(1,25)),
    'hours_gt50': sum(val(r,str(i))>50 for r in raw.values() for i in range(1,25)),
    'days_gt50': sum(any(val(r,str(i))>50 for i in range(1,25)) for r in raw.values())})

for name, src, col, lag in [('hadong_upload_forecast_jma.csv', fc,'shortwave_radiation_previous_day1',1),
                          ('hadong_upload.csv',full,'gy_gsr',-1),
                          ('hadong_upload_forecast_proxy.csv',full,'gy_gsr',1)]:
    u=read('datasets/'+name,'Date')
    rows=list(u.values()); ds=list(u); cut=int((len(rows)-20)*.8); tr=rows[:20+cut]
    ranges=lambda rs: {c: [min(val(r,c) for r in rs),max(val(r,c) for r in rs)] for c in ['Close','Volume']}
    report('upload '+name, {'n':len(rows),'first':ds[0],'last':ds[-1], 'train_n':cut,'test_n':len(rows)-20-cut,
       'train_target_last':ds[20+cut-1],'test_first':ds[20+cut],'test_last':ds[-1],
       'close_maxdiff':max(abs(val(r,'Close')-y[d]) for d,r in u.items()),
       'volume_maxdiff':max(abs(val(r,'Volume')-val(src.get(dateadd(d,lag)),col)) for d,r in u.items()),
       'zero_close':sum(val(r,'Close')==0 for r in rows),'full_scaler':ranges(rows),'train_scaler':ranges(tr),
       'scaler_equal':ranges(rows)==ranges(tr),
       'gaps':sum(dateadd(ds[i],1)!=ds[i+1] for i in range(len(ds)-1))})

def pair(a,b):
    z=[(a[d],b[d]) for d in a.keys() & b.keys() if a[d] is not None and b[d] is not None]
    x,v=zip(*z); mx=st.mean(x); mv=st.mean(v)
    ssx=sum((q-mx)**2 for q in x); ssv=sum((q-mv)**2 for q in v); ssxy=sum((q-mx)*(w-mv) for q,w in z)
    rm=math.sqrt(st.mean((q-w)**2 for q,w in z))
    return {'n':len(z),'mean_obs':mx,'corr':ssxy/math.sqrt(ssx*ssv),'rmse':rm,'rRMSE_pct':100*rm/mx,
            'ratio_sum':sum(v)/sum(x),'slope':ssxy/ssx}

obs={d:val(r,'gy_gsr_obs') if val(r,'gy_gsr_suspect')!=1 else None for d,r in full.items()}
report('agreement_archive',pair(obs,{d:val(r,'shortwave_radiation_sum') for d,r in arc.items()}))
for n in [1,2]: report('agreement_forecast'+str(n),pair(obs,{d:val(r,'shortwave_radiation_previous_day'+str(n)) for d,r in fc.items()}))
report('forecast_date_range',{'n':sum(val(r,'shortwave_radiation_previous_day1') is not None for r in fc.values()),
    'first':min(d for d,r in fc.items() if val(r,'shortwave_radiation_previous_day1') is not None),
    'last':max(d for d,r in fc.items() if val(r,'shortwave_radiation_previous_day1') is not None)})
for n in [1,2]:
    common={d:val(r,'gy_gsr') for d,r in full.items() if '2023-07-17'<=d<='2025-12-30'}
    report('C898_forecast_agreement'+str(n),pair(common,{d:val(r,'shortwave_radiation_previous_day'+str(n)) for d,r in fc.items()}))
u1=read('datasets/hadong_upload_forecast_jma.csv','Date')
up=read('datasets/hadong_upload_forecast_proxy.csv','Date')
lo=min(val(r,'Volume') for r in u1.values()); hi=max(val(r,'Volume') for r in u1.values())
report('proxy_in_forecast_scaler',{'overlap':len(u1.keys() & up.keys()),
    'outside_0_1':sum(not lo<=val(up[d],'Volume')<=hi for d in u1.keys() & up.keys())})

def forecast(d,n): return val(fc.get(d),'shortwave_radiation_previous_day'+str(n))
def rule(d,src='fc1',target='fc1',lag=1):
    def wx(k,s):
        return forecast(k,int(s[-1])) if s.startswith('fc') else val(full.get(k),'gy_gsr') if s=='asos' else val(arc.get(k),'shortwave_radiation_sum')
    days=[dateadd(d,-i-lag) for i in range(7)]
    ww=[wx(k,src) for k in days]; t=wx(d,target)
    return None if t is None or any(w is None for w in ww) else sum(y[k] for k in days)/sum(ww)*t
def meanpast(d,n,lag=1): return st.mean(y[dateadd(d,-i-lag)] for i in range(n))
def metrics(ds, fun):
    z=[(y[d],fun(d)) for d in ds]; z=[(a,b) for a,b in z if b is not None]
    return {'n':len(z),'RMSE':math.sqrt(st.mean((a-b)**2 for a,b in z)), 'WAPE':100*sum(abs(a-b) for a,b in z)/sum(a for a,b in z),
       'bias_pct':100*sum(b-a for a,b in z)/sum(a for a,b in z)}
intervals={'C898':('2023-07-17','2025-12-30'),'P264':('2025-06-09','2026-02-27'),
           'P946':('2023-05-30','2025-12-30'),'T1_958':('2023-07-17','2026-02-28')}
for name,(start,end) in intervals.items():
    ds=[d for d in y if start<=d<=end]
    out={'n':len(ds),'mean_gen':st.mean(y[d] for d in ds),'stop':sum(val(full[d],'stop_day') for d in ds)}
    for lab,fn in [('m7',lambda d:meanpast(d,7)),('m20',lambda d:meanpast(d,20)),('yesterday',lambda d:y[dateadd(d,-1)]),
                   ('rule24',lambda d:rule(d)),('rule48mixed',lambda d:rule(d,target='fc2')),
                   ('rule48all',lambda d:rule(d,src='fc2',target='fc2')),
                   ('rule_asos_upper',lambda d:rule(d,src='asos',target='asos')),
                   ('rule_archive_upper',lambda d:rule(d,src='arc',target='arc'))]: out[lab]=metrics(ds,fn)
    report('baselines '+name,out)
    if name=='C898':
        correct_gate=min(.8*out['m7']['RMSE'],1.05*out['rule48mixed']['RMSE'])
        wrong_gate=min(.8*out['m7']['RMSE'],1.05*out['rule24']['RMSE'])
        with (ROOT/'docs/research/merged/files/T4-performance-gate/t4_per_seed_C898.csv').open() as f: seed=list(csv.DictReader(f))
        s=[r for r in seed if r['family']=='실습 LSTM' and 'T 칸 48h 예보' in r['label']]
        report('48h_gate_secondary_metrics',{'correct_gate':correct_gate,'wrong_gate':wrong_gate,'n':len(s),
           'correct_pass':sum(float(r['RMSE'])<=correct_gate for r in s),'wrong_pass':sum(float(r['RMSE'])<=wrong_gate for r in s),
           'retained_metric_rmse_range':[min(float(r['RMSE']) for r in s),max(float(r['RMSE']) for r in s)]})

# Saved two-day model response only; cannot establish all 23 days are ICON.
api=ROOT/'docs/research/merged/files/T3-weather-input/api'
js=json.loads((api/'prev_gap_models.json').read_text())
report('gap_saved_json_shape',{'type':type(js).__name__,'n':len(js) if isinstance(js,list) else 1})
if isinstance(js,(list,dict)):
    hh=(js[0] if isinstance(js,list) else js)['hourly']; t=hh['time']; c1='shortwave_radiation_previous_day1'
    daylight=[i for i,k in enumerate(t) if 7<=dt.datetime.fromisoformat(k).hour<=18]
    cols=[k for k in hh if c1 in k]
    report('gap_saved_model_keys',cols)
    icon=next(k for k in cols if 'icon_seamless' in k); best=next(k for k in cols if 'best_match' in k)
    report('gap_two_day_comparison',{'daylight_n':len(daylight),'icon_best_equal':sum(hh[icon][i]==hh[best][i] for i in daylight),
       'jma_nonnull':{k:sum(hh[k][i] is not None for i in daylight) for k in cols if 'jma' in k}})
    default=json.loads((api/'prev_gap_default.json').read_text())['hourly']
    report('gap_default_saved_raw_comparison',{'all_hour_n':len(t),
        'best_default_equal':sum(hh[best][i]==default[c1][i] for i in range(len(t))),
        'day_sum_raw_maxdiff':max(abs(sum(hh[best][i] for i,k in enumerate(t) if k[:10]==d)*.0036-
            val(fc[d],c1)) for d in {k[:10] for k in t})})

for k in ['meta_jma_msm_0124.json','meta_jma_msm_0131.json','meta_jma_gsm_0124.json']:
    m=json.loads((api/k).read_text())
    report('saved_meta '+k,{'init_UTC':dt.datetime.fromtimestamp(m['last_run_initialisation_time'],dt.timezone.utc).isoformat(),
       'availability_UTC':dt.datetime.fromtimestamp(m['last_run_availability_time'],dt.timezone.utc).isoformat(),
       'delay_hours':(m['last_run_availability_time']-m['last_run_initialisation_time'])/3600})

ds=[d for d in y if '2023-07-17'<=d<='2025-12-30']
for cap in [50,55]:
    for label,fn in [('perfectdaily',lambda d:y[d]),('yesterday',lambda d:y[dateadd(d,-1)]),
                      ('m7',lambda d:meanpast(d,7)),('rule24',lambda d:rule(d))]:
        errs=[]; allerrs=[]; daily=[]
        for d in ds:
            prev=[raw[dateadd(d,-i)] for i in range(1,21)]
            bins=[sum(val(r,str(h)) for r in prev) for h in range(1,25)]; denom=sum(bins)
            pp=fn(d); daily.append(abs(pp-y[d]))
            for h,b in enumerate(bins,1):
                actual=val(raw[d],str(h)); e=abs(pp*b/denom-actual)/cap*100
                allerrs.append(e)
                if actual>=cap*.1: errs.append(e)
        report('hourly_disaggregation '+str(cap)+' '+label,{'n_days':len(ds),'n_valid_hours':len(errs),
           'daily_MAE_capacity24_pct':st.mean(daily)/(cap*24)*100,'valid_hour_MAE_pct':st.mean(errs),
           'valid_hours_error_le6_pct':100*sum(e<=6 for e in errs)/len(errs),
           'valid_hours_error_le4_pct':100*sum(e<=4 for e in errs)/len(errs), 'all_hours_MAE_pct':st.mean(allerrs)})
