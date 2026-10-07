"""s2b: ASOS 기대 발전량 대비 비율을 위성 규칙과 같은 방식(직전 유효 30일 중앙값 대비 q)으로 바꿔 견준다.
ASOS 기대식은 2013~2014 수준에 고정이라 2021-05 하락 뒤에는 정상일의 실제/기대가 0.90 안팎이다. 고정 임계값(기대의 70%)은
그만큼 정상 수준에 가까워져 오탐이 늘 수 있다. 여기서는 기준을 '그날까지의 최근 수준'으로 바꾼다(그날까지의 값만 사용).
모두 사후 감지 규칙이고 예측 입력이 아니다.
"""
import numpy as np, pandas as pd
from t2_common import *
pd.set_option("display.width", 250)
df, H = load_raw(); a = load_asos().reindex(df.index)
T = pd.read_pickle(SOLAR / "ev" / "a3_table.pkl")
c1 = T.category.str.split("_").str[0]; isA, isB, isC = c1 == "A", c1 == "B", c1 == "C"; soft = c1.isin(["C2", "D", "E"]); truth = isA | isB | isC
y, e = df.y, a.pi_expected_kwh
stop0 = (y < 1) | ((y < 5) & (y.shift(1) < 5))

def rolling_q(emin, n=30, lo=0.7, hi=1.43, minn=10):
    """q = (실제/기대) / 직전 유효 n일의 중앙값. 유효 = 기대 emin 이상이고 q 가 lo~hi."""
    r = (y / e).where(e >= emin)
    hist, q = [], pd.Series(np.nan, index=df.index)
    for d in df.index:
        if np.isfinite(r[d]):
            if len(hist) >= minn:
                b = float(np.median(hist[-n:])); q[d] = r[d] / b
                if lo <= q[d] <= hi: hist.append(r[d])
            else:
                if 0.7 <= r[d] <= 1.43: hist.append(r[d])
    return q

def events(mask):
    ds = list(df.index[truth & mask]); g = []
    for d in ds:
        if g and (d - g[-1][-1]).days <= 3: g[-1].append(d)
        else: g.append([d])
    return g

def score(f, mask, label):
    f = f.fillna(False) & mask; yrs = mask.sum() / 365.25; fp = f & ~truth & ~soft; ev = events(mask)
    return dict(규칙=label, A=f"{int((f & isA).sum())}/{int((isA & mask).sum())}", B=f"{int((f & isB).sum())}/{int((isB & mask).sum())}", C=f"{int((f & isC).sum())}/{int((isC & mask).sum())}",
                사건=f"{sum(any(f[d] for d in g) for g in ev)}/{len(ev)}", 첫날=sum(1 for g in ev if f[g[0]]), 오탐일=int(fp.sum()), 연오탐=round(fp.sum() / yrs, 1), 판정가능비율=None)

def latch(q, thr):
    state, out = False, []
    for d in df.index:
        if np.isfinite(q[d]): state = bool(q[d] < thr)
        out.append(state)
    return pd.Series(out, index=df.index)

rows = []
periods = {"가(2013-01-01~2025-12-31)": pd.Series((df.index <= "2025-12-31"), index=df.index), "나(2015-07-18~2025-12-31)": pd.Series((df.index >= "2015-07-18") & (df.index <= "2025-12-31"), index=df.index)}
Q = {}
for emin in (50, 80):
    Q[emin] = rolling_q(emin)
for pn, m in periods.items():
    for emin in (50, 80):
        q = Q[emin]
        for thr in (0.5, 0.6, 0.65, 0.7):
            r = score(stop0 | (q < thr), m, f"실적만 + ASOS q<{thr} (기대 {emin} 이상)"); r["판정가능비율"] = round(float((q.notna() & m).sum() / m.sum()), 3); r["기간"] = pn; rows.append(r)
        r = score(stop0 | latch(q, 0.6), m, f"실적만 + ASOS q<0.6 표시 유지 (기대 {emin} 이상)"); r["기간"] = pn; rows.append(r)
    if pn.startswith("나"):
        qs = T.q_sat
        for thr in (0.6, 0.7):
            r = score(stop0 | (qs < thr), m, f"실적만 + 위성 q<{thr}"); r["판정가능비율"] = round(float((qs.notna() & m).sum() / m.sum()), 3); r["기간"] = pn; rows.append(r)
        r = score(stop0 | latch(qs, 0.6), m, "실적만 + 위성 q<0.6 표시 유지"); r["기간"] = pn; rows.append(r)
        r = score(stop0 | ((qs < 0.6) & (Q[80] < 0.7)), m, "실적만 + (위성 q<0.6 그리고 ASOS q<0.7)"); r["기간"] = pn; rows.append(r)
        r = score(stop0 | ((qs < 0.6) | (Q[80] < 0.6)), m, "실적만 + (위성 q<0.6 또는 ASOS q<0.6)"); r["기간"] = pn; rows.append(r)
t = pd.DataFrame(rows)[["기간", "규칙", "A", "B", "C", "사건", "첫날", "오탐일", "연오탐", "판정가능비율"]]
print(t.to_string(index=False)); t.to_csv(HERE / "s2b_rules_norm.csv", index=False, encoding="utf-8-sig")

q = Q[80]
print("\n== ASOS q(기대 80 이상, 직전 30일 기준): 절반 출력 14일과 풀린 날")
C = df.index[isC | (c1 == "C2")]
print(pd.DataFrame({"일합계": y[C].round(1), "기대": e[C].round(0), "ASOS_q": q[C].round(2), "위성_q": T.q_sat[C].round(2)}).to_string())
f = (stop0 | (q < 0.6)) & ~truth & ~soft & (df.index <= "2025-12-31")
print("\n== '실적만 + ASOS q<0.6 (기대 80 이상)' 오탐일:")
print(pd.DataFrame({"일합계": y[f].round(1), "기대": e[f].round(0), "ASOS_q": q[f].round(2), "위성_q": T.q_sat[f].round(2), "이웃q3": T.q3[f].round(2), "광양일사": a.gy_gsr_obs[f], "위성일사": T.sat[f]}).to_string())
print("  월별:", pd.Series(1, index=df.index[f]).groupby(df.index[f].month).size().to_dict(), "| 연도별:", pd.Series(1, index=df.index[f]).groupby(df.index[f].year).size().to_dict())
print("\n== 판정 가능한 날의 비율(월별, 2015-07-18~2025-12-31): ASOS 기대 80 이상 / 위성 kt 0.3 이상")
m = periods["나(2015-07-18~2025-12-31)"]
print(pd.DataFrame({"ASOS": q[m].notna().groupby(df.index[m].month).mean().round(2), "위성": T.q_sat[m].notna().groupby(df.index[m].month).mean().round(2)}).T.to_string())
