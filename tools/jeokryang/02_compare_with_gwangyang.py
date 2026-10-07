"""적량면 일사량을 광양 관측, 재분석 자료와 견줘 유효 일수, 빈 구간, 센서 수준의 변화를 본다.

실행 (저장소 루트에서):
    python tools/jeokryang/02_compare_with_gwangyang.py
"""
import numpy as np
import pandas as pd

from common import load_joined

a = load_joined()
print("적량 하루 일사량이 유효한 날:", int(a.jr_gsr.notna().sum()), "/", len(a), "| 광양이 유효한 날:", int(a.gy_gsr.notna().sum()))
y = a.groupby(a.index.year).agg(전체=("gen_kwh", "size"), 적량=("jr_gsr", "count"), 광양=("gy_gsr", "count"))
print("\n연도별 유효 일수:\n", y.T.to_string())

gap = a.jr_gsr.isna()
blk = (gap != gap.shift()).cumsum()
runs = [(g.index.min().date(), g.index.max().date(), len(g)) for _, g in a[gap].groupby(blk[gap]) if len(g) > 30]
print("\n30일 넘게 빈 구간:", runs)
print("\n해 뜨기 전 누적값이 0.05 를 넘는 날의 비율(연도별, %):", (a.predawn_mj > 0.05).groupby(a.index.year).mean().mul(100).round(1).to_dict())
print("19시 뒤에 0.1 넘게 더 쌓인 날의 비율(연도별, %):", (a.after_sunset_mj > 0.1).groupby(a.index.year).mean().mul(100).round(1).to_dict())

b = a.dropna(subset=["jr_gsr", "gy_gsr"])
print("\n두 곳 모두 유효한 날:", len(b))
print("적량 대 광양: 상관 %.3f | 차이 RMSE %.2f MJ/m2 | 합의 비(적량/광양) %.3f | 평균 적량 %.2f, 광양 %.2f"
      % (b.jr_gsr.corr(b.gy_gsr), np.sqrt(((b.jr_gsr - b.gy_gsr) ** 2).mean()), b.jr_gsr.sum() / b.gy_gsr.sum(), b.jr_gsr.mean(), b.gy_gsr.mean()))
rows = []
for yr, x in b.groupby(b.index.year):
    rows.append({"연도": yr, "일수": len(x), "상관": x.jr_gsr.corr(x.gy_gsr), "적량/광양": x.jr_gsr.sum() / x.gy_gsr.sum(),
                 "적량/재분석": x.jr_gsr.sum() / x.era.sum(), "광양/재분석": x.gy_gsr.sum() / x.era.sum()})
print("\n연도별 수준 비교:\n", pd.DataFrame(rows).set_index("연도").round(3).to_string())

ok = (a.stop_day == 0) & (a.pi_outage.fillna(0) == 0)
c = a[ok].dropna(subset=["jr_gsr", "gy_gsr"])
print("\n월별 적량/광양 일사량 비율 (그 달에 15일 이상 있을 때)")
for yr, x in c.groupby(c.index.year):
    m = [f"{g.jr_gsr.sum() / g.gy_gsr.sum():.2f}" for _, g in x.groupby(x.index.month) if len(g) >= 15]
    print(f"  {yr}: " + " ".join(m))

# 계단 찾기: 흐린 날은 비율이 흔들리므로 광양 일사량이 8 MJ/m2 를 넘는 날만 쓴다
r = (a.jr_gsr / a.gy_gsr).where(a.gy_gsr > 8)
print("\n센서 수준이 바뀐 날짜 (앞뒤 30일 비율 중앙값의 차이가 가장 큰 날)")
for name, lo, hi in [("2014년", "2014-06-15", "2014-09-30"), ("2015년", "2015-03-15", "2015-06-30"), ("2024년", "2024-01-05", "2024-03-20")]:
    best = None
    for t in pd.date_range(lo, hi):
        p = r[t - pd.Timedelta(days=30): t - pd.Timedelta(days=1)].dropna()
        q = r[t: t + pd.Timedelta(days=29)].dropna()
        if len(p) < 8 or len(q) < 8:
            continue
        s = q.median() - p.median()
        if best is None or abs(s) > abs(best[1]):
            best = (t, s, p.median(), q.median())
    print(f"  {name}: {best[0].date()} | 앞 30일 {best[2]:.3f} → 뒤 30일 {best[3]:.3f} ({(best[3] / best[2] - 1) * 100:+.0f}%)")
x = r["2024-01-25":"2024-02-16"].dropna().round(2)
print("  2024년 계단 앞뒤의 하루 비율:", " ".join(f"{d.strftime('%m-%d')}:{v}" for d, v in x.items()))
print("\n구간별 비율 (수준이 일정한지)")
for lo, hi in [("2013-01-01", "2014-07-15"), ("2014-09-01", "2015-04-15"), ("2022-01-01", "2024-01-31"), ("2024-03-01", "2025-12-31")]:
    x = r[lo:hi].dropna()
    m = x.resample("MS").median()
    print(f"  {lo} ~ {hi}: 중앙값 {x.median():.3f}, 월별 중앙값의 범위 {m.min():.2f} ~ {m.max():.2f}, 유효 {int(a.jr_gsr[lo:hi].notna().sum())}일 / {len(a[lo:hi])}일")
