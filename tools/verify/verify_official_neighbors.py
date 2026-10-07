"""Audit freshly downloaded official rows, neighbors and contract; never changes source CSVs."""
import argparse, hashlib, json, math
from pathlib import Path
import pandas as pd
p=argparse.ArgumentParser();p.add_argument('--repo',type=Path,required=True);p.add_argument('--sources',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--inverter-hwp',type=Path);a=p.parse_args()
def read(id):
 for enc in ['utf-8-sig','cp949']:
  try:return pd.read_csv(a.sources/f'{id}.csv',encoding=enc)
  except UnicodeDecodeError:continue
 raise ValueError(id)
o={'sources':json.loads((a.sources/'sources.json').read_text())}
o['specs']=read('15030079').query("발전소명 == '하동하수처리장태양광'").to_dict('records')
d=read('15003687');o['equipment']=d[d.발전소명.str.contains('하동하수')].to_dict('records')
d=read('15147894');o['location']=d[d.발전소명.str.contains('하동 하수')].to_dict('records')
d=read('15095366');o['contract']=d[d.astype(str).apply(lambda c:c.str.contains('소외 태양광 인버터')).any(axis=1)].to_dict('records')
phi1,phi2=map(math.radians,[35.05885,34.9434]);dl=math.radians(127.7799-127.6914)
hav=math.sin((phi1-phi2)/2)**2+math.cos(phi1)*math.cos(phi2)*math.sin(dl/2)**2
o['distance_km']=2*6371*math.asin(math.sqrt(hav))
raw=pd.read_csv(a.repo/'datasets/raw/data_15043409.csv',encoding='cp949',parse_dates=['년월일']).set_index('년월일')
y=raw['총량(kw)']; out={};nbs={}
for id in ['15043404','15043405','15043406','15043408']:
 d=read(id);d.index=pd.to_datetime(d.년월일);h=d[[str(k) for k in range(1,25)]];g=d.iloc[:,2]
 nbs[id]=g
 out[id]={'n':len(d),'start':str(d.index.min().date()),'end':str(d.index.max().date()),'sum_diff':float((h.sum(axis=1)-g).abs().max()),'zero_days':int((g==0).sum()),'joint_zero_with_hadong':int(((g==0)&(y==0)).sum()),'hourly_max':float(h.to_numpy().max()),'dec2016_24':float(g['2016-12-24'])}
o['neighbors']=out
def ratio(id,lo,hi):
 nb=nbs[id].loc[lo:hi];hh=y.reindex(nb.index);mask=nb>=200
 return float(hh[mask].sum()/nb[mask].sum()), int(mask.sum())
o['health_clear_drop']={'before':ratio('15043406','2021-04-01','2021-05-14'),'after':ratio('15043406','2021-05-19','2021-06-30')}
o['health_clear_drop']['change_percent']=(o['health_clear_drop']['after'][0]/o['health_clear_drop']['before'][0]-1)*100
o['inverter_hwp_sha256']=hashlib.sha256(a.inverter_hwp.read_bytes()).hexdigest() if a.inverter_hwp else None
a.output.write_text(json.dumps(o,ensure_ascii=False,indent=2,default=str)+'\n');print(json.dumps(o,ensure_ascii=False,indent=2,default=str))
