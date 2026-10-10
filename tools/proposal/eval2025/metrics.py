"""2025년 시간별 예측으로 발전소별 지표를 계산한다. 제도 기준은 팀 저장소 결정 0015 와 같은 규칙이다.

평가 대상 시간 = 실적 ÷ 설비 용량 이 10% 이상인 시간
오차율 = |예측 − 실적| ÷ 설비 용량 × 100
4% 이하 4원/kWh, 4% 초과 6% 이하 3원/kWh, 그 밖 0원
"""
import json
from pathlib import Path
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[3]
EVID = ROOT / "docs/proposal/evidence/eval2025-recompute-20261008"
ev = {p["id"]: p for p in json.loads((EVID / "plants.json").read_text())}


def scheme(actual, pred, cap):
    util = actual / cap
    el = util >= 0.10
    err = np.abs(pred - actual) / cap * 100
    e = err[el]
    rate = np.where(e <= 4, 4, np.where(e <= 6, 3, 0))
    return dict(eligible=int(el.sum()), mean_err=float(e.mean()), le4=float((e <= 4).mean() * 100),
                le6=float((e <= 6).mean() * 100), krw_per_kwh=float((actual[el] * rate).sum() / actual[el].sum()))


rows, frames = [], {}
for pid, p in ev.items():
    d = pd.read_csv(HERE / "out" / f"{pid}.csv")
    a, cap = d.actual_kwh.to_numpy(), p["cap"]
    frames[pid] = d.set_index("timestamp")
    r = dict(id=pid, name=p["name"], region=p["region"], cap=cap, ok=p["ok"], hours=len(d),
             cf=float(a.mean() / cap * 100), peak=float(a.max() / cap * 100), p99=float(np.quantile(a, 0.99) / cap * 100))
    for key, col in (("lstm", "predicted_kwh"), ("lag", "lag24_kwh"), ("ref", "reference_kwh")):
        q = d[col].to_numpy()
        s = scheme(a, q, cap)
        r.update({f"{key}_{k}": v for k, v in s.items()})
        r[f"{key}_wape"] = float(np.abs(q - a).sum() / a.sum() * 100)
        r[f"{key}_rmse"] = float(np.sqrt(np.mean((q - a) ** 2)))
        day = d.radiation.to_numpy() >= 20
        r[f"{key}_day_mae_cap"] = float(np.abs(q - a)[day].mean() / cap * 100)
    r["skill_lag"] = (1 - r["lstm_rmse"] / r["lag_rmse"]) * 100
    r["skill_ref"] = (1 - r["lstm_rmse"] / r["ref_rmse"]) * 100
    rows.append(r)
t = pd.DataFrame(rows)
t.to_json(EVID / "metrics.json", orient="records", force_ascii=False, indent=1)
ok = t[t.ok]

pd.set_option("display.width", 250); pd.set_option("display.max_rows", 50); pd.set_option("display.float_format", lambda v: f"{v:.2f}")
print(t.sort_values("cf")[["name", "region", "cap", "ok", "cf", "peak", "p99", "lstm_eligible", "lstm_mean_err", "lstm_le4", "lstm_le6", "lag_le6", "ref_le6", "lstm_wape", "lag_wape", "ref_wape", "skill_lag"]].to_string(index=False))


def summ(col):
    v = ok[col]
    return f"최소 {v.min():.2f} · 가운데 {v.median():.2f} · 최대 {v.max():.2f}"


print("\n── 통과 31곳의 요약")
for c in ["cf", "peak", "lstm_eligible", "lstm_mean_err", "lag_mean_err", "ref_mean_err", "lstm_le4", "lag_le4", "ref_le4",
          "lstm_le6", "lag_le6", "ref_le6", "lstm_krw_per_kwh", "lag_krw_per_kwh", "ref_krw_per_kwh", "lstm_wape", "lag_wape", "ref_wape", "skill_lag", "skill_ref"]:
    print(f"{c:<18}", summ(c))
print("LSTM 의 6% 이하 비율이 전날 유지보다 높은 곳:", int((ok.lstm_le6 > ok.lag_le6).sum()), "/ 일사량 기준선보다 높은 곳:", int((ok.lstm_le6 > ok.ref_le6).sum()))
print("LSTM 의 WAPE 가 전날 유지보다 낮은 곳:", int((ok.lstm_wape < ok.lag_wape).sum()), "/ 일사량 기준선보다 낮은 곳:", int((ok.lstm_wape < ok.ref_wape).sum()))

# 31곳을 한데 모은 시간 전체(풀링)
A = np.concatenate([frames[i].actual_kwh.to_numpy() / ev[i]["cap"] for i in ok.id])
for key, col in (("LSTM", "predicted_kwh"), ("전날 유지", "lag24_kwh"), ("일사량 기준선", "reference_kwh")):
    Q = np.concatenate([frames[i][col].to_numpy() / ev[i]["cap"] for i in ok.id])
    s = scheme(A, Q, 1.0)
    print(f"풀링 {key}: 평가 대상 {s['eligible']:,}시간 · 평균 오차율 {s['mean_err']:.2f}% · 4% 이하 {s['le4']:.1f}% · 6% 이하 {s['le6']:.1f}%")

# 31곳의 합계(가상 묶음): 공통 시간만
common = None
for i in ok.id:
    idx = frames[i].index
    common = idx if common is None else common.intersection(idx)
capsum = float(ok.cap.sum())
SA = sum(frames[i].loc[common].actual_kwh.to_numpy() for i in ok.id)
print(f"\n── 31곳 합계 · 공통 {len(common):,}시간 · 설비 용량 합계 {capsum:,.3f}kW")
for key, col in (("LSTM", "predicted_kwh"), ("전날 유지", "lag24_kwh"), ("일사량 기준선", "reference_kwh")):
    SQ = sum(frames[i].loc[common][col].to_numpy() for i in ok.id)
    s = scheme(SA, SQ, capsum)
    rm = float(np.sqrt(np.mean((SQ - SA) ** 2)))
    print(f"합계 {key}: RMSE {rm:,.2f} · 평가 대상 {s['eligible']:,}시간 · 평균 오차율 {s['mean_err']:.2f}% · 4% 이하 {s['le4']:.1f}% · 6% 이하 {s['le6']:.1f}% · 모의 단가 {s['krw_per_kwh']:.2f}원/kWh · WAPE {np.abs(SQ-SA).sum()/SA.sum()*100:.2f}%")
json.dump(dict(common_hours=int(len(common)), capsum=capsum), open(EVID / "portfolio.json", "w"))
