# T6 다시 계산(2): (가) 17시까지의 누적값으로 D-1 하루 합계를 추정할 때의 오차,
# (나) 단순 예측의 "실제 합계 대비 오차율"이 조사마다 다른 이유(평가 기간), (다) 20MW 묶음 기준 정산금 상한의 추정.
# 실행: PYTHONDONTWRITEBYTECODE=1 /Users/psm/workspace/skala-aiops/mlflow/.venv/bin/python T6_recalc2.py > out_recalc2.txt
import json
import numpy as np
import pandas as pd

SRC = '(작업 폴더)/solar/data_15043409.csv'
OUT = '(작업 폴더)/merged/T6-scheme/out_recalc2.json'
df = pd.read_csv(SRC, encoding='cp949'); df['d'] = pd.to_datetime(df['년월일']); df = df.sort_values('d').reset_index(drop=True)
A = df[[str(i) for i in range(1, 25)]].to_numpy(dtype=float); tot = A.sum(axis=1); dates = pd.DatetimeIndex(df['d']); mon = dates.month.to_numpy()
res = {}

print('== (가) D-1 17시(또는 14시)까지의 누적 발전량으로 D-1 하루 합계를 추정할 때의 오차')
print('   보정 비율(그 달의 "17시까지 누적 ÷ 하루 합계", 발전량 가중)은 평가 구간 이전 자료로만 구했다. 계량값을 그 시각에 바로 받는다는 가정이다.')
for s, e in (('2023-05-31', '2025-12-31'), ('2023-07-17', '2026-02-28')):
    tr = np.asarray(dates < s) & (tot >= 1.0); te = np.asarray((dates >= s) & (dates <= e))
    row = {}
    for h in (14, 17):
        ratio = np.array([A[tr & (mon == m), :h].sum() / A[tr & (mon == m)].sum() for m in range(1, 13)])
        est = A[:, :h].sum(axis=1) / ratio[mon - 1]
        err = est[te] - tot[te]
        raw = A[te, :h].sum(axis=1) - tot[te]
        row[str(h)] = {'rmse_scaled': float(np.sqrt(np.mean(err ** 2))), 'mae_scaled': float(np.mean(np.abs(err))),
                       'wape_scaled_pct': float(np.abs(err).sum() / tot[te].sum() * 100),
                       'rmse_raw': float(np.sqrt(np.mean(raw ** 2))), 'bias_raw': float(raw.mean())}
        print(f'   평가 {s}~{e} ({int(te.sum())}일, 하루 평균 {tot[te].mean():.1f}kWh) | {h}시 기준: 보정 뒤 RMSE {row[str(h)]["rmse_scaled"]:.2f}kWh, MAE {row[str(h)]["mae_scaled"]:.2f}kWh, 실제 합계 대비 {row[str(h)]["wape_scaled_pct"]:.2f}%'
              f' | 보정 없이 누적값을 그대로 쓰면 RMSE {row[str(h)]["rmse_raw"]:.2f}kWh, 평균 {row[str(h)]["bias_raw"]:+.2f}kWh')
    res[f'partial_{s}_{e}'] = row

print('\n== (나) 단순 예측의 실제 합계 대비 오차율(절대오차 합 ÷ 실제값 합)을 평가 기간별로')
def lag(a, b):
    out = np.full(len(tot), np.nan)
    for T in range(a, len(tot)):
        out[T] = tot[T - a:T - b + 1].mean()
    return out
P = {'어제 값': lag(1, 1), '7일 평균': lag(7, 1), '20일 평균': lag(20, 1)}
res['wape_by_period'] = {}
for name, (s, e) in {'전체(2013-01-21~2026-02-28)': ('2013-01-21', '2026-02-28'), '2016~2025(ASOS 걸어가기 범위)': ('2016-01-01', '2025-12-31'),
                     'ASOS 분할 A 평가(2023-05-31~2025-12-31)': ('2023-05-31', '2025-12-31'), '사전 조사 D2 평가(2023-07-17~2026-02-28)': ('2023-07-17', '2026-02-28')}.items():
    k = np.asarray((dates >= s) & (dates <= e))
    row = {}
    for pn, p in P.items():
        kk = k & ~np.isnan(p); err = p[kk] - tot[kk]
        row[pn] = {'wape_pct': float(np.abs(err).sum() / tot[kk].sum() * 100), 'rmse': float(np.sqrt(np.mean(err ** 2))), 'n': int(kk.sum())}
    print(f'   {name}: ' + ' | '.join(f'{pn} {v["wape_pct"]:.2f}% (RMSE {v["rmse"]:.2f}, {v["n"]}일)' for pn, v in row.items()))
    res['wape_by_period'][name] = row

print('\n== (다) 20MW 묶음 기준 예측제도 정산금 규모의 추정(가정: 묶음 전체가 하동과 같은 이용률, 용량 55kW 기준)')
cap = 55.0
yr = pd.Series(np.where(A >= 0.1 * cap, A, 0).sum(axis=1), index=dates).groupby(dates.year).sum()
cnt = pd.Series(tot, index=dates).groupby(dates.year).count(); fy = [y for y in cnt.index if cnt[y] >= 360]
m = float(yr[fy].mean()); per_kw = m / cap
print(f'   하동: 이용률 10% 이상 시간대 발전량 연평균 {m:,.0f}kWh (완전한 해 {fy[0]}~{fy[-1]}, 해별 최소 {yr[fy].min():,.0f} / 최대 {yr[fy].max():,.0f}) = 용량 1kW당 {per_kw:,.0f}kWh')
for mw in (20.0,):
    kwh = per_kw * mw * 1000
    print(f'   {mw:.0f}MW 묶음: 연 {kwh/1e6:,.2f}GWh. 전부 4원이면 연 {kwh*4/1e8:,.2f}억 원, kWh당 1원 차이는 연 {kwh/1e4:,.0f}만 원')
    res['agg20'] = {'per_kw_kwh': per_kw, 'kwh': kwh, 'krw_at_4': kwh * 4, 'krw_per_1won': kwh}
print(f'   하동 한 곳: kWh당 1원 차이는 연 {m:,.0f}원')
print('   참고(업체 발표, 검증 안 됨): 해줌 2025-07-30 글의 "1MW 기준 연 약 330만 원"은 1,000kW × 3.6시간 × 365일 = 1,314,000kWh 로 나누면 kWh당', round(3300000 / 1314000, 2), '원에 해당한다.')
res['hadong_elig_kwh'] = {'mean': m, 'min': float(yr[fy].min()), 'max': float(yr[fy].max())}
json.dump(res, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
