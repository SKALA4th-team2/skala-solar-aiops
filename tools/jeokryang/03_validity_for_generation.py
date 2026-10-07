"""적량면 일사량이 하동 발전량을 얼마나 설명하는지 광양 관측과 같은 날들에서 견준다.

실행 (저장소 루트에서):
    python tools/jeokryang/03_validity_for_generation.py
"""
import warnings

import numpy as np

from common import bias_pct, load_joined, rmse

# macOS 의 numpy 가 행렬 곱에서 내는 경고를 끈다. 결과 값은 모두 유한하고 경고가 없을 때와 같다.
warnings.filterwarnings("ignore", category=RuntimeWarning)

a = load_joined()
ok = (a.stop_day == 0) & (a.pi_outage.fillna(0) == 0)          # 정지일과 정지로 보이는 날은 뺀다
b = a[ok].dropna(subset=["jr_gsr", "gy_gsr", "gen_kwh"])
print("비교에 쓴 날(정지일 제외, 두 곳 모두 값이 있는 날):", len(b))
print("\n같은 날 발전량과의 상관")
print(f"  전체: 적량 {b.gen_kwh.corr(b.jr_gsr):.3f} | 광양 {b.gen_kwh.corr(b.gy_gsr):.3f} | 재분석 {b.gen_kwh.corr(b.era):.3f}")
for yr, x in b.groupby(b.index.year):
    print(f"  {yr} ({len(x)}일): 적량 {x.gen_kwh.corr(x.jr_gsr):.3f} | 광양 {x.gen_kwh.corr(x.gy_gsr):.3f} | 재분석 {x.gen_kwh.corr(x.era):.3f}")


def design(x, cols):
    """발전량 = 일사량 x (상수 + 계절 항) + 상수. 계절 항은 연중 날짜의 cos, sin 이다."""
    w = 2 * np.pi * x.index.dayofyear.values / 365.25
    parts = []
    for c in cols:
        g = x[c].values
        parts += [g, g * np.cos(w), g * np.sin(w)]
    return np.column_stack(parts + [np.ones(len(x))])


def fit_apply(tr, te, cols):
    coef, *_ = np.linalg.lstsq(design(tr, cols), tr.gen_kwh.values, rcond=None)
    p = design(te, cols) @ coef
    return rmse(te.gen_kwh.values, p), bias_pct(te.gen_kwh.values, p)


print("\n앞 구간으로 맞춘 식을 뒤 구간에 적용 (RMSE kWh / 합계 치우침 %)")
cases = [("학습 2013~2017, 평가 2022~2025", b[b.index.year <= 2017], b[(b.index.year >= 2022) & (b.index.year <= 2025)]),
         ("학습 2022~2023, 평가 2024~2025", b[b.index.year.isin([2022, 2023])], b[b.index.year.isin([2024, 2025])]),
         ("학습 2024, 평가 2025", b[b.index.year == 2024], b[b.index.year == 2025])]
for name, tr, te in cases:
    res = {k: fit_apply(tr, te, c) for k, c in [("적량", ["jr_gsr"]), ("광양", ["gy_gsr"]), ("둘 다", ["jr_gsr", "gy_gsr"])]}
    print(f"  {name} (학습 {len(tr)}일, 평가 {len(te)}일, 평가 구간 하루 평균 {te.gen_kwh.mean():.0f}kWh): "
          + " | ".join(f"{k} {v[0]:.1f} / {v[1]:+.1f}%" for k, v in res.items()))

print("\n같은 해 안에서 앞 70% 로 직선식을 맞춰 뒤 30% 에 적용 (RMSE kWh)")
for yr, x in b.groupby(b.index.year):
    if len(x) < 200:
        continue
    n = int(len(x) * 0.7)
    tr, te = x.iloc[:n], x.iloc[n:]
    out = {}
    for col, k in (("jr_gsr", "적량"), ("gy_gsr", "광양")):
        out[k] = rmse(te.gen_kwh, np.polyval(np.polyfit(tr[col], tr.gen_kwh, 1), te[col]))
    print(f"  {yr}: 평가 {len(te)}일 | 적량 {out['적량']:.1f} | 광양 {out['광양']:.1f}")

x = a[(a.index >= "2026-01-01") & a.jr_gsr.notna() & (a.stop_day == 0)]
print(f"\n2026-01 ~ 02 (광양 자료 없음): 적량 유효 {len(x)}일, 발전량과의 상관 {x.gen_kwh.corr(x.jr_gsr):.3f}, "
      f"재분석과의 상관 {x.jr_gsr.corr(x.era):.3f}, 적량/재분석 비율 {x.jr_gsr.sum() / x.era.sum():.3f}")
