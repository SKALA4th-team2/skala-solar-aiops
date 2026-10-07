"""s5: (1) 여름-겨울 차이를 방식별로(연도별), (2) 2015년 하락·회복 날짜 주변의 날짜별 값, (3) 2024년 월별 전년 대비(방식별), (4) 2024-03-22 전후 다섯 발전소의 낮 시간 정지.
모두 사후 진단값이다(그날 실측과 실제 날씨 사용)."""
import numpy as np, pandas as pd
from t2_common import *
pd.set_option("display.width", 260); pd.set_option("display.max_rows", 500)
df, H = load_raw(); nb, nbH = load_neighbors(df.index); a = load_asos().reindex(df.index); w = load_weather(df.index)
cal = pd.read_csv(SOLAR / "ev" / "day_table_all.csv", encoding="utf-8-sig", parse_dates=["날짜"]).set_index("날짜")
cat = cal["범주"].fillna("").str.split("_").str[0].reindex(df.index)
d = df.join(w).join(a[["gy_gsr_obs", "gy_kt", "pi_expected_kwh", "pi_valid"]]).join(nb); d["ev"] = cat.isin(["A", "B", "C", "C2"]); d["doy"] = d.index.dayofyear
b = d[(d.index.year >= 2013) & (d.index.year <= 2017) & ~d.ev]
env_p, env_t = np.zeros(367), np.zeros(367)
for k in range(1, 367):
    dist = np.abs(b.doy.values - k); dist = np.minimum(dist, 366 - dist); m = dist <= 10
    env_p[k] = np.quantile(b.peak.values[m], 0.9); env_t[k] = np.quantile(b.y.values[m], 0.9)
d["r_peak"] = d.peak / env_p[d.doy.values]; d["r_tot"] = d.y / env_t[d.doy.values]; d["clear"] = d.sunfrac >= 0.85

def seas(yv, kind):
    x = d.loc[f"{yv}-06-01":f"{yv}-09-30"] if kind == "s" else d.loc[f"{yv}-11-01":f"{yv+1}-02-28"]
    x = x[~x.ev]; c = x[x.clear]; v = x[(x.pi_valid == 1)]
    g = c[c.sat.notna()]; go = c[c.sw.notna()]; gg = x[x.gy_gsr_obs.notna() & (x.gy_kt >= 0.5)]
    return dict(M1_peak_clear=c.r_peak.median(), M1_peak_P90=x.r_peak.quantile(.9), M1b_tot_clear=c.r_tot.median(), M1b_tot_P90=x.r_tot.quantile(.9), M2=v.y.sum() / v.pi_expected_kwh.sum() if len(v) else np.nan,
                M3_sat=g.y.sum() / g.sat.sum() if len(g) > 5 else np.nan, M3_om=go.y.sum() / go.sw.sum(), M3_gy=gg.y.sum() / gg.gy_gsr_obs.sum() if len(gg) else np.nan)
S = pd.DataFrame({yv: seas(yv, "s") for yv in range(2013, 2026)}).T; W = pd.DataFrame({yv: seas(yv, "w") for yv in range(2013, 2026)}).T
# M3 은 여름과 겨울의 비 자체가 다르므로(경사면 효과) 기준 해 대비 지수로 바꾼다. 위성은 2016~2017, 나머지는 2013~2017(2015 겨울은 하락 구간이 끼므로 2014 겨울 제외)
def idx(T, col, base):
    return T[col] / T.loc[base, col].mean()
print("== 1. 여름(6~9월) 수준 ÷ 기준 해 평균, 겨울(11~2월) 수준 ÷ 기준 해 평균, 그 차(여름-겨울, 포인트)")
rows = {}
for col, base in [("M1_peak_clear", [2013, 2015, 2016, 2017]), ("M1_peak_P90", [2013, 2015, 2016, 2017]), ("M1b_tot_clear", [2013, 2015, 2016, 2017]), ("M1b_tot_P90", [2013, 2015, 2016, 2017]), ("M2", [2013, 2015, 2016, 2017]), ("M3_gy", [2013, 2015, 2016, 2017]), ("M3_om", [2013, 2015, 2016]), ("M3_sat", [2016, 2017])]:
    s, wv = idx(S, col, base), idx(W, col, base)
    rows[col + "_여름"] = s; rows[col + "_겨울"] = wv; rows[col + "_차"] = (s - wv) * 100
T = pd.DataFrame(rows)
print(T[[c for c in T.columns if c.endswith("_차")]].round(1).to_string())
print("\n   기간 평균(여름-겨울 차, 포인트):")
for nm, ys in [("2013~2017", [2013, 2015, 2016, 2017]), ("2019~2020", [2019, 2020]), ("2021~2023", [2021, 2022, 2023]), ("2024~2025", [2024, 2025])]:
    print(f"   {nm}: " + " | ".join(f"{c[:-2]} {T.loc[ys, c].mean():+.1f}" for c in T.columns if c.endswith("_차")))
print("\n   여름 수준(기준 해 = 1):"); print(T[[c for c in T.columns if c.endswith("_여름")]].round(3).to_string())
print("\n   겨울 수준(기준 해 = 1):"); print(T[[c for c in T.columns if c.endswith("_겨울")]].round(3).to_string())
T.to_csv(HERE / "s5_summer_winter_by_method.csv", encoding="utf-8-sig")

print("\n== 2. 2015년 하락 시작 주변(2014-12-26~2015-01-08)과 복귀 주변(2015-05-06~05-20)")
for a0, a1 in [("2014-12-26", "2015-01-08"), ("2015-05-06", "2015-05-20")]:
    x = d.loc[a0:a1, ["y", "peak", "r_peak", "sunfrac", "pi_expected_kwh", "health", "subst", "stadium"]].copy()
    x["실제/기대"] = x.y / x.pi_expected_kwh; x["y/보건소"] = x.y / x.health; x["y/변전소"] = x.y / x.subst; x["범주"] = cat.reindex(x.index).replace("", "-")
    print(x.round(2).to_string()); print()

print("== 3. 2024년 월별: 2023년 같은 달 대비 변화(%) (이벤트일 제외)")
rows = []
for mo in range(1, 13):
    def L(yv):
        x = d.loc[f"{yv}-{mo:02d}"]; x = x[~x.ev]; c = x[x.clear]; v = x[x.pi_valid == 1]; g = c[c.sat.notna()]
        return dict(M1_peak_clear=c.r_peak.median(), M1_peak_top5=x.peak.nlargest(5).mean(), M1b_tot_top5=x.y.nlargest(5).mean(), M2=v.y.sum() / v.pi_expected_kwh.sum(), M3_sat=g.y.sum() / g.sat.sum() if len(g) >= 3 else np.nan, n맑은날=len(c))
    p, q, r = L(2023), L(2024), L(2025)
    rows.append(dict(월=mo, **{k + "_24대23": (q[k] / p[k] - 1) * 100 for k in p if k != "n맑은날"}, **{k + "_25대23": (r[k] / p[k] - 1) * 100 for k in ("M1_peak_clear", "M2")}, 맑은날23=p["n맑은날"], 맑은날24=q["n맑은날"]))
print(pd.DataFrame(rows).set_index("월").round(1).to_string())

print("\n== 4. 2024-03-18~04-02: 다섯 발전소의 일합계와 낮 시간(열 10~16) 0 인 시간 수")
x = pd.DataFrame(index=pd.date_range("2024-03-18", "2024-04-02"))
x["하수처리장"] = df.y.reindex(x.index).round(1); x["하수_낮0"] = [(H[df.index.get_loc(t), 9:16] == 0).sum() for t in x.index]
for nm in ("health", "water", "stadium", "subst"):
    x[NBK[nm]] = nb[nm].reindex(x.index).round(1); x[NBK[nm] + "_낮0"] = [(nbH[nm][df.index.get_loc(t), 9:16] == 0).sum() for t in x.index]
print(x.to_string())
print("   하수처리장 2023-07-01~2024-12-31 에서 열 10~16 가운데 3시간 이상 연속 0 인 날:", [str(t.date()) for t in df.loc["2023-07-01":"2024-12-31"].index if max((len(s) for s in "".join("1" if v == 0 else "0" for v in H[df.index.get_loc(t), 9:16]).split("0")), default=0) >= 3])
print("   2025-03-28~04-03 하수처리장·보건소 열 7~10:")
for t in pd.date_range("2025-03-30", "2025-04-02"):
    i = df.index.get_loc(t); print("    ", t.date(), "하수", H[i, 6:10].round(2), "보건소", nbH["health"][i, 6:10].round(2), "변전소", nbH["subst"][i, 6:10].round(2))
