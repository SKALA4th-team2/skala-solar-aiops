"""임원 발표 구성안에 쓸 후보 수치. 2025년 독립 평가의 시간별 예측(out/*.csv)만 쓴다. 덱은 건드리지 않는다."""
import json
from pathlib import Path
import numpy as np
import pandas as pd

H = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[3]
EVID = ROOT / "docs/proposal/evidence/eval2025-recompute-20261008"
t = pd.read_json(EVID / "metrics.json"); ok = t[t.ok].copy()
ev = {p["id"]: p for p in json.loads((EVID / "plants.json").read_text())}
F = {i: pd.read_csv(H / "out" / f"{i}.csv").set_index("timestamp") for i in ok.id}
COLS = (("LSTM", "predicted_kwh"), ("전날 유지", "lag24_kwh"), ("일사량 기준선", "reference_kwh"))


def sch(a, q, cap):
    el = a / cap >= .10; e = np.abs(q - a)[el] / cap * 100; rate = np.where(e <= 4, 4, np.where(e <= 6, 3, 0))
    en = a[el]
    return dict(h=int(el.sum()), mean=e.mean(), b4=(e <= 4).mean() * 100, b46=((e > 4) & (e <= 6)).mean() * 100, b6=(e > 6).mean() * 100,
                le6=(e <= 6).mean() * 100, krw=(en * rate).sum(), kwh=en.sum(), unit=(en * rate).sum() / en.sum())


print("══ 1. 구간별 시간의 비율과 모의 단가 (계수 1.0, 2025년)")
tot = {k: dict(krw=0.0, kwh=0.0) for k, _ in COLS}
A = np.concatenate([F[i].actual_kwh.to_numpy() / ev[i]["cap"] for i in ok.id])
for k, c in COLS:
    Q = np.concatenate([F[i][c].to_numpy() / ev[i]["cap"] for i in ok.id]); s = sch(A, Q, 1.0)
    krw = sum(sch(F[i].actual_kwh.to_numpy(), F[i][c].to_numpy(), ev[i]["cap"])["krw"] for i in ok.id)
    kwh = sum(sch(F[i].actual_kwh.to_numpy(), F[i][c].to_numpy(), ev[i]["cap"])["kwh"] for i in ok.id)
    print(f"발전소별로 따질 때 {k}: 4%이하 {s['b4']:.1f} · 4~6% {s['b46']:.1f} · 6%초과 {s['b6']:.1f} | 모의 금액 {krw/1e4:,.0f}만원 · 대상 발전량 {kwh/1e6:.2f}GWh · 모의 단가 {krw/kwh:.2f}원/kWh")
common = None
for i in ok.id: common = F[i].index if common is None else common.intersection(F[i].index)
cap = float(ok.cap.sum()); SA = sum(F[i].loc[common].actual_kwh.to_numpy() for i in ok.id)
SUM = {}
for k, c in COLS:
    SQ = sum(F[i].loc[common][c].to_numpy() for i in ok.id); SUM[k] = SQ; s = sch(SA, SQ, cap)
    print(f"31곳 합계로 따질 때 {k}: 4%이하 {s['b4']:.1f} · 4~6% {s['b46']:.1f} · 6%초과 {s['b6']:.1f} | 모의 금액 {s['krw']/1e4:,.0f}만원 · 대상 발전량 {s['kwh']/1e6:.2f}GWh · 모의 단가 {s['unit']:.2f}원/kWh · 상한(모두 4원) {s['kwh']*4/1e4:,.0f}만원")

print("\n══ 2. 달별 (31곳 합계, 2025년): 평가 대상 시간 · 평균 오차율 · 6% 이하 비율")
idx = pd.to_datetime(pd.Index(common).str.slice(0, 19)); mon = idx.month
for m in range(1, 13):
    k = mon == m
    r = {n: sch(SA[k], SUM[n][k], cap) for n, _ in COLS}
    print(f"{m:>2}월 대상 {r['LSTM']['h']:>3}h | LSTM {r['LSTM']['mean']:.2f}% · {r['LSTM']['le6']:.1f}% | 전날 유지 {r['전날 유지']['mean']:.2f}% · {r['전날 유지']['le6']:.1f}% | 일사량 {r['일사량 기준선']['mean']:.2f}% · {r['일사량 기준선']['le6']:.1f}% | 차이(LSTM−전날) {r['LSTM']['le6']-r['전날 유지']['le6']:+.1f}p")
for name, ms in (("1분기", (1, 2, 3)), ("2분기", (4, 5, 6)), ("3분기", (7, 8, 9)), ("4분기", (10, 11, 12))):
    k = np.isin(mon, ms); r = {n: sch(SA[k], SUM[n][k], cap) for n, _ in COLS}
    print(f"{name} 대상 {r['LSTM']['h']}h | LSTM {r['LSTM']['mean']:.2f}% · {r['LSTM']['le6']:.1f}% | 전날 유지 {r['전날 유지']['mean']:.2f}% · {r['전날 유지']['le6']:.1f}%")

print("\n══ 3. 발전소별 후보 (영월본부는 용량 표기 문제로 따로 본다)")
o2 = ok[ok.name != "영월본부"].copy(); o2["d6"] = o2.lstm_le6 - o2.lag_le6; o2["dm"] = (1 - o2.lstm_mean_err / o2.lag_mean_err) * 100
pd.set_option("display.width", 220); pd.set_option("display.float_format", lambda v: f"{v:.2f}")
cols = ["name", "region", "cap", "lstm_eligible", "lstm_mean_err", "lag_mean_err", "lstm_le6", "lag_le6", "d6", "dm", "lstm_krw_per_kwh", "lag_krw_per_kwh"]
print("6% 이하 비율이 높은 5곳\n", o2.sort_values("lstm_le6", ascending=False)[cols].head(5).to_string(index=False))
print("전날 유지보다 6% 이하 비율이 가장 많이 오른 5곳\n", o2.sort_values("d6", ascending=False)[cols].head(5).to_string(index=False))
print("평균 오차율이 전날 유지보다 가장 많이 내려간 5곳(%)\n", o2.sort_values("dm", ascending=False)[cols].head(5).to_string(index=False))
print("31곳의 범위: 평균 오차율", round(ok.lstm_mean_err.min(), 2), "~", round(ok.lstm_mean_err.max(), 2), "· 6% 이하", round(ok.lstm_le6.min(), 1), "~", round(ok.lstm_le6.max(), 1), "· 가운데", round(ok.lstm_mean_err.median(), 2), round(ok.lstm_le6.median(), 1))
print("영월본부를 뺀 30곳의 범위: 평균 오차율", round(o2.lstm_mean_err.min(), 2), "~", round(o2.lstm_mean_err.max(), 2), "· 6% 이하", round(o2.lstm_le6.min(), 1), "~", round(o2.lstm_le6.max(), 1))

print("\n══ 4. 묶음 후보")
def bundle(ids, label):
    cm = None
    for i in ids: cm = F[i].index if cm is None else cm.intersection(F[i].index)
    c = sum(ev[i]["cap"] for i in ids); a = sum(F[i].loc[cm].actual_kwh.to_numpy() for i in ids)
    r = {n: sch(a, sum(F[i].loc[cm][col].to_numpy() for i in ids), c) for n, col in COLS}
    print(f"{label}: {len(ids)}곳 · {c/1000:.2f}MW · 대상 {r['LSTM']['h']:,}h | LSTM {r['LSTM']['mean']:.2f}% · 6%이하 {r['LSTM']['le6']:.1f}% · 4%이하 {r['LSTM']['b4']:.1f}% | 전날 유지 {r['전날 유지']['mean']:.2f}% · {r['전날 유지']['le6']:.1f}% | 일사량 {r['일사량 기준선']['mean']:.2f}% · {r['일사량 기준선']['le6']:.1f}%")
ids = list(ok.id); reg = lambda i: ev[i]["region"]
bundle(ids, "31곳"); bundle([i for i in ids if not reg(i).startswith("jeju")], "육지 26곳")
bundle([i for i in ids if reg(i) == "hadong"], "하동 10곳"); bundle([i for i in ids if ev[i]["name"] == "하동본부"], "하동본부 5호기")
bundle([i for i in ids if reg(i) == "incheon"], "인천 5곳"); bundle([i for i in ids if reg(i) == "samcheok"], "삼척소내 3호기"); bundle([i for i in ids if reg(i).startswith("jeju")], "제주 5곳")

print("\n══ 5. 묶으면 왜 합계의 오차율이 낮아지는가: 관측")
E = np.vstack([(F[i].loc[common].predicted_kwh.to_numpy() - F[i].loc[common].actual_kwh.to_numpy()) for i in ids])
el = SA / cap >= .10
net, gross = np.abs(E.sum(0))[el], np.abs(E).sum(0)[el]
print(f"평가 대상 {int(el.sum()):,}시간에서: 발전소별 오차 크기의 합 {gross.sum()/1e6:.3f}GWh → 합계의 오차 크기 {net.sum()/1e6:.3f}GWh = {net.sum()/gross.sum()*100:.1f}% (나머지 {100-net.sum()/gross.sum()*100:.1f}% 가 서로 지워짐)")
over = (E[:, el] > 0).mean(0)
print(f"같은 시간에 과대 예측한 발전소의 비율: 가운데 {np.median(over)*100:.0f}% · 모두 한 방향(0% 또는 100%)인 시간 {np.mean((over==0)|(over==1))*100:.1f}%")
En = E / np.array([ev[i]["cap"] for i in ids])[:, None]; Cm = np.corrcoef(En[:, el])
rg = [("jeju" if reg(i).startswith("jeju") else reg(i)) for i in ids]
same = [Cm[a, b] for a in range(len(ids)) for b in range(a + 1, len(ids)) if rg[a] == rg[b]]
diff = [Cm[a, b] for a in range(len(ids)) for b in range(a + 1, len(ids)) if rg[a] != rg[b]]
print(f"발전소 둘의 시간별 오차의 상관: 같은 지역 {np.mean(same):.2f} ({len(same)}쌍) · 다른 지역 {np.mean(diff):.2f} ({len(diff)}쌍)")
