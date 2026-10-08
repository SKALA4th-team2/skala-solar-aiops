"""Audit saved forecast results independently with calendar-based source lookup."""
import argparse
import csv
from collections import Counter
from datetime import date,timedelta,datetime
import hashlib
import json
import math
import pickle
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]


def read(path):return json.loads(path.read_text(encoding='utf-8'))
def rows(path):
    with path.open(encoding='utf-8-sig',newline='') as fp:return list(csv.DictReader(fp))
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def close(a,b):assert math.isclose(float(a),float(b),rel_tol=1e-6,abs_tol=1e-3),(a,b)


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--out',default='docs/proposal/evidence/forecast_models_20261007')
    ap.add_argument('--partial',action='store_true');ap.add_argument('--registry',action='store_true');args=ap.parse_args()
    out=ROOT/args.out;suffix='_partial' if args.partial else ''
    screening=read(out/'screening.json');plants=screening['admitted']
    if args.partial:
        assert not args.registry
        plants=[p for p in plants if (out/'plants'/p['plant_id']/'result.json').exists()]
    for rel,expected in read(out/'training_code_hashes.json').items():
        assert sha(ROOT/rel)==expected and sha(out/'source_snapshot'/rel)==expected
    if not args.partial:assert read(out/'training_integrity.json')['passed']
    all_metrics=[];checks=[]
    for plant in plants:
        pid=plant['plant_id'];dest=out/'plants'/pid;result=read(dest/'result.json');frozen=read(dest/'frozen_selection.json')
        source=ROOT/plant['source'];assert sha(source)==plant['source_sha256']
        raw={date.fromisoformat(r['target_date']):r for r in rows(source)}
        samples={}
        for r in rows(dest/'split_manifest.csv'):
            t=date.fromisoformat(r['date'][:10]);window=[]
            for d in [t-timedelta(days=lag) for lag in range(20,0,-1)]:
                row=raw[d];weather=raw[d+timedelta(days=1)]
                assert float(row.get('generation_valid',1))==1
                c=float(row['gen_kwh']);v=float(weather['shortwave_radiation_previous_day1'])
                assert math.isfinite(c) and c>=0 and math.isfinite(v) and 0<=v<=45
                window.append((c,v))
            assert float(raw[t].get('generation_valid',1))==1
            actual=float(raw[t]['gen_kwh']);assert math.isfinite(actual) and actual>=0
            phase='train' if t<date(2024,7,1) else 'validation' if t<date(2025,1,1) else 'test' if t<date(2026,1,1) else 'post_test'
            assert phase==r['split'];samples[t]=(window,actual,phase)
        vm=frozen['validation_metrics'];chosen=min(vm,key=lambda k:vm[k]['rmse_kwh'])
        assert chosen==result['selected_by_validation']==frozen['selected_by_validation']
        for phase in ['validation','test']:
            predictions=rows(dest/f'{phase}_predictions.csv')
            expected_dates=[d for d,s in samples.items() if s[2]==phase]
            assert [date.fromisoformat(r['date'][:10]) for r in predictions]==expected_dates
            actuals=[]
            for r in predictions:
                target=date.fromisoformat(r['date'][:10]);win,actual,_=samples[target];close(r['actual_kwh'],actual);actuals.append(actual)
                close(r['Persistence'],win[-1][0]);close(r['Mean7'],sum(v[0] for v in win[-7:])/7)
                denominator=sum(v[1] for v in win[-8:-1]);rule=sum(v[0] for v in win[-7:])*win[-1][1]/denominator if denominator>1e-6 else sum(v[0] for v in win[-7:])/7
                close(r['RuleC'],rule)
                for kind,weights in frozen['ensemble_weights'].items():
                    close(sum(weights),1);assert min(weights)>=0
                    if kind=='LSTM_Main_Ensemble':assert weights[0]>=.5
                    close(r[kind],sum(float(r[k])*weight for k,weight in zip(['LSTM','XGBoost','Prophet'],weights)))
            for kind,score in result[f'{phase}_metrics'].items():
                pred=[float(r[kind]) for r in predictions];assert all(math.isfinite(v) and v>=0 for v in pred)
                err=[p-y for p,y in zip(pred,actuals)];n=len(err)
                computed={'rmse_kwh':math.sqrt(sum(e*e for e in err)/n),'mae_kwh':sum(abs(e) for e in err)/n,
                          'wape_pct':100*sum(abs(e) for e in err)/sum(actuals),'bias_pct':100*sum(err)/sum(actuals)}
                assert score['n']==n
                for k,v in computed.items():close(score[k],v)
        for role in ['evaluation','release']:
            folder=dest/role;meta=read(folder/'metadata.json')
            assert meta['input_contract']=='solar_next_day_jma_msm_day1_v1'
            fit=[(d,v) for d,v in samples.items() if role=='release' or v[2] in ['train','validation']]
            assert meta['trained_targets']['last']==str(fit[-1][0])
            assert datetime.fromisoformat(frozen['frozen_utc'])<datetime.fromisoformat(meta['created_utc'])
            c=[value for _,(win,y,_) in fit for value in [y]+[p[0] for p in win]]
            v=[p[1] for _,(win,_,_) in fit for p in win]
            expected={'close_min':min(c),'close_max':max(c),'volume_min':min(v),'volume_max':max(v)}
            with (folder/'scaler.pkl').open('rb') as fp:scaler=pickle.load(fp)
            for k,value in expected.items():close(scaler[k],value);close(meta['scaler'][k],value)
            for f,digest in read(folder/'bundle_hashes.json').items():assert sha(folder/f)==digest
            check=read(dest/f'{role}_reload_check.json');assert check['passed'] and check['native_scaler_api_compatible']
        for kind,score in result['test_metrics'].items():
            all_metrics.append(dict(plant_id=pid,name=plant['name'],region=plant['region'],model=kind,
                 validation_selected=kind==chosen,validation_rmse_kwh=vm[kind]['rmse_kwh'],**score,
                 improvement_vs_mean7_pct=100*(1-score['rmse_kwh']/result['test_metrics']['Mean7']['rmse_kwh']),
                 improvement_vs_rulec_pct=100*(1-score['rmse_kwh']/result['test_metrics']['RuleC']['rmse_kwh'])))
        checks.append({'plant_id':pid,'passed':True})
    registry_count=0
    if args.registry:
        registry=read(out/'registry_index.json');assert not registry['production_promoted']
        records=registry['models'];pairs={(r['plant_id'],r['role']) for r in records}
        assert len(records)==len(pairs)==2*len(plants)
        assert pairs=={(p['plant_id'],role) for p in plants for role in ['evaluation','release']}
        for r in records:
            assert r['tensorflow_flavor'] and r['reload_passed']
            assert r['bundle_sha256']==sha(out/'plants'/r['plant_id']/r['role']/'bundle_hashes.json')
        registry_count=len(records)
    with (out/f'all_metrics{suffix}.csv').open('w',encoding='utf-8-sig',newline='') as fp:
        writer=csv.DictWriter(fp,fieldnames=list(all_metrics[0]));writer.writeheader();writer.writerows(all_metrics)
    selected=[r for r in all_metrics if r['validation_selected']];lstm=[r for r in all_metrics if r['model']=='LSTM']
    output={'passed':True,'partial':args.partial,'plants_checked':len(checks),'registry_versions_checked':registry_count,'checks':checks,
            'validation_selected_counts':dict(Counter(r['model'] for r in selected)),
            'lstm_beats_mean7_on_test':sum(r['improvement_vs_mean7_pct']>0 for r in lstm),
            'lstm_beats_rulec_on_test':sum(r['improvement_vs_rulec_pct']>0 for r in lstm)}
    (out/f'independent_audit{suffix}.json').write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding='utf-8')
    lines=['새 JMA MSM 예보 기반 모델 — 실제 학습 결과','',
           f'학습 완료 {len(checks)}개 호기, 제외 {len(screening["excluded"])}개 매핑 항목.',
           '기준 코드: GitHub main '+read(out/'github_review.json')['origin/main']['commit'],
           '입력: 연속 20일 × (당일 발전량, 다음 날 일사량 예보). 소수 예보와 0 발전량 허용.',
           '새 데이터는 JMA MSM 모델을 명시한 예보. 과거 ASOS 입력 모델을 재사용하지 않고 새로 학습.',
           '선택: 2024-07~12 검증. 시험: 2025년(품질상 제외된 창은 개소별 일수가 다름).',
           '주 모델 LSTM: 수업 32-32-16-Dense16-Dense1, 시드42, 검증 최소손실 epoch 선택.',
           'validation 모델 선택 분포: '+str(output['validation_selected_counts']),
           f'LSTM이 7일 평균보다 시험 RMSE가 낮은 호기: {output["lstm_beats_mean7_on_test"]}/{len(checks)}',
           f'LSTM이 예보 기반 RuleC보다 시험 RMSE가 낮은 호기: {output["lstm_beats_rulec_on_test"]}/{len(checks)}','',
           '발전소 | ID | 선택 모델 | LSTM RMSE(kWh/일) | 선택 모델 RMSE | 시험일수']
    for r in selected:
        l=next(a for a in lstm if a['plant_id']==r['plant_id'])
        lines.append(f'{r["name"]} | {r["plant_id"]} | {r["model"]} | {l["rmse_kwh"]:.2f} | {r["rmse_kwh"]:.2f} | {r["n"]}')
    lines+=['','파일: plants/<plant_id>/evaluation/ 와 release/ 에 각각 model.keras, scaler.pkl, scaler.json, xgboost.ubj, prophet.json, metadata.json, bundle_hashes.json.',
            'evaluation은 2024-12-31까지 학습하여 2025년 재생·AIOps 시연에 사용. release는 최대 2026-02-28까지 다시 학습한 최신 자료용 모델.',
            '여기에 적힌 시험 성능은 evaluation 모델의 결과. release 모델로 과거 시험을 재생하면 학습 데이터가 포함되므로 별도 성능으로 주장하지 않는다.',
            '앙상블 2종은 metadata.json의 가중치와 세 개별 모델을 함께 사용한다. 현재 API 기본 모델은 LSTM이다.',
            f'MLflow native TensorFlow LSTM 버전 등록·재로딩 확인: {registry_count}개. replay/candidate 별칭으로 구분. Production 승격 없음.',
            '최신 GitHub API 실제 모델 테스트: github_api_integration.json. 단건·배치·헬스·스케일러 호환 확인. 임시 가중치에서 1회 업데이트 가능 확인.',
            '현재 API는 plant_id가 없고 발전량 상한이 1320kWh이므로 큰 발전소의 HTTP 호출에는 별도 다개소 계약이 필요하다. 모델 파일 자체와 predict_one 인터페이스는 개소별로 준비했다.',
            'AIOps 판정기·자동 재학습·승격·캐시 교체·프론트 실시간 차트는 이번 모델 생성만으로 연결되지 않는다.',
            '예보 발표 시각의 운영 마감 검증은 미완료. 지역 대표 좌표를 공유하며 현장별 정밀 기상이 아니다.','', '제외 항목:']
    lines += [f'{p["plant_id"]} {p["name"]}: {p["reason"]}' for p in screening['excluded']]
    if args.partial:lines.insert(0,'진행 중 중간 결과')
    (out/f'report{suffix}.txt').write_text('\n'.join(lines),encoding='utf-8')
    print(json.dumps(output,ensure_ascii=False))


if __name__=='__main__':main()
