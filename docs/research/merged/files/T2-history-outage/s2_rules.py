"""s2: 서빙 시점(그날 실적이 들어온 뒤)에 쓸 판정 규칙을 같은 정답표, 같은 기간으로 견준다.

정답표: 보완 조사 3 의 달력(이웃 3곳 대비로 만든 사후 표). A 전면 정지 40일, B 부분 정지 10일, C 절반 출력 14일.
        C2(풀린 날 1일), D(짧은 끊김), E(지역 공통)는 켜져도 오탐으로 세지 않는다.
규칙은 모두 사후 감지다. 그날 실적과 그날 날씨 관측(광양 ASOS 는 다음 날 11시 이후, 위성은 당일 저녁)을 쓴다. 예측 입력이 아니다.
 - 실적만: 일합계 1 미만, 또는 5 미만이 이틀 연속
 - ASOS 정지: 일합계 0, 또는 기대 30 kWh 이상인데 실제가 기대의 30% 미만 (ASOS 파일의 pi_outage)
 - ASOS 하루 저하: 기대 80 kWh 이상인데 실제가 기대의 70% 미만 (ASOS 보류 규칙의 하루 단위 조건)
 - ASOS 보류: 정지 또는 하루 저하가 7일 중 3일 이상 (ASOS 파일의 pi_partial_suspect)
 - 위성 60%: (일합계/위성 일사량)을 직전 유효 30일 중앙값으로 나눈 q 가 0.6 미만. 일사량이 대기권 밖의 30% 이상인 날만 (보완 조사 3 의 q_sat)
기대 발전량은 ASOS 묶음이 2013~2014 로 맞춘 식의 값(파일의 pi_expected_kwh)을 그대로 쓴다.
"""
import numpy as np, pandas as pd
from t2_common import *

pd.set_option("display.width", 250); pd.set_option("display.max_rows", 400)
df, H = load_raw()
a = load_asos().reindex(df.index)
T = pd.read_pickle(SOLAR / "ev" / "a3_table.pkl")           # 보완 조사 3 의 표(q_sat, kt_sat, category)
assert np.allclose(T.y, df.y)
c1 = T.category.str.split("_").str[0]
isA, isB, isC = c1 == "A", c1 == "B", c1 == "C"
soft = c1.isin(["C2", "D", "E"])
truth = isA | isB | isC
y, e = df.y, a.pi_expected_kwh
has_e = e.notna()

R = {}
R["실적만(1 미만 또는 5 미만 이틀 연속)"] = (y < 1) | ((y < 5) & (y.shift(1) < 5))
R["ASOS 정지(0 또는 기대 30 이상·30% 미만)"] = (y <= 0) | ((e >= 30) & (y < 0.3 * e))
low70 = (e >= 80) & (y < 0.7 * e)
R["ASOS 정지 + 하루 저하(기대 80 이상·70% 미만)"] = R["ASOS 정지(0 또는 기대 30 이상·30% 미만)"] | low70
R["ASOS 정지 + 하루 저하(기대 80 이상·60% 미만)"] = R["ASOS 정지(0 또는 기대 30 이상·30% 미만)"] | ((e >= 80) & (y < 0.6 * e))
R["ASOS 정지 + 하루 저하(기대 50 이상·70% 미만)"] = R["ASOS 정지(0 또는 기대 30 이상·30% 미만)"] | ((e >= 50) & (y < 0.7 * e))
R["ASOS 보류(파일의 pi_partial_suspect)"] = a.pi_partial_suspect.fillna(0).astype(int) == 1
R["ASOS 정지 또는 보류"] = R["ASOS 정지(0 또는 기대 30 이상·30% 미만)"] | R["ASOS 보류(파일의 pi_partial_suspect)"]
sat60 = (T.q_sat < 0.6).fillna(False)
sat70 = (T.q_sat < 0.7).fillna(False)
R["실적만 + 위성 60% 미만"] = R["실적만(1 미만 또는 5 미만 이틀 연속)"] | sat60
R["실적만 + 위성 70% 미만"] = R["실적만(1 미만 또는 5 미만 이틀 연속)"] | sat70
# 표시 유지: 위성 60% 가 켜지면 '판정 가능하고 q 가 0.6 이상'인 날이 올 때까지 유지
state, lat = False, []
for d in T.index:
    if np.isfinite(T.q_sat[d]):
        state = bool(T.q_sat[d] < 0.6)
    lat.append(state)
R["실적만 + 위성 60% 미만(표시 유지)"] = R["실적만(1 미만 또는 5 미만 이틀 연속)"] | pd.Series(lat, index=T.index)
# ASOS 하루 저하도 같은 방식으로 유지: 켜지면 '기대 80 이상이고 70% 이상'인 날이 올 때까지
state, lat2 = False, []
base = R["ASOS 정지(0 또는 기대 30 이상·30% 미만)"]
for d in df.index:
    if has_e[d] and e[d] >= 80:
        state = bool(y[d] < 0.7 * e[d])
    elif base[d]:
        state = True
    lat2.append(state)
R["ASOS 정지 + 하루 저하 70%(표시 유지)"] = base | pd.Series(lat2, index=df.index)
# 둘을 함께: 어느 한쪽이라도 켜지면
R["실적만 + 위성 60% 또는 ASOS 하루 저하 70%"] = R["실적만 + 위성 60% 미만"] | R["ASOS 정지 + 하루 저하(기대 80 이상·70% 미만)"]
R["실적만 + (위성 60% 그리고 ASOS 70% 둘 다)"] = R["실적만(1 미만 또는 5 미만 이틀 연속)"] | (sat60 & ((e >= 80) & (y < 0.7 * e)))


def events(mask):
    """정답일(A,B,C)을 사흘 이내 간격으로 묶은 사건."""
    ds = list(df.index[truth & mask]); g = []
    for d in ds:
        if g and (d - g[-1][-1]).days <= 3: g[-1].append(d)
        else: g.append([d])
    return g


def score(f, mask, label):
    f = f.fillna(False) & mask
    yrs = mask.sum() / 365.25
    fp = f & ~truth & ~soft
    ev = events(mask)
    hit = [any(f[d] for d in g) for g in ev]
    first = [next((i + 1 for i, d in enumerate(g) if f[d]), None) for g in ev]
    return dict(규칙=label, A=f"{int((f & isA).sum())}/{int((isA & mask).sum())}", B=f"{int((f & isB).sum())}/{int((isB & mask).sum())}", C=f"{int((f & isC).sum())}/{int((isC & mask).sum())}",
                사건=f"{sum(hit)}/{len(ev)}", 첫날감지=sum(1 for x in first if x == 1), 오탐일=int(fp.sum()), 연오탐=round(fp.sum() / yrs, 1), 켜진날=int(f.sum()))


periods = {
    "가. ASOS 날씨가 있는 전체 기간 2013-01-01~2025-12-31 (13.0년)": (df.index >= "2013-01-01") & (df.index <= "2025-12-31"),
    "나. 두 자료가 모두 있는 기간 2015-07-18~2025-12-31 (10.5년)": (df.index >= "2015-07-18") & (df.index <= "2025-12-31"),
    "다. 시험 구간(업로드 파일 뒤 20%) 2023-05-30~2025-12-30": (df.index >= "2023-05-30") & (df.index <= "2025-12-30"),
}
out = []
for pn, m in periods.items():
    m = pd.Series(m, index=df.index)
    print(f"\n== {pn}: 정답 A {int((isA & m).sum())}일, B {int((isB & m).sum())}일, C {int((isC & m).sum())}일, 사건 {len(events(m))}건")
    rows = []
    for k, f in R.items():
        if pn.startswith("가") and "위성" in k:
            continue
        rows.append(score(f, m, k))
    t = pd.DataFrame(rows); t.insert(0, "기간", pn[:2]); out.append(t)
    print(t.drop(columns="기간").to_string(index=False))
pd.concat(out).to_csv(HERE / "s2_rule_headtohead.csv", index=False, encoding="utf-8-sig")

print("\n== 절반 출력 14일을 각 규칙이 잡는가 (1 = 켜짐)")
C = df.index[isC | (c1 == "C2")]
keys = ["실적만(1 미만 또는 5 미만 이틀 연속)", "ASOS 정지(0 또는 기대 30 이상·30% 미만)", "ASOS 정지 + 하루 저하(기대 80 이상·70% 미만)", "ASOS 보류(파일의 pi_partial_suspect)",
        "ASOS 정지 + 하루 저하 70%(표시 유지)", "실적만 + 위성 60% 미만", "실적만 + 위성 60% 미만(표시 유지)"]
tab = pd.DataFrame({"일합계": y.reindex(C).round(1), "기대": e.reindex(C).round(0), "실제/기대": (y / e).reindex(C).round(2), "위성q": T.q_sat.reindex(C).round(2)})
for i, k in enumerate(keys):
    tab[f"규칙{i+1}"] = R[k].reindex(C).astype(int)
print("  규칙 번호:", " | ".join(f"{i+1}={k}" for i, k in enumerate(keys)))
print(tab.to_string())

print("\n== 부분 정지 10일을 각 규칙이 잡는가")
B = df.index[isB]
tab = pd.DataFrame({"일합계": y.reindex(B).round(1), "기대": e.reindex(B).round(0), "실제/기대": (y / e).reindex(B).round(2), "위성q": T.q_sat.reindex(B).round(2)})
for i, k in enumerate(keys):
    tab[f"규칙{i+1}"] = R[k].reindex(B).astype(int)
print(tab.to_string())

print("\n== 'ASOS 정지 + 하루 저하(기대 80 이상·70% 미만)'의 오탐일(전체 기간): 날짜, 일합계, 기대, 비, 보완3 범주, 이웃 3곳 q 중앙값")
f = R["ASOS 정지 + 하루 저하(기대 80 이상·70% 미만)"] & ~truth & ~soft & (df.index <= "2025-12-31")
fp = pd.DataFrame({"일합계": y[f].round(1), "기대": e[f].round(0), "비": (y / e)[f].round(2), "범주": c1[f].replace("", "-"), "이웃q3": T.q3[f].round(2), "광양일사": a.gy_gsr_obs[f], "위성": T.sat[f]})
print(fp.to_string())
print("  연도별 오탐 수:", fp.groupby(fp.index.year).size().to_dict(), "| 월별:", fp.groupby(fp.index.month).size().to_dict())
print("  오탐 가운데 이웃 대비가 정상(q3 0.85 이상)인 날:", int((fp["이웃q3"] >= 0.85).sum()), "| 0.7~0.85:", int(((fp["이웃q3"] >= 0.7) & (fp["이웃q3"] < 0.85)).sum()), "| 0.7 미만:", int((fp["이웃q3"] < 0.7).sum()), "| 판정 불가:", int(fp["이웃q3"].isna().sum()))

print("\n== 2021-05 하락 뒤 기대식 수준이 낮아진 영향: 실제/기대 의 연도별 중앙값(기대 80 이상인 날)")
r = (y / e).where(e >= 80)
print(r.groupby(r.index.year).median().round(3).to_dict())
