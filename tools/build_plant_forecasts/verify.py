"""Independently recompute every daily value and check generation joins."""
import gzip
import json
from pathlib import Path
import numpy as np
import pandas as pd
from build import OUT, ROOT, VARIABLES, HOURLY, write_json

checks = 0
regions = json.loads((OUT/'locations.json').read_text(encoding='utf-8'))
for region in regions:
    frames = []
    for path in sorted((OUT/'raw').glob(f'{region}_*.json.gz')):
        with gzip.open(path) as f:
            raw = json.load(f)
        units = dict(shortwave_radiation='W/m²', temperature_2m='°C', sunshine_duration='s',
                     cloud_cover='%', precipitation='mm', wind_speed_10m='km/h')
        for lead in (1, 2):
            for var, unit in units.items():
                assert raw['hourly_units'][f'{var}_previous_day{lead}'] == unit
        frames.append(pd.DataFrame(raw['hourly']))
    hourly = pd.concat(frames, ignore_index=True)
    assert not hourly.time.duplicated().any()
    daily = pd.read_csv(OUT/'daily'/f'{region}.csv')
    assert daily.target_date.tolist() == sorted(set(hourly.time.str[:10]))
    for col in HOURLY:
        array = hourly[col].to_numpy(dtype=float).reshape(-1,24)
        counts = np.isfinite(array).sum(axis=1)
        assert np.array_equal(counts, daily[col+'_valid_hours'].to_numpy())
        if col.startswith(('shortwave_radiation_', 'sunshine_duration_', 'precipitation_')):
            expected = np.sum(array, axis=1)
        else:
            expected = np.mean(array, axis=1)
        if col.startswith('shortwave_radiation_'): expected *= 0.0036
        if col.startswith('sunshine_duration_'): expected /= 3600
        np.testing.assert_allclose(expected, daily[col], atol=0.00000051, rtol=0, equal_nan=True)
        if not col.startswith('temperature_2m_'):
            assert np.all(array[np.isfinite(array)] >= 0)
        if col.startswith('cloud_cover_'):
            assert np.all(array[np.isfinite(array)] <= 100)
        if col.startswith('sunshine_duration_'):
            assert np.all(array[np.isfinite(array)] <= 3600)
        checks += len(daily)
for item in json.loads((OUT/'plant_mapping.json').read_text(encoding='utf-8')):
    if item['generation_file'] is None: continue
    source = pd.read_csv(ROOT/'datasets'/item['generation_file'])
    saved = pd.read_csv(OUT/'training'/(item['plant_id']+'.csv'))
    assert saved.target_date.tolist() == source.date.tolist()
    np.testing.assert_allclose(saved.gen_kwh,source.gen_kwh,rtol=0,atol=0.00000051,equal_nan=True)
    daily = pd.read_csv(OUT/'daily'/(item['region']+'.csv')).set_index('target_date')
    joined = daily.reindex(saved.target_date)
    np.testing.assert_allclose(saved[HOURLY],joined[HOURLY],rtol=0,atol=0,equal_nan=True)
    if 'generation_valid' in source:
        assert saved.generation_valid.equals(source.generation_valid)
    for lead in (1,2):
        expected = saved[[v+f'_previous_day{lead}' for v in VARIABLES]].notna().all(axis=1)
        assert expected.equals(saved[f'forecast_day{lead}_complete'])
write_json(OUT/'verification.json',dict(passed=True,daily_values_recomputed=checks,
    hourly_bounds_checked=True,target_date_join_checked=True,generation_preserved=True,
    publication_cutoff_verified=False))
print(f'PASS: {checks} daily values, all generation and target-date joins')
