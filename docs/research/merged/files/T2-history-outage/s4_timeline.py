"""s4: 출력 수준 변화의 크기를 같은 기간, 네 가지 방식으로 다시 잰다.

방식(모두 사후 진단값이다. 그날의 실측이나 실제 날씨를 쓰므로 예측 입력으로는 쓸 수 없다)
 M1 맑은 날 최대 출력 : 그날 시간값 최대 ÷ (2013~2017년 같은 날짜 ±10일의 90번째 백분위). 구간 값은 맑은 날(Open-Meteo 일조율 0.85 이상)의 중앙값과 전체 날의 90번째 백분위(D3 방식)
 M2 성능 지표         : 합계 실제 ÷ 합계 기대(ASOS 묶음이 2013~2014 로 맞춘 광양 날씨 식). pi_valid 인 날만
 M3 발전량÷일사량      : 합계 발전량 ÷ 합계 일사량. 광양 ASOS 관측, Open-Meteo 과거 날씨 값, 위성 세 가지. 계절에 따라 비가 달라 같은 달력 구간끼리만 견준다
 M4 이웃 대비          : 합계 발전량 ÷ 합계 이웃 발전량(보건소, 변전소). 2024-03-22 이후에는 이웃도 인버터 교체 대상이라 쓰지 않는다
정지·이벤트일(보완 조사 3 의 A, B, C, C2)은 모든 구간에서 뺀다.
"""
import numpy as np, pandas as pd
from t2_common import *
pd.set_option("display.width", 260); pd.set_option("display.max_rows", 500)
df, H = load_raw(); nb, nbH = load_neighbors(df.index); a = load_asos().reindex(df.index); w = load_weather(df.index)
cal = pd.read_csv(SOLAR / "ev" / "day_table_all.csv", encoding="utf-8-sig", parse_dates=["날짜"]).set_index("날짜")
cat = cal["범주"].fillna("").str.split("_").str[0].reindex(df.index)
ev = cat.isin(["A", "B", "C", "C2"])
d = df.join(w).join(a[["gy_gsr_obs", "gy_kt", "pi_expected_kwh", "pi_valid", "gy_max_ta"]]).join(nb)
d["ev"] = ev
d["doy"] = d.index.dayofyear

# --- M1 포락선(2013~2017, ±10일, P90). 이벤트일 제외
b = d[(d.index.year >= 2013) & (d.index.year <= 2017) & ~d.ev]
env_p, env_t = np.zeros(367), np.zeros(367)
for k in range(1, 367):
    dist = np.abs(b.doy.values - k); dist = np.minimum(dist, 366 - dist); m = dist <= 10
    env_p[k] = np.quantile(b.peak.values[m], 0.9); env_t[k] = np.quantile(b.y.values[m], 0.9)
d["r_peak"] = d.peak / env_p[d.doy.values]; d["r_tot"] = d.y / env_t[d.doy.values]
d["clear"] = d.sunfrac >= 0.85
# 이웃이 멀쩡한 날(이웃 일합계 20 이상이고, 이웃 자체가 직전 60일 대비 급락하지 않은 날)
for nm in ("health", "subst"):
    r = (d[nm] / d.sw).where(d.sw > 3)
    base = r.shift(1).rolling(60, min_periods=20).median()
    d["ok_" + nm] = (d[nm] >= 20) & ((r / base) > 0.6)


def lvl(a0, a1):
    x = d.loc[a0:a1]; x = x[~x.ev]
    o = {}
    c = x[x.clear]
    o["M1 맑은 날 최대 출력(맑은 날 중앙값)"] = c.r_peak.median(); o["_n맑은날"] = len(c)
    o["M1 맑은 날 최대 출력(전체 P90, D3 방식)"] = x.r_peak.quantile(0.9)
    o["M1b 일합계 지수(전체 P90)"] = x.r_tot.quantile(0.9)
    v = x[(x.pi_valid == 1) & x.pi_expected_kwh.notna()]
    o["M2 성능 지표"] = v.y.sum() / v.pi_expected_kwh.sum() if len(v) else np.nan; o["_n유효"] = len(v)
    g = x[x.gy_gsr_obs.notna() & (x.gy_kt >= 0.5)]
    o["M3 발전량÷광양 관측 일사량(맑음 지수 0.5 이상)"] = g.y.sum() / g.gy_gsr_obs.sum() if len(g) else np.nan
    g = x[x.sw.notna() & x.clear]
    o["M3 발전량÷Open-Meteo 일사량(맑은 날)"] = g.y.sum() / g.sw.sum() if len(g) else np.nan
    g = x[x.sat.notna() & x.clear]
    o["M3 발전량÷위성 일사량(맑은 날)"] = g.y.sum() / g.sat.sum() if len(g) > 5 else np.nan
    for nm in ("health", "subst"):
        g = x[x["ok_" + nm]]
        o[f"M4 {NBK[nm]} 대비"] = g.y.sum() / g[nm].sum() if len(g) else np.nan
    return pd.Series(o)


def cmp(title, before, after, note=""):
    A, B = lvl(*before), lvl(*after)
    t = pd.DataFrame({"앞": A, "뒤": B}); t["변화%"] = (t["뒤"] / t["앞"] - 1) * 100
    t = t[~t.index.str.startswith("_")]
    print(f"\n-- {title}\n   앞 {before[0]}~{before[1]} (맑은 날 {int(A['_n맑은날'])}일, 유효 {int(A['_n유효'])}일) | 뒤 {after[0]}~{after[1]} (맑은 날 {int(B['_n맑은날'])}일, 유효 {int(B['_n유효'])}일) {note}")
    print(t.round(3).to_string())
    t.insert(0, "비교", title); return t

out = []
print("=========== [1] 2015년 일시 하락과 회복 ===========")
out.append(cmp("2015 하락: 직전 석 달 대 하락 구간", ("2014-10-01", "2015-01-02"), ("2015-01-04", "2015-04-22"), "(계절이 달라 M3·M4 는 참고만)"))
out.append(cmp("2015 하락: 한 해 전 같은 구간 대비", ("2014-01-04", "2014-04-22"), ("2015-01-04", "2015-04-22")))
out.append(cmp("2015 회복: 하락 구간 대 복귀 뒤 석 달", ("2015-01-04", "2015-04-22"), ("2015-05-16", "2015-08-31"), "(계절이 달라 M3·M4 는 참고만)"))
out.append(cmp("2015 회복 뒤: 한 해 전 같은 구간 대비(변화가 없어야 함)", ("2014-05-16", "2014-12-31"), ("2015-05-16", "2015-12-31")))

print("\n=========== [2] 2018-08 재가동 뒤 여름 하락: 해마다 여름(6~9월)과 겨울(11~2월) 수준 ===========")
rows = []
for yv in range(2013, 2026):
    s = lvl(f"{yv}-06-01", f"{yv}-09-30"); wv = lvl(f"{yv}-11-01", f"{yv+1}-02-28")
    rows.append(dict(해=yv, 여름_M1맑은날=s.iloc[0], 겨울_M1맑은날=wv.iloc[0], 차_M1=s.iloc[0] - wv.iloc[0], 여름_M1_P90=s.iloc[2], 겨울_M1_P90=wv.iloc[2], 차_M1_P90=s.iloc[2] - wv.iloc[2],
                     여름_M2=s["M2 성능 지표"], 겨울_M2=wv["M2 성능 지표"], 차_M2=s["M2 성능 지표"] - wv["M2 성능 지표"]))
t = pd.DataFrame(rows).set_index("해"); print(t.round(3).to_string()); t.to_csv(HERE / "s4_summer_winter.csv", encoding="utf-8-sig")
g = lambda ys, c: t.loc[ys, c].mean()
for nm, ys in [("2013~2017", [2013, 2014, 2015, 2016, 2017]), ("2019~2020", [2019, 2020]), ("2021~2023", [2021, 2022, 2023]), ("2024~2025", [2024, 2025])]:
    print(f"   {nm}: 여름-겨울 M1(맑은 날 중앙값) {g(ys,'차_M1')*100:+.1f}포인트, M1(P90) {g(ys,'차_M1_P90')*100:+.1f}포인트, M2 {g(ys,'차_M2')*100:+.1f}%p")
print("   2018년 재가동 앞뒤 석 달(같은 여름 안): ")
out.append(cmp("2018 재가동 앞뒤: 2018-05-01~06-12 대 2018-08-02~09-30", ("2018-05-01", "2018-06-12"), ("2018-08-02", "2018-09-30"), "(계절이 달라 M3·M4 는 참고만)"))
out.append(cmp("2018 재가동 뒤 여름: 한 해 전 같은 구간 대비", ("2017-08-02", "2017-09-30"), ("2018-08-02", "2018-09-30")))
out.append(cmp("2019 여름: 2017 여름 대비", ("2017-06-01", "2017-09-30"), ("2019-06-01", "2019-09-30")))

print("\n=========== [3] 2021년 5월 하락 ===========")
out.append(cmp("2021 하락(짧은 창): 2021-04-01~05-12 대 05-19~06-30", ("2021-04-01", "2021-05-12"), ("2021-05-19", "2021-06-30"), "(계절이 달라 M3·M4 는 참고만. 여름 하락이 섞인다)"))
out.append(cmp("2021 하락 직후 6주: 한 해 전 같은 구간 대비", ("2020-05-19", "2020-06-30"), ("2021-05-19", "2021-06-30")))
out.append(cmp("2021 하락 뒤 12개월: 직전 12개월 대비", ("2020-05-19", "2021-05-12"), ("2021-05-19", "2022-05-12")))
out.append(cmp("2021 하락 뒤 첫 겨울: 직전 겨울 대비", ("2020-12-01", "2021-02-28"), ("2021-12-01", "2022-02-28")))
out.append(cmp("2021 하락 뒤 여름(6~9월): 2020 여름 대비", ("2020-06-01", "2020-09-30"), ("2021-06-01", "2021-09-30")))
out.append(cmp("대조: 2020-05-19~06-30 대 2019 같은 구간(변화가 없어야 함)", ("2019-05-19", "2019-06-30"), ("2020-05-19", "2020-06-30")))
out.append(cmp("ASOS 구간 정의: 2019-04-01~2021-05-13 대 2021-05-18~2024-03-27", ("2019-04-01", "2021-05-13"), ("2021-05-18", "2024-03-27")))

print("\n   2021-05-06~05-26 날짜별 (열 번호는 원자료의 열. 일조율은 Open-Meteo, kt 는 광양 관측)")
x = d.loc["2021-05-06":"2021-05-26", ["y", "peak", "r_peak", "sunfrac", "gy_kt", "gy_gsr_obs", "sw", "pi_expected_kwh", "health", "subst"]].copy()
x["y/광양일사"] = x.y / x.gy_gsr_obs; x["y/OM일사"] = x.y / x.sw; x["실제/기대"] = x.y / x.pi_expected_kwh; x["y/보건소"] = x.y / x.health; x["y/변전소"] = x.y / x.subst
print(x.round(2).to_string())
pre = d.loc["2021-04-15":"2021-05-12"]; 
print("   참고: 2021-04-15~05-12 의 실제/기대 중앙값 %.3f, y/변전소 중앙값 %.3f, y/보건소 중앙값 %.3f, 맑은 날 r_peak 중앙값 %.3f" % ((pre.y / pre.pi_expected_kwh).median(), (pre.y / pre.subst).median(), (pre.y / pre.health).median(), pre[pre.clear].r_peak.median()))

print("\n=========== [4] 2023-11 복귀는 예년의 가을 복귀와 다른가: 10월·11월·12월 수준 ===========")
rows = []
for yv in range(2018, 2026):
    r = {"해": yv}
    for mo in (9, 10, 11, 12):
        s = lvl(f"{yv}-{mo:02d}-01", str((pd.Timestamp(f"{yv}-{mo:02d}-01") + pd.offsets.MonthEnd(0)).date()))
        r[f"{mo}월_M1"] = s.iloc[0]; r[f"{mo}월_M2"] = s["M2 성능 지표"]
    rows.append(r)
t = pd.DataFrame(rows).set_index("해"); t["M1_11월-10월"] = t["11월_M1"] - t["10월_M1"]; t["M2_11월-10월"] = t["11월_M2"] - t["10월_M2"]; t["M1_11월-9월"] = t["11월_M1"] - t["9월_M1"]
print(t.round(3).to_string())
print("\n   2023-10-25~11-15 날짜별")
x = d.loc["2023-10-25":"2023-11-15", ["y", "peak", "r_peak", "sunfrac", "tmax", "gy_max_ta", "pi_expected_kwh"]].copy(); x["실제/기대"] = x.y / x.pi_expected_kwh
print(x.round(2).to_string())

print("\n=========== [5] 2024년 회복 ===========")
out.append(cmp("교체 전 2024-01-01~03-21: 한 해 전 같은 구간 대비", ("2023-01-01", "2023-03-21"), ("2024-01-01", "2024-03-21")))
out.append(cmp("교체 직후 2024-03-23~04-30: 한 해 전 같은 구간 대비", ("2023-03-23", "2023-04-30"), ("2024-03-23", "2024-04-30")))
out.append(cmp("2024-05-01~10-31: 한 해 전 같은 구간 대비", ("2023-05-01", "2023-10-31"), ("2024-05-01", "2024-10-31")))
out.append(cmp("2024 여름(6~9월): 2023 여름 대비", ("2023-06-01", "2023-09-30"), ("2024-06-01", "2024-09-30")))
out.append(cmp("2024-11~2025-02 겨울: 한 해 전 겨울 대비", ("2023-11-01", "2024-02-29"), ("2024-11-01", "2025-02-28")))
out.append(cmp("교체 뒤 12개월: 직전 12개월 대비", ("2023-03-23", "2024-03-21"), ("2024-03-23", "2025-03-22")))
out.append(cmp("ASOS 구간 정의: 2021-05-18~2024-03-27 대 2024-03-28~2025-12-31", ("2021-05-18", "2024-03-27"), ("2024-03-28", "2025-12-31")))
out.append(cmp("교체 뒤 12개월: 하락 전 12개월(2020-05-19~2021-05-12) 대비", ("2020-05-19", "2021-05-12"), ("2024-03-23", "2025-03-22"), "(이웃 대비는 쓰지 않음)"))
out.append(cmp("2025 여름(6~9월): 2020 여름 대비", ("2020-06-01", "2020-09-30"), ("2025-06-01", "2025-09-30")))
out.append(cmp("2025 여름(6~9월): 2017 여름 대비", ("2017-06-01", "2017-09-30"), ("2025-06-01", "2025-09-30")))
out.append(cmp("2024-12~2025-02 겨울: 2020-12~2021-02 겨울 대비", ("2020-12-01", "2021-02-28"), ("2024-12-01", "2025-02-28")))
pd.concat(out).to_csv(HERE / "s4_level_changes.csv", encoding="utf-8-sig")

print("\n=========== [6] 연도별 수준 요약(이벤트일 제외) ===========")
rows = []
for yv in range(2013, 2026):
    s = lvl(f"{yv}-01-01", f"{yv}-12-31"); rows.append(dict(해=yv, M1_맑은날=s.iloc[0], M1_P90=s.iloc[2], M2=s["M2 성능 지표"], 연합계_kWh=d.loc[str(yv)].y.sum(), 시간최대=d.loc[str(yv)].peak.max()))
print(pd.DataFrame(rows).set_index("해").round(3).to_string())
