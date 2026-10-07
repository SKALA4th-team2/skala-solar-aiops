"""Independently audit every stored window against the source's calendar dates."""
import json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'docs/proposal/evidence/feature_ablation_20261007'
protocol=json.loads((OUT/'protocol.json').read_text(encoding='utf-8'))
forecast=pd.read_csv(ROOT/'datasets/raw/wx_prevruns_daily.csv',parse_dates=['date']).set_index('date')
count=0
for plant in protocol['plants']:
    key=plant['plant_id']
    if key=='hadong':
        source=pd.read_csv(ROOT/'datasets/hadong_daily_full.csv',parse_dates=['date']).set_index('date')
        gsr,temp,sun='gy_gsr','gy_max_ta','gy_ss'
    else:
        source=pd.read_csv(ROOT/f'datasets/multi_plant/daily/{key}.csv',parse_dates=['date']).set_index('date')
        gsr,temp,sun='gsr_mj_m2','max_temp_c','sunshine_hours'
    reference_dates=None
    for variant in plant['variants']:
        z=np.load(OUT/'arrays'/f'{key}_{variant}.npz')
        dates=pd.to_datetime(z['dates'])
        if reference_dates is not None:
            assert np.array_equal(reference_dates,dates)
        reference_dates=dates
        assert np.allclose(z['y'],source.gen_kwh.reindex(dates),rtol=1e-10,atol=1e-8)
        assert z['tr'].max()<z['va'].min() and z['va'].max()<z['te'].min()
        for j in range(20):
            row_dates=dates-pd.Timedelta(days=20-j)
            wx_dates=row_dates-pd.Timedelta(days=1)
            for k,feature in enumerate(protocol['variants'][variant]):
                if feature=='generation':
                    expected=source.gen_kwh.reindex(row_dates).to_numpy()
                elif feature=='gsr_lag1':
                    expected=(source.gsr_lag1_mj_m2.reindex(row_dates) if key!='hadong' else source[gsr].reindex(wx_dates)).to_numpy()
                elif feature in ['temperature_lag1','sunshine_lag1']:
                    expected=source[temp if feature=='temperature_lag1' else sun].reindex(wx_dates).to_numpy()
                elif feature.startswith('season_'):
                    angle=2*np.pi*((row_dates+pd.Timedelta(days=1)).dayofyear-1)/365.2425
                    expected=(np.sin if feature=='season_sin' else np.cos)(angle)
                else:
                    column={'forecast_gsr':'shortwave_radiation','forecast_sunshine':'sunshine_duration','forecast_cloud':'cloud_cover'}[feature]+'_previous_day1'
                    expected=forecast[column].reindex(row_dates+pd.Timedelta(days=1)).to_numpy()
                    assert (row_dates+pd.Timedelta(days=1)<=dates).all()
                assert np.allclose(z['X'][:,j,k],expected,rtol=1e-6,atol=1e-6,equal_nan=True),(key,variant,feature,j)
                count+=len(dates)
result={'passed':True,'plants':len(protocol['plants']),'feature_cells_checked':count,
        'checks':['every historical feature against original date lookup','target-date equality','same test days across variants','disjoint ordered split indices','forecast_previous_day1 target alignment']}
(OUT/'input_audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(result,ensure_ascii=False,indent=2))
