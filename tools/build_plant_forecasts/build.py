"""Cache regional historical forecasts and produce target-date feature tables.

Run from project/: python ../tools/build_plant_forecasts/build.py
"""
import gzip
import hashlib
import json
import sys
import time
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'datasets/plant_forecasts'
sys.path.insert(0, str(ROOT / 'tools/build_multi_plant'))
from config import SOURCE_REGION

VARIABLES = ['shortwave_radiation', 'temperature_2m', 'sunshine_duration',
             'cloud_cover', 'precipitation', 'wind_speed_10m']
HOURLY = [f'{v}_previous_day{lead}' for lead in (1, 2) for v in VARIABLES]
# Official plant points used as REGIONAL representatives, not as every site's position.
POINT_NAMES = {'hadong': '하동 하수처리장 태양광', 'busan': '부산역 선상주차장 태양광',
 'incheon': '신인천 수산정수장 태양광', 'icheon': '백사면A 태양광',
 'eumseong': '감우리 태양광', 'jeju_west': '무릉리 태양광',
 'jeju_south': '위미2리 태양광', 'jeju_east': '송당리 태양광',
 'jeju_north': '와산리 태양광'}
CITY_NAMES = {'samcheok': 'Samcheok',
              'iksan': 'Iksan', 'andong': 'Andong'}

def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')

def request(url):
    # Cached callers never repeat completed requests. Rate limits stop the run.
    with urlopen(url, timeout=180) as response:
        return response.read()

REQUEST_LOCK = threading.Lock()
LAST_REQUEST = 0.0

def fetch_year(job):
    global LAST_REQUEST
    region, loc, year = job
    path = OUT / 'raw' / f'{region}_{year}.json.gz'
    if path.exists() and path.with_suffix('.meta.json').exists():
        return
    params = dict(latitude=loc['latitude'], longitude=loc['longitude'],
        start_date=f'{year}-01-01', end_date=f'{year}-12-31' if year < 2026 else '2026-02-28',
        hourly=','.join(HOURLY), models='jma_msm', timezone='Asia/Seoul')
    url = 'https://previous-runs-api.open-meteo.com/v1/forecast?' + urlencode(params)
    with REQUEST_LOCK:
        time.sleep(max(0, 4.0 - (time.monotonic() - LAST_REQUEST)))
        LAST_REQUEST = time.monotonic()
    raw = request(url)
    assert 'hourly' in json.loads(raw)
    temporary = path.with_suffix('.tmp')
    with gzip.open(temporary, 'wb') as target:
        target.write(raw)
    temporary.replace(path)
    write_json(path.with_suffix('.meta.json'), dict(url=url, parameters=params,
        retrieved_at_utc=datetime.now(timezone.utc).isoformat(),
        sha256_uncompressed=hashlib.sha256(raw).hexdigest(),
        model='jma_msm', publication_timestamp_available=False))
    print(f'FETCH {region} {year}', flush=True)

def main():
    for folder in ('raw', 'daily', 'training', 'geocoding'):
        (OUT / folder).mkdir(parents=True, exist_ok=True)
    coords = pd.read_csv(ROOT / 'datasets/multi_plant/raw/15147894.csv', encoding='cp949')
    locations = {'yeongwol': dict(latitude=37.18, longitude=128.46,
        representative='영월 ASOS 지역', coordinate_source='https://www.weather.go.kr/download_01/climate_wind.pdf',
        mapping_type='regional_proxy_not_individual_site')}
    for region, name in POINT_NAMES.items():
        row = coords[coords['발전소명'].str.strip().eq(name)].iloc[0]
        locations[region] = dict(latitude=float(row['위도']), longitude=float(row['경도']),
          representative=name, coordinate_source='data.go.kr/15147894',
          mapping_type='regional_proxy_not_individual_site')
    for region, name in CITY_NAMES.items():
        path = OUT / 'geocoding' / f'{region}.json'
        url = 'https://geocoding-api.open-meteo.com/v1/search?' + urlencode(
            dict(name=name, count=10, language='en', countryCode='KR'))
        if not path.exists():
            write_json(path, dict(url=url, response=json.loads(request(url))))
        candidates = json.loads(path.read_text(encoding='utf-8'))['response']['results']
        row = next(r for r in candidates if r['country_code'] == 'KR' and r['name'].lower() == name.lower())
        locations[region] = dict(latitude=row['latitude'], longitude=row['longitude'],
          representative=row['name'], coordinate_source=url,
          mapping_type='city_center_regional_proxy_not_individual_site')
    write_json(OUT / 'locations.json', locations)
    plants = json.loads((ROOT / 'datasets/multi_plant/catalog.json').read_text(encoding='utf-8'))['plants']
    approved=set(json.loads((ROOT/'tools/aiops/approved_plants.json').read_text(encoding='utf-8')))
    plants=[p for p in plants if p['plant_id'] in approved]
    mappings = [dict(plant_id=p['plant_id'], name=p['name'], region=SOURCE_REGION[p['source_id']],
        generation_file='multi_plant/'+p['daily_file'], generation_status=p['status']) for p in plants]
    mappings.append(dict(plant_id='15043409_u1', name='하동하수처리장', region='hadong',
        generation_file='hadong_daily_full.csv', generation_status='existing_baseline'))
    for sid, name, region in [('15043390','삼척사택','samcheok'),
                              ('15043397','안동소내','andong'),('15156688','부산철도2호기','busan')]:
        mappings.append(dict(plant_id=sid, name=name, region=region,
            generation_file=None, generation_status='raw_only_not_daily_training'))
    write_json(OUT / 'plant_mapping.json', mappings)
    # At most ~470 weighted calls/minute (12 variables, annual chunks).
    jobs = [(region, loc, year) for year in range(2026, 2017, -1)
            for region, loc in locations.items()]
    pool = ThreadPoolExecutor(max_workers=3)
    try:
        for _ in pool.map(fetch_year, jobs):
            pass
    finally:
        pool.shutdown(wait=True, cancel_futures=True)
    all_daily = {}
    coverage = []
    for region, loc in locations.items():
        frames = []
        for year in range(2018, 2027):
            start, end = f'{year}-01-01', f'{year}-12-31' if year < 2026 else '2026-02-28'
            path = OUT / 'raw' / f'{region}_{year}.json.gz'
            with gzip.open(path, 'rb') as source:
                raw = source.read()
            meta = json.loads(path.with_suffix('.meta.json').read_text(encoding='utf-8'))
            assert hashlib.sha256(raw).hexdigest() == meta['sha256_uncompressed']
            data = json.loads(raw)
            assert data['utc_offset_seconds'] == 32400
            frame = pd.DataFrame(data['hourly']).set_index('time')
            frame.index = pd.to_datetime(frame.index)
            expected = pd.date_range(start, pd.Timestamp(end) + pd.Timedelta(hours=23), freq='h')
            assert frame.index.equals(expected), (region, year, 'hourly calendar mismatch')
            frames.append(frame)
        hourly = pd.concat(frames)
        assert not hourly.index.duplicated().any()
        daily = pd.DataFrame(index=pd.date_range('2018-01-01', '2026-02-28'))
        for lead in (1, 2):
            for var in VARIABLES:
                col = f'{var}_previous_day{lead}'
                grouped = hourly[col].resample('D')
                counts = grouped.count()
                if var in ('shortwave_radiation', 'sunshine_duration', 'precipitation'):
                    values = grouped.sum(min_count=24)
                else:
                    values = grouped.mean().where(counts == 24)
                if var == 'shortwave_radiation': values *= 0.0036
                if var == 'sunshine_duration': values /= 3600
                daily[col] = values
                daily[col+'_valid_hours'] = counts
        daily.index.name = 'target_date'
        daily.to_csv(OUT / 'daily' / f'{region}.csv', float_format='%.6f')
        all_daily[region] = daily
        for col in HOURLY:
            valid = daily[col].dropna()
            coverage.append(dict(region=region, variable=col, days=len(valid),
                first=str(valid.index.min().date()) if len(valid) else None,
                last=str(valid.index.max().date()) if len(valid) else None))
        print(f'DAILY {region} complete day1={daily[[v+"_previous_day1" for v in VARIABLES]].notna().all(axis=1).sum()}', flush=True)
    records = []
    for item in mappings:
        if item['generation_file'] is None: continue
        gen = pd.read_csv(ROOT / 'datasets' / item['generation_file'])
        gen['target_date'] = pd.to_datetime(gen['date'])
        keep = ['target_date', 'gen_kwh'] + (['generation_valid'] if 'generation_valid' in gen else [])
        merged = gen[keep].merge(all_daily[item['region']], on='target_date', how='left', validate='one_to_one')
        for lead in (1, 2):
            merged[f'forecast_day{lead}_complete'] = merged[[v+f'_previous_day{lead}' for v in VARIABLES]].notna().all(axis=1)
        merged.to_csv(OUT / 'training' / (item['plant_id']+'.csv'), index=False, float_format='%.6f')
        records.append(dict(plant_id=item['plant_id'], rows=len(merged),
            complete_day1=int(merged.forecast_day1_complete.sum()), complete_day2=int(merged.forecast_day2_complete.sum())))
    write_json(OUT / 'validation.json', dict(regions=len(locations), mapped_plants=len(mappings),
        training_files=len(records), raw_files=len(locations)*9,
        hourly_rows=len(locations)*len(hourly), daily_rows=sum(map(len,all_daily.values())),
        sha256_and_hourly_calendars_verified=True, publication_cutoff_verified=False, plants=records))
    pd.DataFrame(coverage).to_csv(OUT / 'coverage.csv', index=False)
    counts = {r['plant_id']: r for r in records}
    lines = ['# 발전소별 예보 학습 파일', '',
        '지역 대표 좌표를 공유한다. 아래 완전 일수는 예보 6개 변수의 보유 일수이며 발전 실적 품질·운영 마감 시각 가용성을 보장하지 않는다.', '',
        '| 발전소/호기 | 지역 | 24시간 예보 완전 일수 | 48시간 예보 완전 일수 | 파일 |',
        '| --- | --- | ---: | ---: | --- |']
    for item in mappings:
        pid = item['plant_id']
        row = counts.get(pid)
        lines.append(f"| {item['name']} ({pid}) | {item['region']} | " +
            (f"{row['complete_day1']} | {row['complete_day2']} | [CSV](training/{pid}.csv) |" if row
             else '— | — | 지역 예보만 보관; 일별 학습 미지원 |'))
    (OUT / 'INDEX.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    (OUT / 'README.md').write_text((Path(__file__).parent / 'DATASET_README.md').read_text(encoding='utf-8'), encoding='utf-8')
    index_path = ROOT / 'datasets/README.md'
    index = index_path.read_text(encoding='utf-8')
    marker = '## 발전소 지역별 과거 예보 저장'
    if marker not in index:
        index_path.write_text(index + '\n\n' + marker + '\n\n'
            '[`plant_forecasts/`](plant_forecasts/README.md)에 Open-Meteo JMA MSM 과거 예보 원본과 '
            '지역별 일 집계, 발전소별 학습 테이블을 저장한다. 6개 변수(일사량·기온·일조시간·구름량·강수량·풍속)의 '
            '24/48시간 선행 예보를 요청하며 실제 유효 기간은 `coverage.csv`에 기록한다. '
            '출처·CC BY 4.0 이용 조건·단위·집계법·지역 대표 좌표의 한계는 해당 README에 있다. '
            '생성 도구는 [`../tools/build_plant_forecasts/`](../tools/build_plant_forecasts/README.md)다. '
            '**발표 시각이 없는 고정 선행시간 자료이므로 운영 예측 마감 기준의 누수 검증은 미완료다.**\n', encoding='utf-8')
    print('DONE', flush=True)

if __name__ == '__main__':
    main()
