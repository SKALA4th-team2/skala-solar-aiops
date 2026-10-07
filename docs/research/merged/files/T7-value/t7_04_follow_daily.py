# (10) 과거 값만 쓰는 LSTM 이 수준 하락을 며칠 만에 따라가는가: ASOS 묶음 A4 의 가짜 변화 실험 원자료(out_08b_lstm_synthetic_raw.csv)를 다시 집계
#      (모델은 2013~2014 로 학습한 씨앗 42 하나. 'real' 은 대상일 날씨를 쓰지 않는 모델이고, A4 원 입력이라 날씨 열이 T-1 까지 들어가 있다)
# (11) 하루 단위 오차율(분모 55kW x 24h)과 제도식 시간대별 오차율이 같은 예측에서 얼마나 다른가
# (12) 2021-05 하락으로 잃은 발전량(kWh): 성능 지표 기준. 판매 단가는 자료에 없으므로 kWh 와 정산금 대비 비율만 계산
import os, numpy as np, pandas as pd
from t7_lib import *

raw = pd.read_csv(os.path.join(S, 'asos', 'a4', 'out_08b_lstm_synthetic_raw.csv'))
print('== 10. LSTM 의 수준 추종 (ASOS A4 08b 원자료 재집계)')
for v in ('real', 'oracle'):
    b = raw[(raw.variant == v) & (raw['drop'] == 0.0)].set_index(['start', 'day'])
    for x in (0.085, 0.3):
        d = raw[(raw.variant == v) & (raw['drop'] == x)].set_index(['start', 'day'])
        ratio = (d.pred / b.pred).rename('r').reset_index()
        g = ratio.groupby('day').r.mean()
        # 따라간 정도 = (1 - 예측 비율) / 낙폭
        fol = (1 - g) / x
        print('  [%s] 낙폭 %.1f%%: 변화 뒤 날짜별 예측 수준(낙폭 없는 예측 대비)  1일 %.3f, 2일 %.3f, 3일 %.3f, 5일 %.3f, 7일 %.3f, 10일 %.3f, 14일 %.3f, 21일 %.3f, 28일 %.3f, 42일 %.3f'
              % (v, x * 100, g[0], g[1], g[2], g[4], g[6], g[9], g[13], g[20], g[27], g[41]))
        half = next((k + 1 for k in range(42) if fol[k] >= 0.5), None); p90 = next((k + 1 for k in range(42) if fol[k] >= 0.9), None)
        print('        낙폭의 절반을 따라간 날: %s일째, 90%% 를 따라간 날: %s일째, 22~42일 평균 추종 %.0f%%' % (half, p90, fol[21:42].mean() * 100))
        # 실제 대비 치우침(예측-실제)/실제, 유효일만
        dv = d[d.valid == 1]; bv = b[b.valid == 1]
        for lab, lo, hi in (('1~7일', 0, 6), ('8~21일', 7, 20), ('22~42일', 21, 41)):
            m = (dv.index.get_level_values('day') >= lo) & (dv.index.get_level_values('day') <= hi)
            m0 = (bv.index.get_level_values('day') >= lo) & (bv.index.get_level_values('day') <= hi)
            print('        %s: 예측 합/실제 합 - 1 = %+.1f%% (낙폭 없을 때 %+.1f%%)' % (lab, (dv.pred[m].sum() / dv.actual[m].sum() - 1) * 100, (bv.pred[m0].sum() / bv.actual[m0].sum() - 1) * 100))

print('\n== 11. 하루 단위 오차율(분모 55kW x 24h)과 제도식(시간대별, 이용률 10% 이상, 분모 55kW) 비교, 하수처리장, 2023-10~2026-02')
hdr, idx, H, tot = load_raw()
ds = H.sum(axis=1); days = np.asarray((idx >= '2023-10-01') & (idx <= '2026-02-28'))
pers_d = np.r_[np.nan, ds[:-1]]
ma20 = pd.Series(ds).rolling(20).mean().shift(1).values
ma7 = pd.Series(ds).rolling(7).mean().shift(1).values
tr_mean = ds[np.asarray(idx < '2023-05-30')].mean()
for nm, f in (('전날 값', pers_d), ('7일 평균', ma7), ('20일 평균', ma20), ('학습 구간(2023-05-29 까지) 평균 고정값 %.1fkWh' % tr_mean, np.full(len(ds), tr_mean))):
    e = np.abs(f - ds)[days]
    print('  %s: 하루 MAE %.1fkWh, RMSE %.1fkWh | 분모 55x24 오차율 %.2f%%, 분모 50x24 오차율 %.2f%% | 실제 합계 대비 %.1f%%' % (nm, e.mean(), np.sqrt((e ** 2).mean()), e.mean() / 1320 * 100, e.mean() / 1200 * 100, e.sum() / ds[days].sum() * 100))
# 제도식: 전날 같은 시간 값(정지일 처리 없음)
P = np.vstack([np.full(24, np.nan), H[:-1]]); el = (H >= 5.5) & days[:, None]
print('  제도식(전날 같은 시간 값): 평균 %.2f%% | 같은 예측의 하루 단위 오차율은 위 첫 줄' % (np.abs(P - H)[el].mean() / 55 * 100))
# 하루 합계를 완벽히 맞혀도 남는 시간대별 오차(직전 7일 시간 비중 사용) = 일 단위 모델의 제도식 오차율 하한
M7 = np.full_like(H, np.nan)
for t in range(7, len(H)): M7[t] = H[t - 7:t].mean(axis=0)
ora = M7 / M7.sum(axis=1, keepdims=True) * ds[:, None]
print('  하루 합계를 완벽히 맞히고 시간 비중만 직전 7일 평균을 쓴 경우(예측 시점에 받을 수 없는 값 사용): 제도식 %.2f%%, 하루 단위 오차율 0%%' % (np.abs(ora - H)[el].mean() / 55 * 100))

print('\n== 12. 2021-05 하락으로 줄어든 발전량 (성능 지표 기준, 사후 계산)')
A = pd.read_csv(os.path.join(S, 'asos', 'hadong_daily_full.csv'), parse_dates=['date']).set_index('date')
v = A[A.pi_valid == 1]
pre = v.loc['2020-05-18':'2021-05-17']; lvl0 = pre.gen_kwh.sum() / pre.pi_expected_kwh.sum()
for a, b in (('2021-05-18', '2022-05-17'), ('2021-05-18', '2024-03-27'), ('2024-03-28', '2025-12-31')):
    x = v.loc[a:b]; lost = (x.pi_expected_kwh * lvl0 - x.gen_kwh).sum(); n = len(x); allx = A.loc[a:b]
    print('  %s ~ %s: 유효 %d일(전체 %d일), 실제 %.0fkWh, 직전 1년 수준(%.3f)이었다면 %.0fkWh, 차이 %.0fkWh (%.1f%%), 연 환산 %.0fkWh'
          % (a, b, n, len(allx), x.gen_kwh.sum(), lvl0, (x.pi_expected_kwh * lvl0).sum(), lost, lost / (x.pi_expected_kwh * lvl0).sum() * 100, lost / n * 365))
print('  비교: 하수처리장 단독 예측 정산금(전날 값 예측, 현행 계단 가정) 연 약 11.05만 원, 상한 약 27.3만 원 = 발전량 1kWh 당 최대 4원')
print('  동서발전 2021-10 발표: 정산금 3.5원/kWh 가 전력판매 수익의 3%% 이상 -> 판매 수익은 kWh 당 %.0f원 이하(역산)' % (3.5 / 0.03))
for price in (50, 100, 117):
    print('   판매 수익이 kWh 당 %d원이라고 두면(가정): 연 6,000kWh 손실 = %.0f만 원, 정산금 상한(27.3만 원)의 %.1f배' % (price, 6000 * price / 1e4, 6000 * price / 273000))
print('  판매 단가와 무관한 비교: 발전량 8.5%% 손실 대 정산금 상한(4원)이 판매 수익에서 차지하는 비율 3%% 이상(2021년 발표 기준)')
