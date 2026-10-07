"""Build true hourly generation + archived forecasts, not daily/24 approximations."""
import gzip,hashlib,json,sys
from pathlib import Path
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'datasets/hourly'
VARS=['shortwave_radiation','temperature_2m','cloud_cover','wind_speed_10m']

def read(path):return json.loads(Path(path).read_text(encoding='utf-8'))
def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
def raw_csv(path):
    for enc in ['utf-8-sig','cp949']:
        try:return pd.read_csv(path,encoding=enc,dtype=str)
        except UnicodeDecodeError:pass
    raise ValueError('Unsupported source encoding')

def main():
    plants=read(ROOT/'tools/hourly/candidates.json')['plants']
    mapping={p['plant_id']:p for p in read(ROOT/'datasets/plant_forecasts/plant_mapping.json')}
    cache={};included=[];excluded=[]
    for pid,p in plants.items():
        sid=p['source_id'];dataset,unit=sid.split('_u')
        try:
            region=mapping[sid]['region']
            if region not in cache:
                frames=[];hashes={}
                for path in sorted((ROOT/'datasets/plant_forecasts/raw').glob(region+'_*.json.gz')):
                    raw=gzip.decompress(path.read_bytes());data=json.loads(raw)
                    assert data['timezone']=='Asia/Seoul'
                    meta=read(path.with_suffix('.meta.json'))
                    assert hashlib.sha256(raw).hexdigest()==meta['sha256_uncompressed']
                    hashes[path.name]=meta['sha256_uncompressed']
                    frame=pd.DataFrame(data['hourly']);frame.index=pd.to_datetime(frame.pop('time'))
                    # Radiation is a preceding-hour mean: end 01:00 -> interval start 00:00.
                    frame=frame[[v+'_previous_day2' for v in VARS]].rename(columns={v+'_previous_day2':v for v in VARS})
                    frame=frame.apply(pd.to_numeric,errors='coerce').astype(float)
                    frame.index-=pd.Timedelta(hours=1);frames.append(frame)
                if not frames:raise ValueError('hourly_forecast_missing')
                weather=pd.concat(frames).sort_index()
                if weather.index.duplicated().any():raise ValueError('duplicate_forecast_timestamp')
                cache[region]=(weather,hashes)
            weather,weather_hashes=cache[region]
            source=ROOT/'datasets/multi_plant/raw'/f'{dataset}.csv'
            if dataset=='15043409':source=ROOT/'datasets/raw/data_15043409.csv'
            if not source.exists():raise ValueError('hourly_generation_missing')
            raw=raw_csv(source);raw=raw[raw['호기'].astype(str).str.strip()==unit].copy()
            cols=[str(h) for h in range(1,25)]
            if not set(cols)<=set(raw):cols=[f'{h}-{h+1}시 발전량(kWh)' for h in range(24)]
            if not set(cols)<=set(raw):raise ValueError('24_hour_columns_missing')
            raw['day']=pd.to_datetime(raw['년월일'],errors='coerce');raw=raw.dropna(subset=['day'])
            total=next(c for c in raw if c.startswith('총량'))
            numeric=raw[cols+[total]].apply(pd.to_numeric,errors='coerce').astype(float)
            good=np.isfinite(numeric).all(axis=1)&numeric.ge(0).all(axis=1)&numeric[cols].le(p['capacity_kw']).all(axis=1)&np.isclose(numeric[cols].sum(axis=1),numeric[total],rtol=1e-6,atol=.05)
            signatures=raw[cols+[total]].astype(str).agg('|'.join,axis=1)
            conflicts=signatures.groupby(raw.day).nunique();bad_days=conflicts[conflicts>1].index
            good &= ~raw.day.isin(bad_days)
            accepted=raw.loc[good].drop_duplicates('day').sort_values('day')
            matrix=accepted[cols].apply(pd.to_numeric).to_numpy()
            timestamps=pd.DatetimeIndex(np.repeat(accepted.day.to_numpy(),24))+pd.to_timedelta(np.tile(np.arange(24),len(accepted)),unit='h')
            gen=pd.DataFrame({'generation_kwh':matrix.ravel()},index=timestamps)
            merged=gen.join(weather,how='inner').sort_index()
            valid=np.isfinite(merged).all(axis=1)&merged.shortwave_radiation.between(0,1500)&merged.temperature_2m.between(-60,60)&merged.cloud_cover.between(0,100)&merged.wind_speed_10m.between(0,200)
            merged=merged[valid]
            complete=merged.groupby(merged.index.normalize()).size();days=complete[complete==24].index
            merged=merged[merged.index.normalize().isin(days)]
            # Store individual valid days; train builder requires exact previous-day adjacency.
            eligible=[d for d in days if d-pd.Timedelta(days=1) in days]
            dates=pd.DatetimeIndex(eligible)
            counts=dict(train=int((dates<pd.Timestamp('2024-07-01')).sum()),validation=int(((dates>=pd.Timestamp('2024-07-01'))&(dates<pd.Timestamp('2025-01-01'))).sum()),test=int(((dates>=pd.Timestamp('2025-01-01'))&(dates<pd.Timestamp('2026-01-01'))).sum()))
            if counts['train']<365 or counts['validation']<90 or counts['test']<180:raise ValueError('insufficient_complete_hourly_days:'+str(counts))
            path=OUT/'plants'/f'{pid}.csv';path.parent.mkdir(parents=True,exist_ok=True)
            merged.index=merged.index.tz_localize('Asia/Seoul');merged.index.name='timestamp';merged.to_csv(path,float_format='%.9g')
            result=dict(p,weather_region=region,hourly_file=str(path.relative_to(ROOT)),rows=len(merged),complete_days=len(days),samples=counts,source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),hourly_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),weather_hashes=weather_hashes,discarded_generation_days=int((~good).sum()),interval='start timestamp, [t,t+1h)',forecast_lead_hours=48,publication_cutoff_verified=False)
            included.append(result);print('HOURLY',pid,counts,flush=True)
        except (ValueError,KeyError,AssertionError,OSError) as exc:
            excluded.append(dict(plant_id=pid,source_id=sid,reason=str(exc)));print('EXCLUDED',pid,str(exc),flush=True)
    write(OUT/'screening.json',dict(included=included,excluded=excluded,source='existing approved 33 plants only',timezone='Asia/Seoul',radiation_alignment='end timestamp minus one hour',forecast='JMA MSM previous_day2 (48h fixed lead; regional proxy)',generation_units='kWh per one-hour interval; verified against daily sums; legacy kW labels interpreted as interval energy'))
    print('COMPLETE',len(included),'included',len(excluded),'excluded')
if __name__=='__main__':main()
