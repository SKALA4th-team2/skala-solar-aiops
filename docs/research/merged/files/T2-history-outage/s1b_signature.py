"""s1b: 일곱 정지일 목록에서 서로 다른 날을 '표시한 목록의 조합'별로 묶어 나열하고, 최종 분류(equipment_events_final.csv)와 맞춘다. s1 과 s7 을 먼저 돌려야 한다."""
import pandas as pd
from t2_common import *
M = pd.read_csv(HERE / "s1_stoplist_matrix.csv", encoding="utf-8-sig", parse_dates=["날짜"]).set_index("날짜")
cols = ["0인 날(24)", "D1 정지(40)", "ASOS stop_day(43)", "D2 정지(45)", "ASOS pi_outage(49)", "D3 정지(50)", "D1 따로 다룰 날(63)"]
short = {"0인 날(24)": "0", "D1 정지(40)": "D1-40", "ASOS stop_day(43)": "ASOS-43", "D2 정지(45)": "D2-45", "ASOS pi_outage(49)": "ASOS-49", "D3 정지(50)": "D3-50", "D1 따로 다룰 날(63)": "D1-63"}
M["sig"] = M[cols].apply(lambda r: ", ".join(short[c] for c in cols if r[c] == 1), axis=1)
ev = pd.read_csv(HERE / "equipment_events_final.csv", encoding="utf-8-sig", parse_dates=["date"]).set_index("date")
M["최종"] = ev.category.reindex(M.index).fillna("목록에 넣지 않음")
rows = []
for (s, f), x in M.groupby(["sig", "최종"], sort=False):
    rows.append((len(s.split(", ")), s, f, len(x), fmt(x.index), f"{x['일합계'].min():.2f}~{x['일합계'].max():.2f}", "/".join(sorted(set(x['보완3_범주'])))))
rows.sort(key=lambda r: (-r[0], r[1]))
for r in rows:
    print(f"[{r[0]}곳] {r[1]} | 최종: {r[2]} | {r[3]}일 | {r[4]} | 일합계 {r[5]} kWh | 보완3 범주 {r[6]}")
print("\n합집합", len(M), "| 일곱 곳 모두", int((M[cols].sum(1) == 7).sum()), "| 서로 다른 날", int((M[cols].sum(1) < 7).sum()))
print("최종 목록 65일 가운데 일곱 목록 어디에도 없는 날:", fmt(set(ev.index) - set(M.index)))
print("일곱 목록 합집합 71일 가운데 최종 목록(65일)에 들지 않는 날:", fmt(set(M.index) - set(ev.index)), len(set(M.index) - set(ev.index)))
print("최종 정지 50일 가운데 각 목록이 놓친 날 수:", {short[c]: int(((ev.stop_50 == 1) & (~ev.index.isin(M.index[M[c] == 1]))).sum()) for c in cols})
print("각 목록에서 최종 정지 50일이 아닌 날 수:", {short[c]: int((~M.index[M[c] == 1].isin(ev.index[ev.stop_50 == 1])).sum()) for c in cols})
# 재학습에 쓰는 최근 41행 안의 설비 이벤트일 수(시험 구간)
up = pd.read_csv(ASOS / "hadong_upload.csv", parse_dates=["Date"])
r = up.Date.isin(ev.index).astype(int).rolling(41).sum(); m = up.Date >= "2023-05-30"; rr = r[m]
print("\n시험 구간에서 최근 41행 안의 이벤트일 수 최대:", int(rr.max()), "| 그 기간:", up.Date[rr.idxmax()].date(), "~", up.Date[rr[rr == rr.max()].index[-1]].date(), "| 1행 이상인 날 수:", int((rr > 0).sum()), "/", len(rr))
