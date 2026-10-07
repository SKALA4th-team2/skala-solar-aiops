# (6) 구성원 한 곳의 저하를 놓쳤을 때: 하동 5곳 집합과 하수처리장 단독에서 '따라감' 대 '고정' (저하 폭 0.915, 0.91, 0.86, 0.5)
# (7) 2021년 하락의 날짜와 크기: 이웃 대비 비율(사전 조사 방식)과 성능 지표(ASOS 방식)를 나란히 다시 계산
# (8) 정지일 목록: 보완 조사 4 규칙(이웃 대비)과 ASOS 묶음의 stop_day / pi_outage 대조
# (9) 연도별 수준: 저하율 문헌값과 견줄 하동 자료의 지수
import numpy as np, pandas as pd
from t7_lib import *

hdr, idx, H, tot = load_raw()
D = {pk: load_pkl(pk)[1] for pk in HADONG}
cf = pd.DataFrame({p: D[p].sum(axis=1) / CAP[p] for p in HADONG}, index=idx)
STOP = {}; F = {}; V = {}
for p in HADONG:
    STOP[p], _ = stop_mask(cf, p, HADONG)
    F[p], V[p] = forecasts(D[p], STOP[p])
days = np.asarray((idx >= '2023-10-01') & (idx <= '2026-02-28'))
share5 = {p: CAP[p] / sum(CAP.values()) for p in HADONG}

def run(members, p, k, kind):
    Hov = dict(D); Hov[p] = D[p] * k
    F0 = {q: F[q][kind] for q in members}
    Fa = dict(F0); Fa[p] = F0[p] * k
    e1, A1, el1, b1 = agg(Hov, Fa, V, CAP, members, days); ad = summarize(e1, A1, el1, b1)
    e2, A2, el2, b2 = agg(Hov, F0, V, CAP, members, days); st = summarize(e2, A2, el2, b2)
    return ad, st

print('== 6a. 주입 실험, 하동 5곳 집합 [2023-10~2026-02, 현행 4·6% 계단을 전 기간에 적용]. 차이 = 고정 - 따라감')
print('    ORA 는 대상일의 실제 하루 합계를 쓴 참고 계산(예측 시점에 받을 수 없는 값)')
for p in ('15043409', '15043408', '15043404'):
    for k in (0.915, 0.86, 0.5):
        s = '  %s(비중 %.1f%%) x%.3f [비중x저하율 %.1f%%]:' % (NAMES[p], share5[p] * 100, k, share5[p] * (1 - k) * 100)
        for kind in ('PERS', 'ORA'):
            ad, st = run(HADONG, p, k, kind)
            s += ' %s 오차율 %+.2f%%p, 단가 %+.1f%% |' % (kind, st['err'] - ad['err'], (st['unit'] / ad['unit'] - 1) * 100)
        print(s)
print('\n== 6b. 같은 저하를 하수처리장 단독으로 볼 때 (따라감 -> 고정)')
for k in (0.915, 0.91, 0.86, 0.5):
    for kind in ('PERS', 'ORA'):
        ad, st = run(['15043409'], '15043409', k, kind)
        print('  x%.3f %s: 오차율 %.2f%% -> %.2f%% (%+.2f%%p), 편향 %+.2f -> %+.2f%%p, 단가 %.3f -> %.3f원 (%+.1f%%)' % (k, kind, ad['err'], st['err'], st['err'] - ad['err'], ad['bias'], st['bias'], ad['unit'], st['unit'], (st['unit'] / ad['unit'] - 1) * 100))
# 집합 오차율의 달별 흔들림
err, A, elig, bias = agg(D, {q: F[q]['PERS'] for q in HADONG}, V, CAP, HADONG, days)
mon = idx.to_period('M')
ms = [err[np.asarray(mon == m)][elig[np.asarray(mon == m)]].mean() for m in sorted(set(mon[days]))]
print('  하동 5곳 PERS 월평균 오차율의 달별 표준편차 %.2f%%p (29개월, %.2f~%.2f%%)' % (np.std(ms, ddof=1), min(ms), max(ms)))

# ---------- 7. 2021년 하락
print('\n== 7a. 이웃(보건소·변전소 평균) 대비 하루 이용시간 비율')
nb = cf[['15043406', '15043405']].mean(axis=1)
okn = (~STOP['15043409']) & (~STOP['15043406']) & (~STOP['15043405']) & (nb.values >= 3.0)   # 이웃 이용시간 3시간 이상(맑은 편인 날)
r = (cf['15043409'] / nb).where(okn)
for d in pd.date_range('2021-05-10', '2021-05-24'):
    print('   %s 하수처리장 %.2fh 이웃 %.2fh 비율 %s' % (d.date(), cf['15043409'][d], nb[d], ('%.3f' % r[d]) if not np.isnan(r[d]) else '(흐린 날 또는 정지, 재지 않음)'))
def med(a, b): return r[a:b].median(), int(r[a:b].notna().sum())
def sumr(a, b):
    m = okn & np.asarray((idx >= a) & (idx <= b)); return cf['15043409'][m].sum() / nb[m].sum()
pre2 = med('2019-05-18', '2021-05-14'); post1 = med('2021-05-18', '2022-05-17'); post6w = med('2021-05-18', '2021-06-28')
pre1 = med('2020-05-18', '2021-05-14')
print('  비율 중앙값: 직전 2년 %.3f(%d일), 직전 1년 %.3f(%d일), 직후 1년 %.3f(%d일), 직후 6주 %.3f(%d일)' % (pre2 + pre1 + post1 + post6w))
print('  직후 1년 / 직전 2년 = %+.1f%%, 직후 1년 / 직전 1년 = %+.1f%%, 직후 6주 / 직전 2년 = %+.1f%%' % ((post1[0] / pre2[0] - 1) * 100, (post1[0] / pre1[0] - 1) * 100, (post6w[0] / pre2[0] - 1) * 100))
print('  합계 비율: 직후 1년 / 직전 2년 = %+.1f%%, 직후 1년 / 직전 1년 = %+.1f%%' % ((sumr('2021-05-18', '2022-05-17') / sumr('2019-05-18', '2021-05-14') - 1) * 100, (sumr('2021-05-18', '2022-05-17') / sumr('2020-05-18', '2021-05-14') - 1) * 100))
# 같은 달 대비 (2016~2019 평균)
rm = r.groupby([idx.year, idx.month]).median()
print('  2016~2019 같은 달 중앙값 대비 달별 수준(2021-05 하순 이후 12개월):')
out = []
for (y, m) in [(2021, 6), (2021, 7), (2021, 8), (2021, 9), (2021, 10), (2021, 11), (2021, 12), (2022, 1), (2022, 2), (2022, 3), (2022, 4), (2022, 5)]:
    base = np.mean([rm[(yy, m)] for yy in (2016, 2017, 2018, 2019)]); base2 = np.mean([rm[(yy, m)] for yy in (y - 2, y - 1)]) if (y, m) >= (2022, 6) else np.mean([rm[(yy, m)] for yy in ((2019, 2020) if (y == 2021) else (2020, 2021))])
    out.append((y, m, (rm[(y, m)] / base - 1) * 100))
print('   ' + ', '.join('%d-%02d %+.1f%%' % o for o in out))
print('   최소 %+.1f%%, 최대 %+.1f%%, 12개월 평균 %+.1f%%' % (min(o[2] for o in out), max(o[2] for o in out), np.mean([o[2] for o in out])))

print('\n== 7b. ASOS 묶음의 성능 지표(실제/기대)로 본 같은 계단 (hadong_daily_full.csv, 사후 점검값)')
A = pd.read_csv(os.path.join(S, 'asos', 'hadong_daily_full.csv'), parse_dates=['date']).set_index('date')
v = A[A.pi_valid == 1]
def pi(a, b):
    x = v.loc[a:b]; return x.gen_kwh.sum() / x.pi_expected_kwh.sum(), len(x)
p_pre1 = pi('2020-05-18', '2021-05-17'); p_post1 = pi('2021-05-18', '2022-05-17'); p_post6w = pi('2021-05-18', '2021-06-28'); p_pre6w = pi('2021-04-06', '2021-05-17')
p_pre2 = pi('2019-05-18', '2021-05-17')
print('  실제/기대 합계 비율: 직전 2년 %.3f, 직전 1년 %.3f(%d일), 직후 1년 %.3f(%d일), 직전 6주 %.3f, 직후 6주 %.3f' % (p_pre2[0], p_pre1[0], p_pre1[1], p_post1[0], p_post1[1], p_pre6w[0], p_post6w[0]))
print('  직후 1년 / 직전 1년 = %+.1f%%, 직후 1년 / 직전 2년 = %+.1f%%, 직후 6주 / 직전 6주 = %+.1f%%, 직후 6주 / 직전 1년 = %+.1f%%' % ((p_post1[0] / p_pre1[0] - 1) * 100, (p_post1[0] / p_pre2[0] - 1) * 100, (p_post6w[0] / p_pre6w[0] - 1) * 100, (p_post6w[0] / p_pre1[0] - 1) * 100))
print('  pi_21d: 2021-05-17 %.4f, 2021-06-27 %.4f' % (A.pi_21d['2021-05-17'], A.pi_21d['2021-06-27']))
# 2024 회복
p23 = pi('2023-03-28', '2024-03-27'); p24 = pi('2024-03-28', '2025-03-27')
print('  2024-03-28 전후 1년: %.3f -> %.3f (%+.1f%%)' % (p23[0], p24[0], (p24[0] / p23[0] - 1) * 100))

# ---------- 8. 정지일 목록 대조
print('\n== 8. 하수처리장 정지일 목록 대조')
g4 = set(idx[STOP['15043409']].strftime('%Y-%m-%d'))
asos_stop = set(A.index[A.stop_day == 1].strftime('%Y-%m-%d')); asos_out = set(A.index[A.pi_outage == 1].strftime('%Y-%m-%d'))
zero = set(idx[H.sum(axis=1) == 0].strftime('%Y-%m-%d'))
print('  합계 0 인 날 %d | 보완 4 규칙(이웃 대비 0.3배 미만 포함) %d일 | ASOS stop_day %d일 | ASOS pi_outage %d일' % (len(zero), len(g4), len(asos_stop), len(asos_out)))
print('  보완 4 에만 있음(stop_day 기준):', sorted(g4 - asos_stop))
print('  ASOS stop_day 에만 있음:', sorted(asos_stop - g4))
print('  보완 4 에만 있음(pi_outage 기준):', sorted(g4 - asos_out))
print('  ASOS pi_outage 에만 있음:', sorted(asos_out - g4))
for d in ('2015-05-06', '2024-03-22', '2018-06-13', '2024-07-12'):
    print('   %s: 발전량 %.1fkWh, 이웃 이용시간 %.2fh, 하수처리장 %.2fh, ASOS 기대 %.1fkWh, stop_day %d, pi_outage %d, pi_partial_suspect %d' % (d, H[idx == d].sum(), nb[d], cf['15043409'][d], A.pi_expected_kwh[d], A.stop_day[d], A.pi_outage[d], A.pi_partial_suspect[d]))
print('  평가 기간 2023-10~2026-02 안의 보완 4 정지일:', sorted(x for x in g4 if '2023-10-01' <= x <= '2026-02-28'))

# ---------- 9. 연도별 수준
print('\n== 9. 연도별 수준(문헌의 연 저하율과 견줄 값)')
# (가) 원자료만: 봄(3~5월) 하루 시간 최대값의 상위 10일 중앙값, 2013=100
hm = pd.Series(H.max(axis=1), index=idx)
ds = pd.Series(H.sum(axis=1), index=idx)
rows = []
for y in range(2013, 2026):
    sp = hm[(idx.year == y) & (idx.month >= 3) & (idx.month <= 5)]
    top = sp.nlargest(10).median()
    yr_p999 = np.quantile(H[(idx.year == y)].ravel(), 0.999)
    rows.append((y, top, yr_p999, ds[idx.year == y].sum()))
b = rows[0]
print('  연도 | 봄 시간 최대 상위 10일 중앙값(2013=100) | 연 시간값 99.9% 분위(2013=100) | 연 발전량(2013=100)')
for y, t, q, s in rows:
    print('   %d | %.1f (%.0f) | %.1f (%.0f) | %.0f (%.0f)' % (y, t, t / b[1] * 100, q, q / b[2] * 100, s, s / b[3] * 100))
# (나) 성능 지표 연 평균(ASOS), 2013~2014=1.0 기준
yy = v.groupby(v.index.year).apply(lambda x: x.gen_kwh.sum() / x.pi_expected_kwh.sum())
print('  ASOS 성능 지표의 연 합계 비율:', ', '.join('%d %.3f' % (y, x) for y, x in yy.items()))
# 변화가 없던 구간(2015-06 ~ 2021-04)의 기울기
seg = v.loc['2015-06-01':'2021-04-30']; segm = seg.groupby([seg.index.year]).apply(lambda x: x.gen_kwh.sum() / x.pi_expected_kwh.sum())
xs = np.array(segm.index, float); sl = np.polyfit(xs[1:-1], segm.values[1:-1], 1)   # 온전한 해 2016~2020
print('  성능 지표 2016~2020(온전한 5개 해) 선형 기울기: %+.2f%%p/년 (값 %s)' % (sl[0] * 100, ', '.join('%.3f' % x for x in segm.values[1:-1])))
# 원자료 봄 지수의 2013->2021, 2013->2025 연율
t = {y: tt for y, tt, _, _ in rows}
print('  봄 지수 연율: 2013->2020 %.2f%%/년, 2013->2021 %.2f%%/년, 2021->2022 %+.1f%%, 2013->2025 %.2f%%/년' % ((1 - (t[2020] / t[2013]) ** (1 / 7)) * 100, (1 - (t[2021] / t[2013]) ** (1 / 8)) * 100, (t[2022] / t[2021] - 1) * 100, (1 - (t[2025] / t[2013]) ** (1 / 12)) * 100))
# 이웃 대비가 아닌 절대 수준에서 계단을 빼면: 2021-05 계단(-8.5~-9%)을 제외한 나머지
tot_drop = 1 - t[2025] / t[2013]
for step in (0.085, 0.09):
    rest = 1 - (t[2025] / t[2013]) / (1 - step)
    print('  2013->2025 봄 지수 전체 변화 %.1f%% 가운데 2021-05 계단 %.1f%% 를 빼면 나머지 %.1f%% (12년, 연 %.2f%%)' % (-tot_drop * 100, -step * 100, -rest * 100, (1 - (1 - rest) ** (1 / 12)) * 100 if rest > 0 else 0))
