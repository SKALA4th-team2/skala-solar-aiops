"""s1: 정지일 목록을 날짜 단위로 대조한다.

목록(일수): 정확히 0(24), 1 미만(39), D1 사실상 정지 포함(40), ASOS stop_day(43), D2 정지 구간(45), 5 미만(45),
ASOS pi_outage(49), D3 정지 구간(50), 보완 조사 A+B(50), D1 따로 다룰 날(63), 1b(64), ASOS pi_partial_suspect(68).
원자료에서 다시 만들 수 있는 것은 여기서 다시 만들고, 각 조사의 파일에 든 표시와 맞는지 확인한다.
"""
import numpy as np, pandas as pd
from t2_common import *

pd.set_option("display.width", 250); pd.set_option("display.max_rows", 400); pd.set_option("display.max_columns", 60)
df, H = load_raw()
nb, nbH = load_neighbors(df.index)
a = load_asos()
w = load_weather(df.index)
idx = df.index
assert len(df) == 4807 and np.allclose(df.y, df.sum24, atol=1e-6)
assert np.allclose(a.gen_kwh.reindex(idx), df.y, atol=1e-3)

L = {}
L["0인 날(24)"] = idx[df.y == 0]
L["1 미만(39)"] = idx[df.y < 1]
L["5 미만(45)"] = idx[df.y < 5]
# D1: 정확히 0 인 24일 + 사실상 정지 16일(2015-04-23~05-05, 2018-07-04·07·12)
L["D1 정지(40)"] = dates([("2016-12-22", "2016-12-26"), ("2018-07-13", "2018-07-31"), ("2015-04-23", "2015-05-05"), "2018-07-04", "2018-07-07", "2018-07-12"])
# D1: 따로 다뤄야 할 날 63일 = 위 40 + 낮 0 이 2개 이상 19일 + 수기 입력 3일 + 복사 1일 (D1 요약본 4절에 적힌 날짜)
d1_gap = ["2014-07-18", "2014-08-25", "2015-05-13", "2016-09-17", "2016-12-27", "2017-08-14", "2017-10-10", "2018-06-13", "2018-07-05", "2018-07-11",
          "2018-08-01", "2019-06-29", "2020-09-07", "2020-09-08", "2020-09-09", "2022-09-05", "2022-09-06", "2023-08-10", "2024-03-22"]
L["D1 따로 다룰 날(63)"] = L["D1 정지(40)"].union(dates(d1_gap + [("2016-02-24", "2016-02-26"), "2016-12-28"]))
# D2: d2r/common.py OUTAGE_RANGES
L["D2 정지(45)"] = dates([("2015-04-23", "2015-05-06"), ("2016-12-22", "2016-12-27"), "2018-07-04", "2018-07-07", ("2018-07-11", "2018-08-01"), "2020-09-08"])
# D3: d3_retry/common.py OUTAGE
L["D3 정지(50)"] = dates([("2015-04-23", "2015-05-06"), ("2016-12-22", "2016-12-27"), ("2018-07-04", "2018-08-01"), "2020-09-08"])
# ASOS 파일의 표시
for c, nm in [("zero_gen", "ASOS zero_gen(24)"), ("near_zero_stop", "ASOS near_zero_stop(19)"), ("stop_day", "ASOS stop_day(43)"),
              ("pi_outage", "ASOS pi_outage(49)"), ("pi_partial_suspect", "ASOS pi_partial_suspect(68)")]:
    L[nm] = a.index[a[c].fillna(0).astype(int) == 1]
# 보완 조사 3 의 달력(이웃 3곳 대비로 만든 사후 정답표)
cal = pd.read_csv(SOLAR / "ev" / "day_table_all.csv", encoding="utf-8-sig", parse_dates=["날짜"]).set_index("날짜")
cat = cal["범주"].fillna("").str.split("_").str[0]
for k, nm in [("A", "보완3 A 전면 정지(40)"), ("B", "보완3 B 부분 정지(10)"), ("C", "보완3 C 절반 출력(14)"), ("C2", "보완3 C2 풀린 날(1)"), ("D", "보완3 D 짧은 끊김(8)"),
              ("E", "보완3 E 지역 공통(1)"), ("F", "보완3 F 기록 이상(4)"), ("W", "보완3 W 이웃도 같음(12)")]:
    L[nm] = cal.index[cat == k]
L["보완3 A+B(50)"] = L["보완3 A 전면 정지(40)"].union(L["보완3 B 부분 정지(10)"])
L["1b(64)"] = cal.index[(cal["정의_1b_72%미만"] == 1) | (cal["정의_1b_절반출력"] == 1)]
L["day_table 정의_D1"] = cal.index[cal["정의_D1"] == 1]
L["day_table 정의_D2"] = cal.index[cal["정의_D2"] == 1]
L["day_table 정의_D3"] = cal.index[cal["정의_D3"] == 1]

print("== 1. 목록별 일수")
for k, v in L.items():
    print(f"  {k:32s} {len(v):3d}일")
print("\n== 2. 내가 다시 만든 목록과 각 조사 파일의 표시가 같은가")
for mine, theirs in [("D1 따로 다룰 날(63)", "day_table 정의_D1"), ("D2 정지(45)", "day_table 정의_D2"), ("D3 정지(50)", "day_table 정의_D3"), ("0인 날(24)", "ASOS zero_gen(24)")]:
    print(f"  {mine} == {theirs}: {set(L[mine]) == set(L[theirs])}")
print("  D1 정지(40) == 보완3 A 전면 정지(40):", set(L["D1 정지(40)"]) == set(L["보완3 A 전면 정지(40)"]))
print("  1 미만(39) ⊂ D1 정지(40):", set(L["1 미만(39)"]) <= set(L["D1 정지(40)"]), "| 40 에만 있는 날:", fmt(set(L["D1 정지(40)"]) - set(L["1 미만(39)"])))
# ASOS near_zero 규칙을 파일의 광양·진주 일사량 없이 재현할 수는 없으므로(진주 값이 파일에 없음) 일수와 날짜만 본다
print("  ASOS near_zero_stop 19일:", fmt(L["ASOS near_zero_stop(19)"]))

print("\n== 3. 과제에 적힌 일곱 목록(24, 40, 43, 45, 49, 50, 63)의 포함 관계")
seven = ["0인 날(24)", "D1 정지(40)", "ASOS stop_day(43)", "D2 정지(45)", "ASOS pi_outage(49)", "D3 정지(50)", "D1 따로 다룰 날(63)"]
for i, p in enumerate(seven):
    for q in seven[i + 1:]:
        A, B = set(L[p]), set(L[q])
        print(f"  [{p}] 대 [{q}]: 겹침 {len(A & B)} | 앞에만 {len(A - B)}: {fmt(A - B)} | 뒤에만 {len(B - A)}: {fmt(B - A)}")
print("  [5 미만(45)] 대 [D2 정지(45)]: 일수는 같지만 다른 목록. 5 미만에만:", fmt(set(L["5 미만(45)"]) - set(L["D2 정지(45)"])), "| D2 에만:", fmt(set(L["D2 정지(45)"]) - set(L["5 미만(45)"])))
print("  [D3 정지(50)] 대 [보완3 A+B(50)]: 일수는 같지만 다른 목록. D3 에만:", fmt(set(L["D3 정지(50)"]) - set(L["보완3 A+B(50)"])), "| A+B 에만:", fmt(set(L["보완3 A+B(50)"]) - set(L["D3 정지(50)"])))

print("\n== 4. 일곱 목록 가운데 한 곳 이상이 표시한 날 전체(날짜 × 목록). 1 = 표시")
U = sorted(set().union(*[set(L[k]) for k in seven]))
M = pd.DataFrame({k.split("(")[0] + k[k.index("("):]: [int(d in set(L[k])) for d in U] for k in seven}, index=pd.DatetimeIndex(U))
M["표시한_목록수"] = M.sum(axis=1)
M.insert(0, "일합계", df.y.reindex(M.index).round(2))
# 이웃 대비: 그날 이 발전소 일합계 / 이웃 일합계 를, 직전 60일(그날 제외, 두 곳 모두 5 kWh 이상인 날) 비율 중앙값으로 나눈 값
def qratio(nm):
    r = (df.y / nb[nm]).where((nb[nm] >= 20))
    base = r.where(df.y >= 5).shift(1).rolling(60, min_periods=15).median()
    return (r / base)
for nm in ["health", "subst", "stadium"]:
    M[NBK[nm] + "_일합계"] = nb[nm].reindex(M.index).round(1)
    M[NBK[nm] + "대비_q"] = qratio(nm).reindex(M.index).round(2)
M["광양기대대비"] = (a.gen_kwh / a.pi_expected_kwh).reindex(M.index).round(2)
M["기대_kWh"] = a.pi_expected_kwh.reindex(M.index).round(0)
M["낮0_열수(9~17)"] = [(H[idx.get_loc(d), 8:17] == 0).sum() for d in M.index]
M["보완3_범주"] = cat.reindex(M.index).replace("", "-")
M.index.name = "날짜"
M.to_csv(HERE / "s1_stoplist_matrix.csv", encoding="utf-8-sig")
print(f"  합집합 {len(M)}일, 일곱 목록 모두 표시한 날 {int((M['표시한_목록수'] == 7).sum())}일, 서로 다른 날 {int((M['표시한_목록수'] < 7).sum())}일")
print(M[M["표시한_목록수"] < 7].to_string())

print("\n== 5. 일곱 목록이 모두 표시한 날")
print("  ", fmt(M.index[M["표시한_목록수"] == 7]))

print("\n== 6. ASOS stop_day(43)와 보완3 A+B(50)의 차이 7일, D3(50)와 A+B(50)의 차이: 시간값과 이웃")
def show(d):
    i = idx.get_loc(pd.Timestamp(d))
    hv = " ".join(f"{h+1}:{H[i, h]:.1f}" for h in range(6, 19))
    nbs = " ".join(f"{NBK[k]} {nb[k].iloc[i]:.0f}" for k in ["health", "subst", "stadium"])
    return f"  {d} 일합계 {df.y.iloc[i]:7.2f} | 열 7~19: {hv} | {nbs} | 광양 기대 {a.pi_expected_kwh.iloc[i]:.0f} 범주 {cat.iloc[i] or '-'}"
for d in ["2015-05-06", "2017-10-10", "2018-06-13", "2018-07-05", "2018-08-01", "2020-09-09", "2024-03-22"]:
    print(show(d))
print("  -- D3(50)에만 있고 A+B(50)에 없는 날")
for d in sorted(set(L["D3 정지(50)"]) - set(L["보완3 A+B(50)"])):
    print(show(str(d.date())))
print("  -- pi_outage(49)에만 있고 A+B(50)에 없는 날 / A+B 에만 있는 날")
for d in sorted(set(L["ASOS pi_outage(49)"]) - set(L["보완3 A+B(50)"])):
    print(show(str(d.date())))
for d in sorted(set(L["보완3 A+B(50)"]) - set(L["ASOS pi_outage(49)"])):
    print(show(str(d.date())))

print("\n== 7. 절반 출력 14일 + 풀린 날 1일: 각 목록이 표시했는가")
C = L["보완3 C 절반 출력(14)"].union(L["보완3 C2 풀린 날(1)"])
tab = pd.DataFrame({"일합계": df.y.reindex(C).round(1), "변전소대비_q": qratio("subst").reindex(C).round(2), "광양기대대비": (a.gen_kwh / a.pi_expected_kwh).reindex(C).round(2),
                    "기대_kWh": a.pi_expected_kwh.reindex(C).round(0), "stop_day": a.stop_day.reindex(C), "pi_outage": a.pi_outage.reindex(C), "pi_partial_suspect": a.pi_partial_suspect.reindex(C),
                    "D1(63)": [int(d in set(L["D1 따로 다룰 날(63)"])) for d in C], "D2": [int(d in set(L["D2 정지(45)"])) for d in C], "D3": [int(d in set(L["D3 정지(50)"])) for d in C]})
print(tab.to_string())
print("  ASOS pi_partial_suspect 68일:", fmt(L["ASOS pi_partial_suspect(68)"]))

print("\n== 8. 용량 확인: 시간값이 50 을 넘는 시간 수와 최댓값")
print("  50 초과 시간 수", int((H > 50).sum()), "| 54 초과", int((H > 54).sum()), "| 55 초과", int((H > 55).sum()), "| 최대", H.max(), "날짜", idx[np.unravel_index(H.argmax(), H.shape)[0]].date(), "열", np.unravel_index(H.argmax(), H.shape)[1] + 1)
