"""달별 지표와, 모으면 오차가 지워지는 정도를 계산해 monthly.json 과 cancel.json 에 둔다.

candidates.py 의 2번과 5번 계산과 같은 식이다. 2025년 독립 평가의 시간별 예측(out/*.csv)만 쓴다.
"""
import json
from pathlib import Path
import numpy as np
import pandas as pd

H = Path(__file__).resolve().parent
EVID = H.parents[2] / "docs/proposal/evidence/eval2025-recompute-20261008"
t = pd.read_json(EVID / "metrics.json"); ok = t[t.ok].copy()
ev = {p["id"]: p for p in json.loads((EVID / "plants.json").read_text())}
F = {i: pd.read_csv(H / "out" / f"{i}.csv").set_index("timestamp") for i in ok.id}
ids = list(ok.id)


def sch(a, q, cap):
    el = a / cap >= .10; e = np.abs(q - a)[el] / cap * 100
    return dict(h=int(el.sum()), mean=float(e.mean()), le6=float((e <= 6).mean() * 100))


common = None
for i in ids: common = F[i].index if common is None else common.intersection(F[i].index)
cap = float(ok.cap.sum())
SA = sum(F[i].loc[common].actual_kwh.to_numpy() for i in ids)
SQ = {k: sum(F[i].loc[common][c].to_numpy() for i in ids) for k, c in (("lstm", "predicted_kwh"), ("lag", "lag24_kwh"))}
mon = pd.to_datetime(pd.Index(common).str.slice(0, 19)).month
rows = []
for m in range(1, 13):
    k = mon == m; a, b = sch(SA[k], SQ["lstm"][k], cap), sch(SA[k], SQ["lag"][k], cap)
    rows.append(dict(month=m, hours=a["h"], lstm_mean=a["mean"], lstm_le6=a["le6"], lag_mean=b["mean"], lag_le6=b["le6"]))
json.dump(rows, open(EVID / "monthly.json", "w"), ensure_ascii=False)

E = np.vstack([(F[i].loc[common].predicted_kwh.to_numpy() - F[i].loc[common].actual_kwh.to_numpy()) for i in ids])
el = SA / cap >= .10
net, gross = np.abs(E.sum(0))[el], np.abs(E).sum(0)[el]
En = E / np.array([ev[i]["cap"] for i in ids])[:, None]; Cm = np.corrcoef(En[:, el])
rg = [("jeju" if ev[i]["region"].startswith("jeju") else ev[i]["region"]) for i in ids]
same = [Cm[a, b] for a in range(len(ids)) for b in range(a + 1, len(ids)) if rg[a] == rg[b]]
diff = [Cm[a, b] for a in range(len(ids)) for b in range(a + 1, len(ids)) if rg[a] != rg[b]]
json.dump(dict(cancel_pct=float(100 - net.sum() / gross.sum() * 100), corr_same=float(np.mean(same)), corr_diff=float(np.mean(diff)),
               pairs_same=len(same), pairs_diff=len(diff)), open(EVID / "cancel.json", "w"))
print("monthly.json, cancel.json 을 다시 썼다")
