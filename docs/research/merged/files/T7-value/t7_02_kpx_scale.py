# (4) 전력거래소 공개 오차율: 조사 6(30개월, 2024-06~2025-05 대 2025-06~2026-03)과 보완 조사 4(29개월, 2023-10~2025-05 대 2025-06~2026-02)의 평균을 사본에서 다시 계산
# (5) 금액 환산: 조사 6(5,125MW x 330만 원 x 5~18%)과 보완 조사 4(171MW x 231만 원 x 8.6%)를 같은 단위(MW당 연 금액)로 놓음
import re, glob, os, numpy as np
from t7_lib import S
Q6 = os.path.join(S, 'solar', 'q6')
vals = {}
for f in sorted(glob.glob(os.path.join(Q6, 'err_*.txt'))):
    t = open(f, encoding='utf-8', errors='replace').read()
    lines = t.splitlines()
    hd = next(l for l in lines if '구 분' in l)
    mons = re.findall(r"[`'’‘](\d{2})\.\s*(\d{1,2})\.", hd)
    # 첫 '평 균' / '최 하' / '최 상' 줄이 태양광 육지
    def first(tag):
        l = next(l for l in lines if tag in l)
        return [float(x) for x in re.findall(r'\d+\.\d+', l)]
    avg, lo, hi = first('평 균'), first('최 하'), first('최 상')
    for k, (yy, mm) in enumerate(mons):
        key = '20%s-%02d' % (yy, int(mm))
        v = (avg[k], lo[k], hi[k])
        if key in vals and vals[key] != v:
            print('!! 같은 달 값이 파일마다 다름', key, vals[key], v, os.path.basename(f))
        vals[key] = v
    print(os.path.basename(f), [('20%s-%02d' % (y, int(m))) for y, m in mons], avg)
ks = sorted(vals)
print('\n달 수', len(ks), ks[0], '~', ks[-1])
def mean(a, b, col=0):
    x = [vals[k][col] for k in ks if a <= k <= b]
    return np.mean(x), len(x), min(x), max(x)
for lab, a, b in (('조사 6: 30개월 2023-10~2026-03', '2023-10', '2026-03'), ('보완 4: 29개월 2023-10~2026-02', '2023-10', '2026-02'),
                  ('조사 6 변경 전 12개월 2024-06~2025-05', '2024-06', '2025-05'), ('조사 6 변경 뒤 10개월 2025-06~2026-03', '2025-06', '2026-03'),
                  ('보완 4 변경 전 20개월 2023-10~2025-05', '2023-10', '2025-05'), ('보완 4 변경 뒤 9개월 2025-06~2026-02', '2025-06', '2026-02')):
    m, n, lo, hi = mean(a, b)
    print(' %s: 평균의 평균 %.3f%% (%d개월, %.3f~%.3f)' % (lab, m, n, lo, hi))
m, n, lo, hi = mean('2023-10', '2026-03', 1); print(' 최하: 평균 %.3f, 범위 %.3f~%.3f' % (m, lo, hi))
m, n, lo, hi = mean('2023-10', '2026-03', 2); print(' 최상: 평균 %.3f, 범위 %.3f~%.3f' % (m, lo, hi))
m, n, lo, hi = mean('2023-10', '2026-02', 1); print(' 29개월 최하 평균 %.3f, ' % m, end='')
m, n, lo, hi = mean('2023-10', '2026-02', 2); print('최상 평균 %.3f' % m)
print(' 평균이 6%% 를 넘은 달: %s' % [k for k in ks if vals[k][0] > 6])
print(' 평균이 4%% 이하인 달 수: %d, 최하가 4%% 를 넘은 달: %s' % (sum(vals[k][0] <= 4 for k in ks), [k for k in ks if vals[k][1] > 4]))

print('\n== 5. 금액 환산을 같은 단위로')
kwh_per_mw_g4 = 887346 / 908.17 * 1000          # 보완 4: 육지 7곳 연 발전량 / 용량
print(' 보완 4 의 발전 패턴: MW당 연 %.0f kWh (하루 %.2f시간, 이용률 %.1f%%)' % (kwh_per_mw_g4, kwh_per_mw_g4 / 1000 / 365, kwh_per_mw_g4 / 8760 / 10))
elig_share = 0.947
for unit in (2.49, 2.53, 3.24):
    print('  단가 %.2f원(정산 대상 시간 기준) x 대상 비중 %.3f x MW당 발전량 = MW당 연 %.1f만 원' % (unit, elig_share, unit * elig_share * kwh_per_mw_g4 / 1e4))
mw = 2.49 * elig_share * kwh_per_mw_g4
print('  20MW %.0f만 원, 171MW %.2f억 원 (5,125/30 = %.1f MW)' % (mw * 20 / 1e4, mw * 170.8333 / 1e8, 5125 / 30))
for d in (0.07, 0.086, 0.09, 0.10, 0.15, 0.17, 0.194):
    print('   감소율 %.1f%% -> MW당 연 %.1f만 원, 171MW %.0f만 원' % (d * 100, mw * d / 1e4, mw * 170.8333 * d / 1e4))
print(' 조사 6 의 기준선: 해줌 예상 1MW 연 330만 원 = 3.6h x 365 x 1000 = %d kWh x %.2f원' % (3.6 * 365 * 1000, 3300000 / (3.6 * 365 * 1000)))
for d in (0.05, 0.12, 0.18):
    print('   감소율 %.0f%% -> MW당 연 %.1f만 원, 5,125MW %.1f억 원' % (d * 100, 330 * d, 330 * d * 5125 / 1e4))
print('  5,125MW x 330만 원 = %.0f억 원' % (5125 * 330 / 1e4))
print(' 두 기준선의 차이: 발전시간 3.6h 대 %.2fh 가 %.2f배, 단가 2.51 대 %.2f(전체 발전량 기준) ' % (kwh_per_mw_g4 / 365000, 3.6 / (kwh_per_mw_g4 / 365000), 2.49 * elig_share))
print(' 같은 발전시간(3.6h)과 대상 비중으로 맞추면 보완 4 단가의 MW당 금액: %.0f만 원' % (2.49 * elig_share * 1314000 / 1e4))
# 하동 한 곳
print(' 하수처리장 한 곳: 단독 PERS 연 약 11.05만 원 x (11.8~17.1%%) = %.1f~%.1f만 원 / 연 (현행 계단, 단독 정산 가정)' % (11.05 * 0.118, 11.05 * 0.171))
print(' 하수처리장이 171MW 집합에서 차지하는 용량 비중: %.3f%%, 20MW 집합에서: %.3f%%' % (55 / 171000 * 100, 55 / 20000 * 100))
