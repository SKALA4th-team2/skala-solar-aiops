"""s7: (1) 추천 판정 규칙 하나를 정확히 적은 대로 계산해 성적을 낸다. (2) 팀이 쓸 설비 이벤트 목록 파일을 만든다.

추천 규칙(매일 그날 실적 마감 뒤 계산하는 사후 판정. 예측 입력이 아니다)
  1단계(날씨 없이, 당일 저녁): 일합계 1 kWh 미만, 또는 5 kWh 미만이 이틀 연속이면 '정지'
  2단계(다음 날 11시 이후, 광양 ASOS 관측으로 기대 발전량 e 를 계산한 뒤):
      e 가 30 kWh 이상인데 실제가 e 의 30% 미만이면 '정지'
      e 가 80 kWh 이상인데 실제가 e 의 60% 미만이면 '출력 저하'
      e 가 80 kWh 미만이고 위에 해당하지 않으면 '판정 보류'(어두운 날)
기대 발전량 e 는 ASOS 묶음이 2013~2014 로 맞춘 식의 값(hadong_daily_full.csv 의 pi_expected_kwh)이다.
정답표는 보완 조사 3 의 달력(A 40, B 10, C 14)이고 이웃 발전소 자료로 만든 사후 표다. 임계값은 전체 기간을 보고 정한 것이라 아래 성적은 표본 안 값이다.
"""
import numpy as np, pandas as pd
from t2_common import *
pd.set_option("display.width", 250); pd.set_option("display.max_rows", 200)
df, H = load_raw(); a = load_asos().reindex(df.index); nb, nbH = load_neighbors(df.index)
T = pd.read_pickle(SOLAR / "ev" / "a3_table.pkl")
c1 = T.category.str.split("_").str[0]; isA, isB, isC = c1 == "A", c1 == "B", c1 == "C"; soft = c1.isin(["C2", "D", "E"]); truth = isA | isB | isC
y, e = df.y, a.pi_expected_kwh
s1 = (y < 1) | ((y < 5) & (y.shift(1) < 5))
s2 = (e >= 30) & (y < 0.3 * e)
stop = s1 | s2
low = (e >= 80) & (y < 0.6 * e) & ~stop
hold = (~stop) & (~low) & (e.isna() | (e < 80))
flag = stop | low
state = pd.Series("정상", index=df.index); state[hold] = "판정 보류"; state[low] = "출력 저하"; state[stop] = "정지"
# 표시 유지: 출력 저하나 정지가 켜진 뒤 '정상' 판정이 나올 때까지 보류일도 켜진 것으로 본다
lat, on = [], False
for d in df.index:
    if state[d] in ("정지", "출력 저하"): on = True
    elif state[d] == "정상": on = False
    lat.append(on)
latch = pd.Series(lat, index=df.index)

def events(mask):
    ds = list(df.index[truth & mask]); g = []
    for d in ds:
        if g and (d - g[-1][-1]).days <= 3: g[-1].append(d)
        else: g.append([d])
    return g
def score(f, mask, label):
    f = f & mask; yrs = mask.sum() / 365.25; fp = f & ~truth & ~soft; ev = events(mask)
    return dict(규칙=label, A=f"{int((f & isA).sum())}/{int((isA & mask).sum())}", B=f"{int((f & isB).sum())}/{int((isB & mask).sum())}", C=f"{int((f & isC).sum())}/{int((isC & mask).sum())}",
                사건=f"{sum(any(f[d] for d in g) for g in ev)}/{len(ev)}", 첫날감지=sum(1 for g in ev if f[g[0]]), 오탐일=int(fp.sum()), 연오탐=round(fp.sum() / yrs, 1), 켜진날=int(f.sum()))
P = {"가 2013-01-01~2025-12-31": pd.Series(df.index <= "2025-12-31", index=df.index), "나 2015-07-18~2025-12-31": pd.Series((df.index >= "2015-07-18") & (df.index <= "2025-12-31"), index=df.index),
     "다 시험 구간 2023-05-30~2025-12-30": pd.Series((df.index >= "2023-05-30") & (df.index <= "2025-12-30"), index=df.index)}
rows = []
for pn, m in P.items():
    for nm, f in [("1단계만(실적만)", s1), ("1+2단계 정지", stop), ("추천 규칙(정지 + 출력 저하)", flag), ("추천 규칙 + 표시 유지", latch)]:
        r = score(f, m, nm); r["기간"] = pn; rows.append(r)
t = pd.DataFrame(rows)[["기간", "규칙", "A", "B", "C", "사건", "첫날감지", "오탐일", "연오탐", "켜진날"]]
print(t.to_string(index=False)); t.to_csv(HERE / "s7_recommended_rule_score.csv", index=False, encoding="utf-8-sig")
m = P["가 2013-01-01~2025-12-31"]
print("\n판정 분포(2013-01-01~2025-12-31, %d일):" % m.sum(), state[m].value_counts().to_dict(), "| 판정 보류 비율 %.1f%%" % (100 * (state[m] == "판정 보류").mean()))
print("월별 판정 보류 비율(%):", (state[m] == "판정 보류").groupby(df.index[m].month).mean().mul(100).round(0).astype(int).to_dict())
print("\n추천 규칙이 놓친 정답일:", [(str(d.date()), c1[d], round(y[d], 1), None if np.isnan(e[d]) else round(e[d]), None if np.isnan(e[d]) else round(y[d] / e[d], 2), state[d]) for d in df.index[truth & m & ~flag]])
fp = flag & m & ~truth & ~soft
print("추천 규칙의 오탐일 %d일:" % fp.sum())
print(pd.DataFrame({"일합계": y[fp].round(1), "기대": e[fp].round(0), "비": (y / e)[fp].round(2), "판정": state[fp], "이웃3곳q": T.q3[fp].round(2), "광양일사": a.gy_gsr_obs[fp], "위성일사": T.sat[fp]}).to_string())
print("  오탐 월별:", pd.Series(1, index=df.index[fp]).groupby(df.index[fp].month).size().to_dict())
print("\n시험 구간(2023-05-30~2025-12-30)에서 추천 규칙이 켜진 날:")
mm = P["다 시험 구간 2023-05-30~2025-12-30"]
x = pd.DataFrame({"일합계": y[flag & mm].round(1), "기대": e[flag & mm].round(0), "비": (y / e)[flag & mm].round(2), "판정": state[flag & mm], "정답표": c1[flag & mm].replace("", "오탐")})
print(x.to_string())
print("\n2024-07-08~07-22 판정:", " ".join(f"{d.strftime('%m-%d')}:{state[d]}" for d in pd.date_range("2024-07-08", "2024-07-22")))

# ---- (2) 팀이 쓸 설비 이벤트 목록
cal = pd.read_csv(SOLAR / "ev" / "day_table_all.csv", encoding="utf-8-sig", parse_dates=["날짜"]).set_index("날짜")
cat = cal["범주"].fillna("").str.split("_").str[0]
name = {"A": "전면 정지", "B": "부분 정지", "C": "절반 출력", "C2": "절반 출력이 낮에 풀린 날"}
sel = cat.isin(list(name))
out = pd.DataFrame(index=cal.index[sel]); out.index.name = "date"
out["category"] = cat[sel].map(name)
out["gen_kwh"] = df.y.reindex(out.index).round(3)
out["exclude_from_training"] = 1
out["exclude_from_error_stats"] = 1
out["stop_50"] = cat[sel].isin(["A", "B"]).astype(int).values
out["in_asos_stop_day_43"] = a.stop_day.reindex(out.index).astype(int).values
out["in_asos_pi_outage_49"] = a.pi_outage.reindex(out.index).fillna(0).astype(int).values
out["in_D1_40"] = (cat[sel] == "A").astype(int).values
out["in_D2_45"] = cal["정의_D2"].reindex(out.index).astype(int).values
out["in_D3_50"] = cal["정의_D3"].reindex(out.index).astype(int).values
out["expected_kwh_gwangyang"] = e.reindex(out.index).round(1)
out["ratio_to_expected"] = (y / e).reindex(out.index).round(3)
out["rule_state"] = state.reindex(out.index)
out["neighbors_q_median"] = cal["이웃3곳_q중앙값"].reindex(out.index)
out.to_csv(HERE / "equipment_events_final.csv", encoding="utf-8-sig")
print("\n설비 이벤트 목록 저장:", HERE / "equipment_events_final.csv", "|", len(out), "일 |", out.category.value_counts().to_dict(), "| 정지 50일 가운데 ASOS Stop 43 에 든 날", int((out.stop_50 & out.in_asos_stop_day_43).sum()))
print("정지 50일:", fmt(out.index[out.stop_50 == 1]))
print("절반 출력 15일:", fmt(out.index[out.stop_50 == 0]))
print("추천 규칙이 이 65일에 내린 판정:", out.groupby("category").rule_state.value_counts().to_dict())
