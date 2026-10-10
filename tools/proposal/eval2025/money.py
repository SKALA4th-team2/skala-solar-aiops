"""2025년 독립 평가의 시간대별 예측으로 예상 인센티브 정산금을 계산해 money.json 에 둔다. 계수 1.0, 2026.7.25 시행 규칙의 단가."""
import json, pathlib
import numpy as np, pandas as pd
H = pathlib.Path(__file__).resolve().parent
EVID = H.parents[2] / "docs/proposal/evidence/eval2025-recompute-20261008"
t = pd.read_json(EVID / "metrics.json"); ok = t[t.ok].copy()
ev = {p["id"]: p for p in json.loads((EVID / "plants.json").read_text())}
F = {i: pd.read_csv(H / "out" / f"{i}.csv").set_index("timestamp") for i in ok.id}
COLS = (("lstm", "predicted_kwh"), ("lag", "lag24_kwh"), ("ref", "reference_kwh"))

def pay(a, q, cap):
    el = a / cap >= .10; e = np.abs(q - a)[el] / cap * 100
    rate = np.where(e <= 4, 4, np.where(e <= 6, 3, 0)); en = a[el]
    return float((en * rate).sum()), float(en.sum()), int(el.sum())

common = None
for i in ok.id: common = F[i].index if common is None else common.intersection(F[i].index)
cap = float(ok.cap.sum()); SA = sum(F[i].loc[common].actual_kwh.to_numpy() for i in ok.id)
out = {"agg": {}, "plant": {}, "cap_kw": cap, "hours_common": int(len(common))}
for k, c in COLS:
    SQ = sum(F[i].loc[common][c].to_numpy() for i in ok.id)
    krw, kwh, h = pay(SA, SQ, cap)
    out["agg"][k] = krw; out["agg"]["kwh"] = kwh; out["agg"]["hours"] = h; out["agg"]["cap"] = kwh * 4
    out["plant"][k] = sum(pay(F[i].actual_kwh.to_numpy(), F[i][c].to_numpy(), ev[i]["cap"])[0] for i in ok.id)
(EVID / "money.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
print(json.dumps(out, ensure_ascii=False))
