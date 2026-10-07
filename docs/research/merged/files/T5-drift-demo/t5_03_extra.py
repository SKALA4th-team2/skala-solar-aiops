"""T5 대조 3: (가) 2024년 회복의 크기를 두 정의로, (나) 2024-07 절반 출력 9일과 정지·보류 표시, (다) 정지 규칙 세 가지를 같은 날짜표(보완 조사 3 의 설비 이벤트 달력)에 올림,
(라) 41행 배치 하나로 판정할 때(실습 코드 구조)의 성능 지표 감지율과 오경보율, (마) 2025-04-15 무렵의 성능 지표 하락.
자료는 읽기만 한다. 모든 값은 그날이 지난 뒤의 사후 계산이다.
"""
from pathlib import Path
import numpy as np
import pandas as pd

S = Path(__file__).resolve().parents[2]
pd.set_option("display.width", 250); pd.set_option("display.max_columns", 60); pd.set_option("display.max_rows", 400)
raw = pd.read_csv(S / "solar" / "data_15043409.csv", encoding="cp949")
HOURS = [str(h) for h in range(1, 25)]
g = pd.DataFrame({"date": pd.to_datetime(raw["년월일"]), "gen": raw["총량(kw)"].astype(float).values})
g["peak"] = raw[HOURS].astype(float).values.max(axis=1)
g = g.sort_values("date").set_index("date")
a = pd.read_csv(S / "asos" / "hadong_daily_full.csv", parse_dates=["date"]).set_index("date")
g["e"] = a.pi_expected_kwh.reindex(g.index); g["doy"] = g.index.dayofyear
g["gy_sunfrac"] = a.gy_sun_frac.reindex(g.index)
D3_OUT = [("2015-04-23", "2015-05-06"), ("2016-12-22", "2016-12-27"), ("2018-07-04", "2018-08-01"), ("2020-09-08", "2020-09-08")]
g["d3_out"] = False
for x, y in D3_OUT:
    g.loc[x:y, "d3_out"] = True
gen = g.gen.values.copy(); e = g.e.values.copy()


def gate(gen_, e_):
    outage = (gen_ <= 0) | ((e_ >= 30) & (gen_ < 0.3 * e_))
    low = ((e_ >= 80) & (gen_ < 0.7 * e_)) | outage
    susp = pd.Series(low.astype(float)).rolling(7, min_periods=1).sum().values >= 3
    valid = ~np.isnan(e_) & (e_ > 0) & ~outage & ~susp
    return outage, low, susp, valid


outage, low, susp, valid = gate(gen, e)


def envelope(a_, b_, half=10, q=0.90):
    bb = g[(g.index >= a_) & (g.index <= b_) & (~g.d3_out)]
    doy = bb.doy.values; v = bb.peak.values; env = np.zeros(367)
    for d in range(1, 367):
        dist = np.abs(doy - d); dist = np.minimum(dist, 366 - dist); k = dist <= half
        if k.sum() < 5:
            k = dist <= 3 * half
        env[d] = np.quantile(v[k], q)
    return env


env13 = envelope(pd.Timestamp("2013-01-01"), pd.Timestamp("2017-12-31"))
g["r13"] = np.where(g.d3_out, np.nan, g.peak / env13[g.doy.values])


def pi_sum(a_, b_, v=None):
    v = valid if v is None else v
    m = (g.index >= a_) & (g.index <= b_) & v
    gc = np.clip(gen[m], 0.5 * e[m], 1.5 * e[m])
    return gc.sum() / e[m].sum(), int(m.sum())


print("[가] 2024년 회복의 크기: 같은 철끼리 한 해 차이 (PI = 합계 실제 / 합계 기대, r_peak P90 = 2013~2017 포락선 대비 시간대 최대값의 90번째 백분위)")
rows = []
for nm, span in {"1~2월": (1, 1, 2, 28), "3~4월": (3, 1, 4, 30), "5~9월": (5, 1, 9, 30), "6~8월": (6, 1, 8, 31), "10~12월": (10, 1, 12, 31), "3-28~다음 해 3-27": None}.items():
    r = dict(철=nm)
    m0, d0, m1, d1 = span if span else (0, 0, 0, 0)
    for y in (2022, 2023, 2024, 2025):
        if nm.startswith("3-28"):
            x0, x1 = pd.Timestamp(y, 3, 28), pd.Timestamp(y + 1, 3, 27)
        else:
            x0, x1 = pd.Timestamp(y, m0, d0), pd.Timestamp(y, m1, d1)
        if x1 > pd.Timestamp("2025-12-31"):
            r[f"PI{y}"] = np.nan; r[f"rP90_{y}"] = np.nan; continue
        r[f"PI{y}"] = round(pi_sum(x0, x1)[0], 3); r[f"rP90_{y}"] = round(g.r13.loc[x0:x1].quantile(0.9), 3)
    r["PI 2024/2023 pct"] = round((r["PI2024"] / r["PI2023"] - 1) * 100, 1) if r["PI2024"] == r["PI2024"] else np.nan
    r["rP90 2024/2023 pct"] = round((r["rP90_2024"] / r["rP90_2023"] - 1) * 100, 1) if r["rP90_2024"] == r["rP90_2024"] else np.nan
    rows.append(r)
print(pd.DataFrame(rows).to_string(index=False))

print("\n[나] 2024-07-06 ~ 07-24 의 날짜별 값과 ASOS 정지 관문 표시 (보완 조사 3 의 절반 출력은 07-10 ~ 07-18, 07-19 낮에 풀림)")
t = g.loc["2024-07-06":"2024-07-24", ["gen", "peak", "e", "gy_sunfrac", "r13"]].copy()
t["실제/기대"] = t.gen / t.e
sl = (g.index >= "2024-07-06") & (g.index <= "2024-07-24")
t["정지"] = outage[sl].astype(int); t["70%미만"] = low[sl].astype(int); t["보류"] = susp[sl].astype(int); t["판정에 씀"] = valid[sl].astype(int)
print(t.round(3).to_string())

print("\n[다] 정지 규칙 세 가지를 보완 조사 3 의 설비 이벤트 달력(이웃 발전소 대비로 만든 사후 정답표)에 올림. 2013-01-01 ~ 2025-12-31")
cal = pd.read_csv(S / "solar" / "ev" / "equipment_event_calendar.csv", encoding="utf-8-sig")
catcol = [c for c in cal.columns if cal[c].astype(str).str.contains("A_|B_|C_").any()][0]
cal["date"] = pd.to_datetime(cal["날짜"]); cal["cat"] = cal[catcol].astype(str).str.split("_").str[0]
print("  달력 범주 열:", catcol, "| 범주별 일수:", cal.cat.value_counts().to_dict())
catmap = cal.set_index("date").cat.reindex(g.index).fillna("-")
lt1 = (g.gen < 1).values; lt5 = (g.gen < 5).values
r_d3 = lt5 & (np.r_[False, lt5[:-1]])                                 # 5 미만 이틀 연속(둘째 날부터 켜짐)
r_gap3 = lt1 | r_d3                                                    # 1 미만 또는 5 미만 이틀 연속
rules = {"사전 조사 D3: 일합계 5 미만 이틀 연속": r_d3, "보완 조사 3: 1 미만 또는 5 미만 이틀 연속": r_gap3,
         "ASOS 정지(0 이거나 기대 30 이상인데 30% 미만)": outage, "ASOS 정지 또는 보류(판정에서 빠지는 날)": (outage | susp),
         "ASOS 하루 단위 70% 미만 표시(기대 80 이상)": low}
per = (g.index <= "2025-12-31")
rows = []
for nm, fl in rules.items():
    fl = fl & per
    r = dict(규칙=nm, 켜진날=int(fl.sum()))
    for c, tot in (("A", 40), ("B", 10), ("C", 14), ("C2", 1), ("D", 8), ("E", 1)):
        r[f"{c}({tot})"] = int((fl & (catmap == c).values).sum())
    oth = fl & ~catmap.isin(["A", "B", "C", "C2", "D", "E"]).values
    r["그 밖"] = int(oth.sum())
    r["그 밖의 날짜(앞 8개)"] = ", ".join(str(d.date()) for d in g.index[oth][:8])
    rows.append(r)
print(pd.DataFrame(rows).to_string(index=False))
c_days = g.index[(catmap == "C").values]
print("  절반 출력 14일의 실제/기대와 표시:", [(str(d.date()), round(float(g.gen[d] / g.e[d]), 2), "정지" if outage[g.index.get_loc(d)] else ("보류" if susp[g.index.get_loc(d)] else ("70%미만" if low[g.index.get_loc(d)] else "표시 없음"))) for d in c_days])

print("\n[라] 실습 코드 구조: 41행 배치 하나(대상 21일)의 PI 를 '주입 전 직전 365일 PI'와 견줌. 주입 뒤 행만으로 된 배치(행 s ~ s+40)")


def batch_table(starts, label):
    rows = []
    for f in (1.0, 0.915, 0.86, 0.80, 0.70):
        dev = []; held = []
        for st in starts:
            i0 = g.index.get_loc(st)
            if i0 + 40 >= len(g) or np.isnan(e[i0 + 40]):
                continue
            gg = gen.copy(); gg[i0:] *= f
            o2, l2, s2, v2 = gate(gg, e)
            mb = v2.copy(); mb[i0:] = False; mb[:i0 - 365] = False
            gc = np.clip(gg, 0.5 * e, 1.5 * e)
            base = gc[mb].sum() / e[mb].sum()
            mt = np.zeros(len(g), bool); mt[i0 + 20:i0 + 41] = True; mt &= v2
            held.append(21 - int(mt.sum()))
            if mt.sum() < 15:
                dev.append(np.nan); continue
            dev.append(gc[mt].sum() / e[mt].sum() / base - 1)
        dev = np.array(dev); ok = ~np.isnan(dev)
        rows.append(dict(구간=label, 배율=f, 배치수=len(dev), 판정못함pct=round((~ok).mean() * 100, 1), 편차중앙pct=round(np.nanmedian(dev) * 100, 1),
                         편차5pct=round(np.nanpercentile(dev, 5) * 100, 1), 편차95pct=round(np.nanpercentile(dev, 95) * 100, 1),
                         **{"-7.5% 아래 pct": round((dev < -0.075).sum() / len(dev) * 100, 1), "-10% 아래 pct": round((dev < -0.10).sum() / len(dev) * 100, 1),
                            "+7.5% 위 pct": round((dev > 0.075).sum() / len(dev) * 100, 1), "빠진 날 중앙": float(np.median(held))}))
    return pd.DataFrame(rows)


s25 = [d for d in pd.date_range("2025-03-08", "2025-12-31", freq="7D") if d + pd.Timedelta(days=40) <= pd.Timestamp("2025-12-31")]
sN1 = list(pd.date_range("2016-01-01", "2018-05-20", freq="7D"))
print(pd.concat([batch_table(s25, "2025-03 ~ 12 (7일 간격)"), batch_table(sN1, "N1 2016-01 ~ 2018-05 (7일 간격)")]).to_string(index=False))

print("\n[마] 2025년의 성능 지표: 달별 PI(합계 실제 / 합계 기대)와 한 해 전 같은 달")
rows = []
for m in range(1, 13):
    r = dict(달=m)
    for y in (2023, 2024, 2025):
        x0 = pd.Timestamp(y, m, 1); x1 = x0 + pd.offsets.MonthEnd(0)
        r[y] = round(pi_sum(x0, x1)[0], 3)
    rows.append(r)
print(pd.DataFrame(rows).to_string(index=False))
