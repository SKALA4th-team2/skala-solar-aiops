"""발표에 쓸 나머지 수치: 큰 오차의 비율, 묶음별 지표, 분할 일수."""
import json
from pathlib import Path
import numpy as np
import pandas as pd

H = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[3]
EVID = ROOT / "docs/proposal/evidence/eval2025-recompute-20261008"
t = pd.read_json(EVID / "metrics.json"); ok = t[t.ok]
ev = {p["id"]: p for p in json.loads((EVID / "plants.json").read_text())}
F = {i: pd.read_csv(H / "out" / f"{i}.csv").set_index("timestamp") for i in t.id}
print("LSTM 평균 오차율이 전날 유지보다 낮은 곳:", int((ok.lstm_mean_err < ok.lag_mean_err).sum()), "· 일사량 기준선보다 낮은 곳:", int((ok.lstm_mean_err < ok.ref_mean_err).sum()), "/ 31")
print("6% 이하 비율이 전날 유지보다 높지 않은 곳:", ok[ok.lstm_le6 <= ok.lag_le6][["name", "lstm_le6", "lag_le6"]].round(2).values.tolist())
print("4% 이하 비율이 전날 유지보다 높은 곳:", int((ok.lstm_le4 > ok.lag_le4).sum()), "/ 31")
print("평균 오차율 상위 6:", ok.sort_values("lstm_mean_err", ascending=False)[["name", "region", "lstm_mean_err"]].head(6).round(2).values.tolist())
print("WAPE 상위 6:", ok.sort_values("lstm_wape", ascending=False)[["name", "region", "lstm_wape"]].head(6).round(2).values.tolist())
yw = ok[ok.name == "영월본부"].iloc[0]
print("영월본부:", {k: round(float(yw[k]), 2) for k in ["cap", "cf", "peak", "p99", "lstm_eligible", "lstm_mean_err", "lstm_le6", "lstm_wape", "lag_wape", "skill_lag"]})
print("WAPE 가 영월본부보다 큰 곳:", int((ok.lstm_wape > yw.lstm_wape).sum()), "/ 31 · 전날 유지 대비 개선이 영월본부보다 작은 곳:", int((ok.skill_lag < yw.skill_lag).sum()))
print("최대 출력 ÷ 용량 이 낮은 곳:", t.sort_values("peak")[["name", "cap", "peak", "cf"]].head(4).round(2).values.tolist())
out = {}
A = np.concatenate([F[i].actual_kwh.to_numpy() / ev[i]["cap"] for i in ok.id]); el = A >= .10
for key, col in (("lstm", "predicted_kwh"), ("lag", "lag24_kwh"), ("ref", "reference_kwh")):
    Q = np.concatenate([F[i][col].to_numpy() / ev[i]["cap"] for i in ok.id]); e = np.abs(Q - A)[el] * 100
    out[key] = dict(mean=float(e.mean()), median=float(np.median(e)), le4=float(np.mean(e <= 4) * 100), le6=float(np.mean(e <= 6) * 100),
                    gt10=float(np.mean(e > 10) * 100), gt20=float(np.mean(e > 20) * 100), gt30=float(np.mean(e > 30) * 100))
    print("풀링", key, {k: round(v, 2) for k, v in out[key].items()})
out["eligible"] = int(el.sum()); out["hours"] = int(len(A))


def bundle(ids, label):
    common = None
    for i in ids:
        common = F[i].index if common is None else common.intersection(F[i].index)
    cap = sum(ev[i]["cap"] for i in ids)
    SA = sum(F[i].loc[common].actual_kwh.to_numpy() for i in ids); e_l = SA / cap >= .10
    r = dict(n=len(ids), cap=cap, hours=int(len(common)), eligible=int(e_l.sum()))
    for key, col in (("lstm", "predicted_kwh"), ("lag", "lag24_kwh"), ("ref", "reference_kwh")):
        SQ = sum(F[i].loc[common][col].to_numpy() for i in ids); e = np.abs(SQ - SA)[e_l] / cap * 100
        r[key] = dict(mean=float(e.mean()), le4=float((e <= 4).mean() * 100), le6=float((e <= 6).mean() * 100),
                      gt10=float((e > 10).mean() * 100), rmse=float(np.sqrt(np.mean((SQ - SA) ** 2))))
    print(f"{label}: {r['n']}곳 · {cap:,.2f}kW · 공통 {r['hours']:,}h · 대상 {r['eligible']:,}h ·", {k: {a: round(b, 2) for a, b in r[k].items()} for k in ("lstm", "lag", "ref")})
    return r


res = dict(pooled=out, all=bundle(list(ok.id), "31곳"),
           land=bundle([i for i in ok.id if not ev[i]["region"].startswith("jeju")], "육지"),
           jeju=bundle([i for i in ok.id if ev[i]["region"].startswith("jeju")], "제주"),
           hadong=bundle([i for i in ok.id if ev[i]["region"] == "hadong"], "하동"))
json.dump(res, open(EVID / "bundles.json", "w"), ensure_ascii=False, indent=1)
s = json.loads((ROOT / "datasets/hourly/screening.json").read_text())["included"]
oks = set(ok.id)
tr = [p["samples"]["train"] for p in s if p["plant_id"] in oks]; va = [p["samples"]["validation"] for p in s if p["plant_id"] in oks]; te = [p["samples"]["test"] for p in s if p["plant_id"] in oks]
print("31곳의 분할 일수: 학습", min(tr), "~", max(tr), "· 검증", min(va), "~", max(va), "· 평가", min(te), "~", max(te), "| 평가 시간 합", sum(te) * 24)
json.dump(dict(train=[min(tr), max(tr)], val=[min(va), max(va)], test=[min(te), max(te)]), open(EVID / "splits.json", "w"))
