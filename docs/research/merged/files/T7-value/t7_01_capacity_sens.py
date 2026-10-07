# (1) 설비 용량 50kW 대 55kW, (2) 발전소 한 곳의 오차율·정산금·1%p 민감도를 조사 6 방식과 보완 조사 4 방식으로 각각 다시 계산,
# (3) 하동 5곳 집합의 민감도(현행 4·6% 계단, 옛 6·8% 계단). 부산 2곳은 디스크에 사본이 없어 7곳 값은 다시 계산하지 않는다.
import numpy as np, pandas as pd
from t7_lib import *

hdr, idx, H, tot = load_raw()
print('== 0. 원본:', len(idx), '행', idx[0].date(), '~', idx[-1].date(), '| 날짜 중복', int(idx.duplicated().sum()))
yr = idx.year.values
print('\n== 1. 설비 용량')
hmax = H.max(); i, j = np.unravel_index(H.argmax(), H.shape)
print(' 시간값 최대 %.3f (%s, %d열)' % (hmax, idx[i].date(), j + 1))
print(' 50 을 넘는 시간 수 %d, 55 를 넘는 시간 수 %d' % ((H > 50).sum(), (H > 55).sum()))
ann = pd.Series(H.sum(axis=1), index=idx).groupby(yr).sum()
full = ann.loc[2013:2025]
print(' 연 발전량 2013~2025 평균 %.0f, 최소 %.0f(%d), 최대 %.0f(%d), 최근 3년(2023~2025) 평균 %.0f kWh' % (full.mean(), full.min(), full.idxmin(), full.max(), full.idxmax(), full.loc[2023:2025].mean()))
for cap in (50.0, 55.0):
    m13 = (yr >= 2013) & (yr <= 2025)
    el = H[m13][H[m13] >= 0.1 * cap].sum() / H[m13].sum() * 100
    print('  용량 %.0fkW: 2013~2025 평균 하루 발전시간 %.2fh(이용률 %.1f%%), 최대값/용량 %.1f%%, 이용률 10%% 이상 시간대의 발전량 비중 %.1f%%' % (cap, full.mean() / cap / 365, full.mean() / cap / 8760 * 100, hmax / cap * 100, el))

# ---- 조사 6 방식: 정지일을 건너뛰지 않음, 평가 기간 2023~2025, 전날 값/직전 7일 평균/하루 합계 적중
def r6_method(cap, a, b, label):
    T = len(idx)
    pers = np.full((T, 24), np.nan); pers[1:] = H[:-1]
    ma7 = np.full((T, 24), np.nan)
    for t in range(7, T): ma7[t] = H[t - 7:t].mean(axis=0)
    s = ma7.sum(axis=1, keepdims=True); ora = np.where(s > 0, ma7 / np.where(s > 0, s, 1) * H.sum(axis=1, keepdims=True), 0.0)
    days = np.asarray((idx >= a) & (idx <= b)); days[:30] = False
    ny = days.sum() / 365.25
    out = {}
    for k, F in (('PERS', pers), ('MA7', ma7), ('ORA', ora)):
        err = np.abs(F - H) / cap * 100
        elig = (H >= 0.1 * cap) & days[:, None]
        b0, s1, s2 = sens(err, H, elig)
        bo, o1, o2 = sens(err, H, elig, t1=6.0, t2=8.0)
        out[k] = (b0, s1, s2, bo, o1, o2)
        print('  [%s] %s cap=%.0f: 대상 시간 평균 오차율 %.2f%%(중앙값 %.2f), 단가 %.3f원, 연 정산금 %.0f원, 상한 %.0f원 | +1%%p %+.1f%%, +2%%p %+.1f%% | 옛 계단 단가 %.3f, +1%%p %+.1f%%, +2%%p %+.1f%%'
              % (label, k, cap, b0['err'], b0['med'], b0['unit'], b0['won'] / ny, b0['kwh'] * 4 / ny, s1, s2, bo['unit'], o1, o2))
    return out

print('\n== 2a. 조사 6 방식(정지일 처리 없음), 2023-01-01~2025-12-31  [ORA 는 대상일 실제 하루 합계를 쓴 참고 계산]')
for cap in (50.0, 55.0):
    r6_method(cap, '2023-01-01', '2025-12-31', '조사6식 2023~2025')
print('\n== 2b. 같은 방식으로 기간만 2023-10-01~2026-02-28')
r6_method(55.0, '2023-10-01', '2026-02-28', '조사6식 23-10~26-02')

# ---- 보완 조사 4 방식: 하동 5곳, 정지일 건너뜀
D = {}
for pk in HADONG:
    ix, Hh, nm = load_pkl(pk); assert (ix == idx).all(), pk
    D[pk] = Hh
print('\n== 캐시 대조: 하수처리장 캐시와 원본 CSV 시간값 최대 차이 %.6f' % np.abs(D['15043409'] - H).max())
cf = pd.DataFrame({p: D[p].sum(axis=1) / CAP[p] for p in HADONG}, index=idx)
STOP = {}; F = {}; V = {}
for p in HADONG:
    STOP[p], _ = stop_mask(cf, p, HADONG)
    F[p], V[p] = forecasts(D[p], STOP[p])
print(' 정지일 수(13년 전체, 합계 0 / 정지 판정): ' + ', '.join('%s %d/%d' % (NAMES[p], int((cf[p] == 0).sum()), int(STOP[p].sum())) for p in HADONG))
np.save('stop_sewage_gap4rule.npy', STOP['15043409'])
pd.Series(STOP['15043409'], index=idx).loc[lambda s: s].index.strftime('%Y-%m-%d').to_series().to_csv('stop_sewage_gap4rule.csv', index=False, header=['date'])

def g4_method(members, a, b, label):
    days = np.asarray((idx >= a) & (idx <= b))
    ny = days.sum() / 365.25
    res = {}
    for k in ('PERS', 'MA7', 'ORA'):
        err, A, elig, bias = agg(D, {p: F[p][k] for p in members}, V, CAP, members, days)
        b0, s1, s2 = sens(err, A, elig)
        bo, o1, o2 = sens(err, A, elig, t1=6.0, t2=8.0)
        bb = summarize(err, A, elig, bias)
        res[k] = (b0, s1, s2, bo, o1, o2)
        print('  [%s] %s: 평균 오차율 %.2f%%(중앙값 %.2f, 편향 %+.2f%%p), 단가 %.3f원, 연 정산금 %.0f원, 상한 %.0f원 | 현행 +1%%p %+.1f%%, +2%%p %+.1f%% | 옛 계단 단가 %.3f, +1%%p %+.1f%%, +2%%p %+.1f%% | 옛->현행 %+.1f%%'
              % (label, k, b0['err'], b0['med'], bb['bias'], b0['unit'], b0['won'] / ny, b0['kwh'] * 4 / ny, s1, s2, bo['unit'], o1, o2, (b0['unit'] / bo['unit'] - 1) * 100))
    return res

print('\n== 3a. 보완 조사 4 방식(정지일 건너뜀, 용량 55kW), 하수처리장 단독  [ORA 는 대상일 실제 하루 합계를 쓴 참고 계산]')
g4_method(['15043409'], '2023-10-01', '2026-02-28', '단독 23-10~26-02')
g4_method(['15043409'], '2023-01-01', '2025-12-31', '단독 2023~2025')
print('\n== 3b. 하동 5곳 집합(606.17kW)')
r5 = g4_method(HADONG, '2023-10-01', '2026-02-28', '하동5 23-10~26-02')
g4_method(HADONG, '2023-01-01', '2025-12-31', '하동5 2023~2025')
g4_method(HADONG, '2025-06-01', '2026-02-28', '하동5 현행 계단 시행 뒤 25-06~26-02')

# 수준 맞춤: 하동 5곳 PERS/MA7 의 오차를 같은 비율로 줄여 평균을 전력거래소 평균 수준에 맞춤
print('\n== 3c. 수준 맞춤(추정): 하동 5곳 오차를 같은 비율로 줄여 평균을 목표값에 맞춘 가상 예측 [2023-10~2026-02]')
days = np.asarray((idx >= '2023-10-01') & (idx <= '2026-02-28'))
for k in ('PERS', 'MA7', 'ORA'):
    err, A, elig, bias = agg(D, {p: F[p][k] for p in HADONG}, V, CAP, HADONG, days)
    m0 = err[elig].mean()
    for tg in (2.95, 4.0, 5.53, 5.71):
        sc = tg / m0
        b0, s1, s2 = sens(err, A, elig, scale=sc)
        bo, o1, o2 = sens(err, A, elig, scale=sc, t1=6.0, t2=8.0)
        # 곱셈식 악화: 평균이 1%p, 2%p 오르도록 전체를 같은 비율로 키움
        m1 = summarize(err, A, elig, scale=(tg + 1) / m0)['unit'] / b0['unit'] - 1
        m2 = summarize(err, A, elig, scale=(tg + 2) / m0)['unit'] / b0['unit'] - 1
        print('  [%s 모양] 목표 평균 %.2f%%: 단가 %.3f원 | 더하기식 +1%%p %+.1f%%, +2%%p %+.1f%% | 곱하기식 +1%%p %+.1f%%, +2%%p %+.1f%% | 옛 계단 +1%%p %+.1f%%, +2%%p %+.1f%%' % (k, tg, b0['unit'], s1, s2, m1 * 100, m2 * 100, o1, o2))

# 단독과 집합의 민감도 나란히
print('\n== 3d. 요약: 묶으면 민감도가 줄어드는가 (현행 계단, 2023-10~2026-02)')
for nm, mem in (('하수처리장 단독', ['15043409']), ('공설운동장 단독', ['15043404']), ('하동 5곳', HADONG)):
    for k in ('PERS', 'MA7'):
        err, A, elig, bias = agg(D, {p: F[p][k] for p in mem}, V, CAP, mem, days)
        b0, s1, s2 = sens(err, A, elig)
        print('  %s %s: 오차율 %.2f%%, 단가 %.2f원, +1%%p %+.1f%%, +2%%p %+.1f%%' % (nm, k, b0['err'], b0['unit'], s1, s2))

# 상쇄 비율: 집합 오차 / 구성원 절대오차 합 (하동 5곳, 5곳 모두 정상인 날)
print('\n== 3e. 하동 5곳 상쇄 비율(집합 절대오차 합 / 구성원 절대오차 합), 5곳 모두 정상인 날, 2023-10~2026-02')
allok = np.all([V[p] for p in HADONG], axis=0) & days
for k in ('PERS', 'MA7', 'ORA'):
    Fsum = sum(np.nan_to_num(F[p][k]) for p in HADONG); Asum = sum(D[p] for p in HADONG); C = sum(CAP.values())
    elig = (Asum >= 0.1 * C) & allok[:, None]
    num = np.abs(Fsum - Asum)[elig].sum(); den = sum(np.abs(np.nan_to_num(F[p][k]) - D[p]) for p in HADONG)[elig].sum()
    e_agg = (np.abs(Fsum - Asum) / C * 100)[elig].mean()
    # 단독 오차율(같은 날)
    es = (np.abs(np.nan_to_num(F['15043409'][k]) - D['15043409']) / 55 * 100)[(D['15043409'] >= 5.5) & allok[:, None]].mean()
    print('  %s: 정상일 %d일, 집합 오차율 %.2f%%, 하수처리장 단독 %.2f%%, 상쇄 비율 %.3f (감소 %.1f%%)' % (k, allok.sum(), e_agg, es, num / den, (1 - num / den) * 100))
