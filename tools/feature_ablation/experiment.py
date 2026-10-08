"""Causal input-feature ablation; isolated from serving and other benchmark runs."""
import os
os.environ.setdefault('TF_ENABLE_ONEDNN_OPTS', '0')
os.environ.setdefault('TF_CPP_MIN_LOG_LEVEL', '2')
os.environ.setdefault('OMP_NUM_THREADS', '2')
os.environ.setdefault('TF_NUM_INTRAOP_THREADS', '2')
os.environ.setdefault('TF_NUM_INTEROP_THREADS', '1')
import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import sys
import time

if '--stage' in sys.argv and sys.argv[sys.argv.index('--stage')+1] == 'lstm':
    import tensorflow as tf
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'docs/proposal/evidence/feature_ablation_20261007'
DATA = ROOT / 'datasets'
SEQ = 20
VARIANTS = {
    'base': ['generation', 'gsr_lag1'],
    'calendar': ['generation', 'gsr_lag1', 'season_sin', 'season_cos'],
    'temperature': ['generation', 'gsr_lag1', 'temperature_lag1'],
    'sunshine': ['generation', 'gsr_lag1', 'sunshine_lag1'],
    'expanded': ['generation', 'gsr_lag1', 'temperature_lag1', 'sunshine_lag1', 'season_sin', 'season_cos'],
    'forecast': ['generation', 'forecast_gsr'],
    'forecast_expanded': ['generation', 'gsr_lag1', 'temperature_lag1', 'sunshine_lag1', 'season_sin', 'season_cos', 'forecast_gsr', 'forecast_sunshine', 'forecast_cloud'],
}
LSTM_VARIANTS = ['base', 'expanded', 'forecast', 'forecast_expanded']


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str)+'\n', encoding='utf-8')


def scores(y, p):
    return {'rmse_kwh': float(np.sqrt(np.mean((y-p)**2))), 'mae_kwh': float(np.mean(np.abs(y-p)))}


def windows(frame):
    # X ends on t-1; target is t. Calendar fields at row d refer to d+1, known in advance.
    a = frame.to_numpy(dtype=float)
    return np.array([a[i-SEQ:i] for i in range(SEQ, len(a))]), a[SEQ:, 0], frame.index[SEQ:]


def causal_features(generation, gsr, temp, sunshine):
    d = pd.DataFrame(index=generation.index)
    d['generation'] = generation
    d['gsr_lag1'] = gsr.reindex(d.index-pd.Timedelta(days=1)).to_numpy()
    d['temperature_lag1'] = temp.reindex(d.index-pd.Timedelta(days=1)).to_numpy()
    d['sunshine_lag1'] = sunshine.reindex(d.index-pd.Timedelta(days=1)).to_numpy()
    phase = 2*np.pi*((d.index+pd.Timedelta(days=1)).dayofyear-1)/365.2425
    d['season_sin'], d['season_cos'] = np.sin(phase), np.cos(phase)
    return d


def prepare():
    OUT.mkdir(parents=True, exist_ok=True)
    for name in ['arrays', 'predictions', 'histories']:
        (OUT/name).mkdir(exist_ok=True)
    (OUT/'.gitignore').write_text('arrays/\n*.log\n', encoding='utf-8')
    catalog = json.loads((DATA/'multi_plant/catalog.json').read_text(encoding='utf-8'))
    plants, excluded, hashes = [], [], {}
    def hashed(path):
        hashes[path.relative_to(ROOT).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    def save(key, name, region, frame, variants, fixed_test=False):
        assert frame.index.is_unique and frame.index.to_series().diff().dropna().eq(pd.Timedelta(days=1)).all()
        X, y, dates = windows(frame)
        if fixed_test:
            tr = np.flatnonzero(dates < '2024-07-01')
            va = np.flatnonzero((dates >= '2024-07-01') & (dates < '2025-01-01'))
            te = np.flatnonzero(dates >= '2025-01-01')
        else:
            tr, va, te = np.arange(len(y)-545), np.arange(len(y)-545,len(y)-365), np.arange(len(y)-365,len(y))
        assert len(tr)>=365 and len(te)==365 and np.isfinite(y).all()
        assert np.isfinite(X[:,:,frame.columns.get_loc('gsr_lag1')]).all()
        for v in variants:
            cols = [frame.columns.get_loc(c) for c in VARIANTS[v]]
            np.savez_compressed(OUT/'arrays'/f'{key}_{v}.npz', X=X[:,:,cols].astype('float32'), y=y, dates=dates.strftime('%Y-%m-%d').to_numpy(dtype=str), tr=tr, va=va, te=te)
        frame.to_csv(OUT/'arrays'/f'{key}_features.csv', index_label='date')
        plants.append({'plant_id':key,'name':name,'region':region,'variants':variants,'rows':len(frame),
                       'train':[str(dates[tr[0]].date()),str(dates[tr[-1]].date()),len(tr)],
                       'validation':[str(dates[va[0]].date()),str(dates[va[-1]].date()),len(va)],
                       'test':[str(dates[te[0]].date()),str(dates[te[-1]].date()),len(te)],
                       'missing_counts':{c:int(frame[c].isna().sum()) for c in frame}})
    hp=DATA/'hadong_daily_full.csv'; hashed(hp)
    h=pd.read_csv(hp,parse_dates=['date']).set_index('date')
    frame=causal_features(h.gen_kwh,h.gy_gsr,h.gy_max_ta,h.gy_ss).loc['2022-07-02':'2025-12-31']
    fp=DATA/'raw/wx_prevruns_daily.csv'; hashed(fp)
    forecast=pd.read_csv(fp,parse_dates=['date']).set_index('date')
    for name, source in [('forecast_gsr','shortwave_radiation'),('forecast_sunshine','sunshine_duration'),('forecast_cloud','cloud_cover')]:
        frame[name]=forecast[source+'_previous_day1'].reindex(frame.index+pd.Timedelta(days=1)).to_numpy()
    oldp=DATA/'hadong_upload_forecast_jma.csv'; hashed(oldp)
    old=pd.read_csv(oldp,parse_dates=['Date']).set_index('Date').reindex(frame.index)
    assert np.allclose(frame.forecast_gsr, old.Volume) and np.allclose(frame.generation,old.Close)
    assert frame[['forecast_gsr','forecast_sunshine','forecast_cloud']].notna().all().all()
    save('hadong','하동하수처리장','경남 하동',frame,list(VARIANTS),True)
    for plant in catalog['plants']:
        eligible=[x for x in plant['uploads'] if x['rows']>=930]
        if not eligible:
            excluded.append({'plant_id':plant['plant_id'],'reason':'no contiguous upload segment >=930 days'})
            continue
        chosen=max(eligible,key=lambda x:(x['end'],x['rows']))
        up=DATA/'multi_plant'/chosen['file']; hashed(up)
        upload=pd.read_csv(up,parse_dates=['Date']).set_index('Date')
        dp=DATA/'multi_plant'/plant['daily_file']; hashed(dp)
        daily=pd.read_csv(dp,parse_dates=['date']).set_index('date')
        frame=causal_features(daily.gen_kwh,daily.gsr_mj_m2,daily.max_temp_c,daily.sunshine_hours).reindex(upload.index)
        # First generation date can still have weather from the preceding calendar day.
        frame['gsr_lag1']=daily.gsr_lag1_mj_m2.reindex(upload.index)
        assert np.allclose(frame.gsr_lag1,upload.Volume)
        # Cap long histories identically for every variant of this plant; no performance-based selection.
        frame=frame.iloc[-1825:]
        save(plant['plant_id'],plant['name']+' #'+plant['unit'],plant['region'],frame,list(VARIANTS)[:5])
    protocol={'seed_list':[42,43,44],'variants':VARIANTS,'lstm_variants':LSTM_VARIANTS,
              'lstm':{'architecture':'32-32-16 stacked LSTM + Dense16 relu + Dense1, only input width changes','lr':0.001,'epochs':80,'batch_size':32,'selection':'minimum validation MSE checkpoint, no test-based tuning; no refit'},
              'xgboost':{'max_depth':3,'learning_rate':0.03,'n_estimators':600,'early_stopping_rounds':40,'subsample':1,'colsample_bytree':1,'reg_lambda':10,'selection':'validation early stopping, no refit'},
              'forecast_timing':'Previous Runs previous_day1 for d+1 stored at row d; publication availability assumed per repository, not independently timestamp-audited',
              'observed_weather_timing':'row d uses observations d-1; 20-row input ends t-1, so latest observed weather is t-2',
              'evaluation':'rolling one-day forecast with observed generation through t-1; fixed trained model; all variants within a plant have identical dates and targets; target calendar known beforehand',
              'missing':'XGBoost native missing; LSTM per-channel training-window median, then training-only minmax; no backward fill',
              'plants':plants,'excluded':excluded,'source_sha256':hashes,
              'not_independent':'nearby plants and units share weather; heterogeneous plant test periods; this is retrospective, not a new blind dataset'}
    dump(OUT/'protocol.json',protocol)
    dump(OUT/'environment.json',{x:importlib.metadata.version(x) for x in ['numpy','pandas','tensorflow','keras','xgboost','scikit-learn']})
    print(f'Prepared {len(plants)} units incl Hadong; excluded {len(excluded)}',flush=True)


def load(key,v):
    return dict(np.load(OUT/'arrays'/f'{key}_{v}.npz'))


def save_predictions(key,v,learner,z,pv,pt):
    ix=np.r_[z['va'],z['te']]
    pd.DataFrame({'date':z['dates'][ix],'split':['validation']*len(z['va'])+['test']*len(z['te']),
                  'actual_kwh':z['y'][ix],'predicted_kwh':np.r_[pv,pt]}).to_csv(OUT/'predictions'/f'{key}_{v}_{learner}.csv',index=False)


def trees():
    from xgboost import XGBRegressor
    protocol=json.loads((OUT/'protocol.json').read_text(encoding='utf-8'))
    results=[]
    for plant in protocol['plants']:
        key=plant['plant_id']
        for v in plant['variants']:
            z=load(key,v); x=z['X'].reshape(len(z['y']),-1)
            model=XGBRegressor(**{k:v for k,v in protocol['xgboost'].items() if k!='selection'},n_jobs=2,tree_method='hist',random_state=42)
            start=time.perf_counter()
            model.fit(x[z['tr']],z['y'][z['tr']],eval_set=[(x[z['va']],z['y'][z['va']])],verbose=False)
            pv=np.maximum(model.predict(x[z['va']]),0);pt=np.maximum(model.predict(x[z['te']]),0)
            save_predictions(key,v,'xgb',z,pv,pt)
            r={'plant_id':key,'name':plant['name'],'region':plant['region'],'variant':v,'learner':'XGBoost',
               'features':len(VARIANTS[v]),'rounds':model.best_iteration+1,'seconds':time.perf_counter()-start,
               'validation_rmse_kwh':scores(z['y'][z['va']],pv)['rmse_kwh'],**scores(z['y'][z['te']],pt)}
            results.append(r)
            pd.DataFrame(results).to_csv(OUT/'xgb_metrics.csv',index=False)
            print(f"XGB {key} {v} val={r['validation_rmse_kwh']:.2f} test={r['rmse_kwh']:.2f}",flush=True)
        z=load(key,'base')
        for name,pred in [('persistence',z['X'][:,-1,0]),('mean7',z['X'][:,-7:,0].mean(axis=1))]:
            save_predictions(key,name,'naive',z,pred[z['va']],pred[z['te']])


def lstm():
    from tensorflow import keras
    tf.config.threading.set_intra_op_parallelism_threads(2)
    tf.config.threading.set_inter_op_parallelism_threads(1)
    tf.config.experimental.enable_op_determinism()
    protocol=json.loads((OUT/'protocol.json').read_text(encoding='utf-8'))
    results=[]
    for v in LSTM_VARIANTS:
        z=load('hadong',v); X=z['X'];y=z['y'];tr,va,te=z['tr'],z['va'],z['te']
        train=X[tr].reshape(-1,X.shape[-1]);median=np.nanmedian(train,axis=0);median=np.nan_to_num(median)
        train=np.where(np.isfinite(train),train,median)
        lo=train.min(axis=0);scale=np.maximum(train.max(axis=0)-lo,1e-6)
        xx=((np.where(np.isfinite(X),X,median)-lo)/scale).astype('float32')
        yl=y[tr].min();ys=max(y[tr].max()-yl,1e-6); yy=((y-yl)/ys).astype('float32')
        pv_all=[];pt_all=[]
        for seed in protocol['seed_list']:
            keras.backend.clear_session();keras.utils.set_random_seed(seed)
            model=keras.Sequential([keras.layers.Input((SEQ,X.shape[-1])),keras.layers.LSTM(32,return_sequences=True),keras.layers.LSTM(32,return_sequences=True),keras.layers.LSTM(16),keras.layers.Dense(16,activation='relu'),keras.layers.Dense(1)])
            model.compile(optimizer=keras.optimizers.Adam(0.001),loss='mse')
            class Best(keras.callbacks.Callback):
                def __init__(self):
                    super().__init__();self.score=float('inf');self.epoch=0;self.weights=None
                def on_epoch_end(self,epoch,logs=None):
                    score=float(logs['val_loss'])
                    if score<self.score:
                        self.score=score;self.epoch=epoch+1;self.weights=self.model.get_weights()
                    if (epoch+1)%20==0:
                        print(f'LSTM {v} seed={seed} epoch={epoch+1} val_rmse={np.sqrt(score)*ys:.2f}',flush=True)
            best=Best(); start=time.perf_counter()
            history=model.fit(xx[tr],yy[tr],validation_data=(xx[va],yy[va]),epochs=80,batch_size=32,shuffle=False,verbose=0,callbacks=[best])
            assert best.weights is not None
            model.set_weights(best.weights)
            pv=np.maximum(model.predict(xx[va],verbose=0).ravel()*ys+yl,0)
            pt=np.maximum(model.predict(xx[te],verbose=0).ravel()*ys+yl,0)
            save_predictions('hadong',v,f'lstm_seed{seed}',z,pv,pt)
            dump(OUT/'histories'/f'{v}_seed{seed}.json',history.history)
            r={'plant_id':'hadong','variant':v,'seed':seed,'selected_epoch':best.epoch,'seconds':time.perf_counter()-start,'validation_rmse_kwh':scores(y[va],pv)['rmse_kwh'],**scores(y[te],pt)}
            results.append(r);pd.DataFrame(results).to_csv(OUT/'lstm_seed_metrics.csv',index=False)
            pv_all.append(pv);pt_all.append(pt)
            print(f"DONE LSTM {v} seed={seed} test={r['rmse_kwh']:.2f}",flush=True)
        save_predictions('hadong',v,'lstm_mean3',z,np.mean(pv_all,axis=0),np.mean(pt_all,axis=0))
    print('LSTM complete',flush=True)


def report():
    assert json.loads((OUT/'input_audit.json').read_text(encoding='utf-8'))['passed']
    x=pd.read_csv(OUT/'xgb_metrics.csv'); p=json.loads((OUT/'protocol.json').read_text(encoding='utf-8'))
    expected=sum(len(a['variants']) for a in p['plants'])
    assert len(x)==expected
    seed_metrics=pd.read_csv(OUT/'lstm_seed_metrics.csv')
    assert len(seed_metrics)==12 and set(zip(seed_metrics.variant,seed_metrics.seed))=={(v,s) for v in LSTM_VARIANTS for s in [42,43,44]}
    rows=[]
    for file in (OUT/'predictions').glob('hadong_*.csv'):
        d=pd.read_csv(file);d=d[d.split=='test']
        rows.append({'model':file.stem.removeprefix('hadong_'),**scores(d.actual_kwh.to_numpy(),d.predicted_kwh.to_numpy())})
    metrics=pd.DataFrame(rows).sort_values('rmse_kwh');metrics.to_csv(OUT/'hadong_metrics.csv',index=False)
    multi=x[x.plant_id!='hadong'].pivot(index='plant_id',columns='variant',values='rmse_kwh')
    summaries=[]
    for v in list(VARIANTS)[1:5]:
        improvement=100*(1-multi[v]/multi['base'])
        summaries.append({'variant':v,'units':len(improvement),'improved_units':int((improvement>0).sum()),'median_rmse_reduction_pct':float(improvement.median()),'mean_rmse_reduction_pct':float(improvement.mean()),'min_pct':float(improvement.min()),'max_pct':float(improvement.max())})
    pd.DataFrame(summaries).to_csv(OUT/'multi_plant_summary.csv',index=False)
    selected=[]
    for key,group in x[x.plant_id!='hadong'].groupby('plant_id'):
        best=group.loc[group.validation_rmse_kwh.idxmin()]
        base=group[group.variant=='base'].iloc[0]
        selected.append({'plant_id':key,'validation_selected_variant':best.variant,'test_rmse_kwh':best.rmse_kwh,
                         'base_test_rmse_kwh':base.rmse_kwh,'reduction_pct':100*(1-best.rmse_kwh/base.rmse_kwh)})
    pd.DataFrame(selected).to_csv(OUT/'validation_selected_features.csv',index=False)
    audit={'passed':True,'prediction_files':0,'rows_checked':0}
    for file in (OUT/'predictions').glob('*.csv'):
        d=pd.read_csv(file); assert np.isfinite(d[['actual_kwh','predicted_kwh']]).all().all()
        assert d.date.is_unique and (d.predicted_kwh>=0).all()
        assert (d.split=='test').sum()==365
        assert d[d.split=='validation'].date.max()<d[d.split=='test'].date.min()
        key=next(a['plant_id'] for a in p['plants'] if file.name.startswith(a['plant_id']+'_'))
        z=load(key,'base');ix=np.r_[z['va'],z['te']]
        assert np.array_equal(d.date,z['dates'][ix])
        assert np.allclose(d.actual_kwh,z['y'][ix],atol=1e-8,rtol=0)
        audit['prediction_files']+=1;audit['rows_checked']+=len(d)
    # Audit cached feature dates and observation/forecast join, including future perturbation.
    hd=pd.read_csv(DATA/'hadong_daily_full.csv',parse_dates=['date']).set_index('date')
    altered=hd.copy(); cutoff=pd.Timestamp('2024-01-15');altered.loc[cutoff:,['gen_kwh','gy_gsr','gy_max_ta','gy_ss']]=999999
    original=causal_features(hd.gen_kwh,hd.gy_gsr,hd.gy_max_ta,hd.gy_ss)
    mutated=causal_features(altered.gen_kwh,altered.gy_gsr,altered.gy_max_ta,altered.gy_ss)
    assert np.allclose(original.loc[:cutoff-pd.Timedelta(days=1)],mutated.loc[:cutoff-pd.Timedelta(days=1)],equal_nan=True)
    for path,sha in p['source_sha256'].items():
        assert hashlib.sha256((ROOT/path).read_bytes()).hexdigest()==sha
    audit['future_observation_perturbation_passed']=True;audit['source_hashes_passed']=True
    dump(OUT/'audit.json',audit)
    # Paired 14-day circular block bootstrap; prediction-average across 3 seeds, not best seed.
    def prediction(v):
        d=pd.read_csv(OUT/'predictions'/f'hadong_{v}_lstm_mean3.csv');return d[d.split=='test']
    rng=np.random.default_rng(42);comparisons=[]
    for baseline,v in [('base',v) for v in LSTM_VARIANTS[1:]]+[('forecast','forecast_expanded')]:
        base=prediction(baseline);d=prediction(v); assert np.array_equal(base.date,d.date)
        y=d.actual_kwh.to_numpy();b=base.predicted_kwh.to_numpy();q=d.predicted_kwh.to_numpy();diff=[]
        for _ in range(1000):
            idx=np.concatenate([(rng.integers(len(y))+np.arange(14))%len(y) for _ in range(27)])[:len(y)]
            diff.append(scores(y[idx],q[idx])['rmse_kwh']-scores(y[idx],b[idx])['rmse_kwh'])
        comparisons.append({'baseline':baseline,'variant':v,'rmse_difference_kwh':scores(y,q)['rmse_kwh']-scores(y,b)['rmse_kwh'],'paired_95pct_block_interval_kwh':np.quantile(diff,[.025,.975]).tolist()})
    dump(OUT/'paired_bootstrap.json',comparisons)
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(1,2,figsize=(12,4.8))
    variants=LSTM_VARIANTS
    labels=['Base (2)','Past weather +\nseason (6)','Forecast GSR (2)','Forecast +\nexpanded (9)']
    pos=np.arange(4)
    lm=[float(metrics.loc[metrics.model==v+'_lstm_mean3','rmse_kwh'].iloc[0]) for v in variants]
    xm=[float(metrics.loc[metrics.model==v+'_xgb','rmse_kwh'].iloc[0]) for v in variants]
    axes[0].bar(pos-.18,lm,width=.36,label='LSTM: mean of 3 seeds',color='#3565a0')
    axes[0].bar(pos+.18,xm,width=.36,label='XGBoost',color='#e5a142')
    axes[0].set_xticks(pos,labels,fontsize=9);axes[0].set_ylabel('Test RMSE (kWh/day), lower is better')
    axes[0].set_title('Hadong: identical 365 test days in 2025');axes[0].legend(fontsize=8)
    for i,(a,b) in enumerate(zip(lm,xm)):
        axes[0].text(i-.18,a+1,f'{a:.1f}',ha='center',fontsize=8)
        axes[0].text(i+.18,b+1,f'{b:.1f}',ha='center',fontsize=8)
    distributions=[100*(1-multi[v]/multi['base']) for v in list(VARIANTS)[1:5]]
    axes[1].boxplot(distributions,labels=['Season','Temperature','Sunshine','All'],patch_artist=True)
    axes[1].axhline(0,color='gray',linestyle='--',linewidth=1)
    axes[1].set_ylabel('RMSE reduction vs base (%), positive is better')
    axes[1].set_title('32 additional units: XGBoost feature ablation')
    fig.text(.5,.005,'Past observed weather only; target-day observations excluded. Fixed temporal holdouts; units are not independent.',ha='center',fontsize=8)
    fig.tight_layout(rect=[0,.04,1,1]);fig.savefig(OUT/'comparison.png',dpi=160);plt.close(fig)
    lines=['# 예측 입력 변수 추가 실험','', '실행일: 2026-10-07. 서빙 모델·스케일러는 변경하지 않았다.','',
           '## 하동: 동일한 2025년 365일 평가','',
           '학습 정답: 2022-07-22~2024-06-30. 검증: 2024-07-01~2024-12-31. 시험: 2025-01-01~2025-12-31. 20일 입력. 검증 구간으로 XGBoost 반복 수/LSTM 체크포인트를 선택했고 재학습 없이 같은 시험일에 비교했다. 스케일·결측 대체는 학습 구간에서만 계산했다.','',
           '| 모델·변수 | RMSE (kWh/일) | MAE (kWh/일) |','| --- | ---: | ---: |']
    for r in metrics.to_dict('records'):
        lines.append(f"| {r['model']} | {r['rmse_kwh']:.3f} | {r['mae_kwh']:.3f} |")
    lines+=['','`lstm_mean3`는 시드 42·43·44 예측의 평균이다. 시드별 오차는 lstm_seed_metrics.csv에 있다.','',
            '## 추가 32개 호기: XGBoost 내 변수 비교','',
            '| 추가 변수 | 개선 호기 / 전체 | RMSE 감소율 중앙값 |','| --- | ---: | ---: |']
    for r in summaries:
        lines.append(f"| {r['variant']} | {r['improved_units']} / {r['units']} | {r['median_rmse_reduction_pct']:.2f}% |")
    lines+=['','감소율이 양수면 개선이다. 각 호기의 기준 모델과 같은 시험일로 비교했다. 호기별 시험 연도는 다를 수 있고, 같은 지역의 호기는 독립 표본이 아니다. 연속 930일 이상인 가장 최근 구간을 선택하고 최대 1,825일을 사용했다. 마지막 365일 시험, 그 전 180일 검증, 나머지 학습이다. 짧거나 보류된 호기는 제외했고 목록은 protocol.json에 있다.','',
            '## 변수와 한계','',
            '- base: 과거 발전량 + 하루 전 관측 일사량. calendar: 연중 날짜 sin/cos 추가. temperature/sunshine: 각각 하루 전 최고기온/일조시간 추가. expanded: 모두 추가.',
            '- forecast: 과거 발전량 + 대상일에 대한 하루 전 일사량 예보. forecast_expanded: expanded + 일사량·일조시간·구름량 예보. 예보 기온은 보유 자료에 없어 실험하지 않았다.',
            '- 모든 모델은 입력 마지막 날까지 실제 발전량이 관측된 다음 날 1일 예측이다. 한 번에 1년 전체를 예측한 결과가 아니다.',
            '- 실제 대상일 관측 날씨는 사용하지 않았다. 과거 예보의 정확한 공개 시각은 저장소의 가정을 따르며 별도로 시각 증빙을 검증하지 않았다.',
            '- LSTM은 동일한 3층 구조, 학습률 0.001, 80 epoch 예산, 시드 3개로 비교했다. 충분한 최적화나 모든 하이퍼파라미터 조합의 최적값을 보증하지 않는다.',
            '- XGBoost는 20일 창을 펼쳐 같은 설정으로 학습했다. LSTM과의 승패보다 각 학습기 안에서 변수의 효과를 해석한다.',
            '- 날씨 결측/관측소 대리값과 설비 상태 변화가 포함된다. 일사량 예보의 효과와 지역 일반화는 구분한다. 결과를 보고 시험 구간에 맞춰 재선택하지 않았다.',
            '- protocol.json(조건·출처 해시), predictions/(날짜별 예측), histories/(학습 곡선), paired_bootstrap.json(하동 LSTM 차이 구간), audit.json(검증)을 함께 확인한다.','']
    reduction=100*(1-lm[3]/lm[0])
    extra=100*(1-lm[3]/lm[2])
    lines[4:4]=[
        f'실행 결과: 과거 관측 변수만 늘린 LSTM은 RMSE {lm[0]:.2f} → {lm[1]:.2f}kWh/일로 악화됐다. 일사량 예보를 쓰면 {lm[2]:.2f}, 과거 정보와 일사량·일조시간·구름량 예보를 함께 쓰면 {lm[3]:.2f}kWh/일이었다. 기본 대비 {reduction:.2f}% 감소이며 일사량 예보 조합 대비 추가 개선은 {extra:.2f}%다.', '',
        '이 수치는 시드 3개의 평균 예측에 대한 오차다. 이 실험에서는 대상일 사전 예보의 효과가 가장 컸다. 과거 기온·일조시간·계절을 모두 추가한 다지역 XGBoost는 32개 중 13개 호기에서 개선됐고, 감소율 중앙값은 -0.23%로 일관된 이득이 없었다. 모든 발전소의 변수를 일괄 확대하기보다 별도 검증 구간에서 선택하는 편이 적절하다.', '',
        '날짜별 14일 블록 부트스트랩에서 하동 LSTM의 확장 예보 조합과 일사량 예보 조합 간 RMSE 차이의 95% 구간은 약 -3.18~-0.14kWh/일이었다. 이번 고정 분할에서의 차이이며 다른 연도·지역이나 재학습 성능을 보증하지 않는다.', '',
    ]
    lines+=['![입력 변수 비교](comparison.png)','']
    (OUT/'REPORT.md').write_text('\n'.join(lines),encoding='utf-8')
    print(metrics.to_string(index=False)); print(pd.DataFrame(summaries).to_string(index=False))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--stage',choices=['prepare','trees','lstm','report'],required=True)
    args=parser.parse_args(); {'prepare':prepare,'trees':trees,'lstm':lstm,'report':report}[args.stage]()
