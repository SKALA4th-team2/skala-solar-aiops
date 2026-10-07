"""T4: ASOS 분석이 모의로 추정한 예보 성능(43~62kWh)과 실제 예보로 잰 값을 같은 조건에서 견준다.

ASOS 분석(A2)은 과거 예보가 없어, 대상일의 실제 광양 일사량에 독립 정규 잡음을 더해 '예보'를 흉내 냈다.
여기서는 사전 조사가 받아 둔 실제 예보(Open-Meteo Previous Runs, JMA MSM, 24시간 전·48시간 전)를 같은 모델·같은 날짜에 넣는다.
  (1) 실제 예보가 광양 ASOS 일사량과 얼마나 다른가(rRMSE, 상관). A2 의 잡음 곡선을 그 rRMSE 에서 읽으면 얼마가 나오는가.
  (2) A2 와 같은 가벼운 모델(선형 회귀, 그래디언트 부스팅. 입력 = 발전량 20칸 + 광양 일사량 20칸, 마지막 칸이 대상일)을 A2 와 같은 방법으로 다시 만들어
      먼저 A2 가 저장한 예측과 같은지 확인하고, 마지막 칸에 실제 예보와 같은 크기의 모의 잡음을 각각 넣어 본다.
A2 의 모듈은 import 하지 않고 정의를 옮겨 적었다(asos/a2_rev2/a2_lib.py, 03_noise.py). 새 파일은 이 폴더에만 만든다.
"""
import json
import os
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "1")
import warnings

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import LinearRegression

# macOS 의 numpy 가 matmul 에서 내는 가짜 경고를 끈다(A2 의 03_noise.py 도 같은 경고를 껐다). 대신 아래에서 예측이 유한한지 직접 확인한다.
warnings.filterwarnings("ignore", category=RuntimeWarning)
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
A2 = ROOT / "asos" / "a2_rev2"
SEQ, FIRST_T = 20, 21
TEST_YEARS = list(range(2016, 2026))
GBM = json.load(open(A2 / "gbm_params.json"))
pd.set_option("display.width", 220)
pd.set_option("display.max_rows", 200)


def rmse(e):
    return float(np.sqrt(np.mean(np.asarray(e, float) ** 2)))


# ---------------------------------------------------------------- 자료 (A2 의 load_daily 와 같은 메우기)
d = pd.read_csv(A2 / "a2_daily.csv", parse_dates=["date"])
d = d[d["date"] <= "2025-12-31"].reset_index(drop=True)
g, j = d["gy_sumGsr"].copy(), d["jj_sumGsr"].copy()
d["gy_sumGsr"] = g.fillna(j).ffill()
d["jj_sumGsr"] = j.fillna(g).ffill()
d["m2_sumGsr"] = (d["gy_sumGsr"] + d["jj_sumGsr"]) / 2
d["year"] = d["date"].dt.year
pr = pd.read_csv(ROOT / "solar" / "d2r" / "wx_prevruns_daily.csv", parse_dates=["date"]).set_index("date")
d["fc1"] = pr["shortwave_radiation_previous_day1"].reindex(d["date"]).to_numpy()
d["fc2"] = pr["shortwave_radiation_previous_day2"].reindex(d["date"]).to_numpy()
d["fc0"] = pr["shortwave_radiation"].reindex(d["date"]).to_numpy()
arch = pd.read_csv(ROOT / "solar" / "d2r" / "wx_archive_daily.csv", parse_dates=["date"]).set_index("date")["shortwave_radiation_sum"]
d["era"] = arch.reindex(d["date"]).to_numpy()

gen = d["gen"].to_numpy(float)
gs = d["gy_sumGsr"].to_numpy(float)
zero = gen == 0
near = (~zero) & ((gen < 1.0) | ((gen < 10.0) & (d["m2_sumGsr"].to_numpy() >= 8.0)))
T = np.arange(FIRST_T, len(d))
y = gen[T]
years = d["year"].to_numpy()[T]
dates = d["date"].to_numpy()[T]
offs = np.arange(-(SEQ + 1), 1)
ok = ~(zero | near)[T[:, None] + offs[None, :]].any(axis=1)


def win(arr, k):
    o = np.arange(-SEQ, 0) + k
    return np.asarray(arr, float)[T[:, None] + o[None, :]]


G = win(gen, 0)
Wact = win(gs, +1)          # 마지막 칸 = 대상일 T 의 실제 광양 일사량
Wf1 = win(d["fc1"].to_numpy(), +1)
Wf2 = win(d["fc2"].to_numpy(), +1)
C0, C1 = pd.Timestamp("2023-07-17"), pd.Timestamp("2025-12-30")
ev = (pd.to_datetime(dates) >= C0) & (pd.to_datetime(dates) <= C1) & ok
print(f"공통 구간 표본 {int(ev.sum())}개 ({pd.to_datetime(dates[ev]).min().date()} ~ {pd.to_datetime(dates[ev]).max().date()}), 정지 걸린 표본 {int(((pd.to_datetime(dates) >= C0) & (pd.to_datetime(dates) <= C1) & ~ok).sum())}")

# ---------------------------------------------------------------- (1) 실제 예보와 ASOS 관측의 차이
print("\n[1] 실제 예보(하루 합계 MJ/m2)와 광양 ASOS 일사량의 차이")
dd = d.set_index("date")
for nm, a, b in [("공통 898일", C0, C1), ("예보가 있는 전 기간", pd.Timestamp("2022-07-03"), pd.Timestamp("2025-12-31")), ("보정식을 맞춘 구간(공통 구간 이전)", pd.Timestamp("2022-07-03"), C0 - pd.Timedelta(days=1))]:
    s = dd.loc[a:b]
    for col, lab in [("fc1", "24시간 전 예보"), ("fc2", "48시간 전 예보"), ("fc0", "예보 모델 최신 실행분"), ("era", "재분석(보관 자료)")]:
        m = s[col].notna() & s["gy_sumGsr"].notna()
        e = s.loc[m, col] - s.loc[m, "gy_sumGsr"]
        print(f"  {nm:22s} {lab:14s} n {int(m.sum()):4d} | ASOS 평균 {s.loc[m, 'gy_sumGsr'].mean():5.2f} 예보 평균 {s.loc[m, col].mean():5.2f} (비 {s.loc[m, col].sum() / s.loc[m, 'gy_sumGsr'].sum():.3f})"
              f" | 차이 RMSE {rmse(e):.2f} MJ/m2 = ASOS 평균의 {rmse(e) / s.loc[m, 'gy_sumGsr'].mean() * 100:.1f}% | 상관 {np.corrcoef(s.loc[m, col], s.loc[m, 'gy_sumGsr'])[0, 1]:.3f}"
              f" | 같은 날 발전량과의 상관: 예보 {np.corrcoef(s.loc[m, col], s.loc[m, 'gen'])[0, 1]:.3f}, ASOS {np.corrcoef(s.loc[m, 'gy_sumGsr'], s.loc[m, 'gen'])[0, 1]:.3f}")

# A2 의 잡음 곡선을 실제 예보의 rRMSE 에서 읽기 (A2 의 평가는 걸어가기 2016~2025, 3,555일)
R = pd.read_csv(A2 / "res_noise.csv")
s = dd.loc[C0:C1]
rr = {}
for col in ("fc1", "fc2"):
    m = s[col].notna()
    rr[col] = rmse(s.loc[m, col] - s.loc[m, "gy_sumGsr"]) / s.loc[m, "gy_sumGsr"].mean() * 100
print(f"\n  A2 잡음 곡선(걸어가기 2016~2025, 3,555일)을 실제 예보의 rRMSE 에서 읽은 값: 24시간 전 {rr['fc1']:.1f}%, 48시간 전 {rr['fc2']:.1f}%")
for pos in ("T", "T-1,T"):
    for tr in ("clean", "noisy"):
        out = []
        for m in ("lin", "gbm"):
            gcur = R[(R["var"] == "gy_sumGsr") & (R["pos"] == pos) & (R["train"] == tr) & (R["model"] == m)].sort_values("fc_rrmse")
            out.append(f"{m} 24h {np.interp(rr['fc1'], gcur['fc_rrmse'], gcur['rmse']):.1f} / 48h {np.interp(rr['fc2'], gcur['fc_rrmse'], gcur['rmse']):.1f}")
        print(f"    잡음 자리 {pos:6s} 학습 {'관측으로' if tr == 'clean' else '같은 잡음으로'}: " + " | ".join(out))

# ---------------------------------------------------------------- (2) 같은 모델·같은 날짜에 실제 예보와 모의 잡음을 넣기
print("\n[2] A2 와 같은 가벼운 모델을 다시 만들어 공통 구간에서 비교")


def mk(name):
    return LinearRegression() if name == "lin" else HistGradientBoostingRegressor(**GBM)


def fit_models(X, name, years_needed=(2023, 2024, 2025)):
    return {Y_: mk(name).fit(X[(years < Y_) & ok], y[(years < Y_) & ok]) for Y_ in years_needed}


def predict(models, X):
    p = np.full(len(y), np.nan)
    for Y_, m in models.items():
        te = years == Y_
        good = te & ~np.isnan(X).any(axis=1)
        p[good] = m.predict(X[good])
        assert np.isfinite(p[good]).all(), "예측에 유한하지 않은 값이 있다"
    return p


Xact = np.hstack([G, Wact])
models = {m: fit_models(Xact, m) for m in ("lin", "gbm")}
models_gen = {m: fit_models(G, m) for m in ("lin", "gbm")}
# 저장된 A2 예측과 대조
z = np.load(A2 / "preds_wf.npz", allow_pickle=True)
zd = pd.to_datetime(z["dates"])
for m in ("lin", "gbm"):
    mine = pd.Series(predict(models[m], Xact), index=pd.to_datetime(dates))
    theirs = pd.Series(z[f"D_gy_sumGsr|{m}|zero+near"], index=zd)
    idx = mine.index[ev]
    print(f"  재현 확인 {m}: A2 가 저장한 상한 예측과의 최대차 {np.nanmax(np.abs(mine.loc[idx] - theirs.reindex(idx))):.2e} kWh (표본 {len(idx)})")

# 보정식: ASOS = c0 + c1 x 예보, 공통 구간 이전 날짜로만
pre = (d["date"] < C0) & d["fc1"].notna()
c1_, c0_ = np.polyfit(d.loc[pre, "fc1"], d.loc[pre, "gy_sumGsr"], 1)
pre2 = (d["date"] < C0) & d["fc2"].notna()
e1_, e0_ = np.polyfit(d.loc[pre2, "fc2"], d.loc[pre2, "gy_sumGsr"], 1)
print(f"  보정식(공통 구간 이전 {int(pre.sum())}일): ASOS = {c0_:.3f} + {c1_:.4f} x 24h 예보 | ASOS = {e0_:.3f} + {e1_:.4f} x 48h 예보")


def variant(tslot, t1slot):
    W = Wact.copy()
    W[:, -1] = tslot
    if t1slot is not None:
        W[:, -2] = t1slot
    return np.hstack([G, W])


aT, aT1 = Wact[:, -1], Wact[:, -2]
f1T, f1T1, f2T = Wf1[:, -1], Wf1[:, -2], Wf2[:, -1]
ev2 = ev & ~np.isnan(f1T) & ~np.isnan(f1T1) & ~np.isnan(f2T)
assert ev2.sum() == ev.sum(), "공통 구간에 예보가 빈 날이 있다"
yy = y[ev]
V = {
    "발전량만(둘째 입력 없음)": (None, False, "받을 수 있음"),
    "대상일 실제 ASOS(상한)": (Xact, True, "받을 수 없음"),
    "T 칸만 24h 예보(T-1 은 ASOS 실제)": (variant(f1T, None), False, "T-1 ASOS 는 받을 수 없음"),
    "T-1·T 칸 24h 예보": (variant(f1T, f1T1), False, "받을 수 있음(추정)"),
    "T-1·T 칸 보정한 24h 예보": (variant(c0_ + c1_ * f1T, c0_ + c1_ * f1T1), False, "받을 수 있음(추정)"),
    "T 칸 48h 예보, T-1 칸 24h 예보": (variant(f2T, f1T1), False, "받을 수 있음(추정)"),
    "T 칸 보정한 48h 예보, T-1 칸 보정한 24h 예보": (variant(e0_ + e1_ * f2T, c0_ + c1_ * f1T1), False, "받을 수 있음(추정)"),
}
res = []
for k, (X, fut, av) in V.items():
    row = {"서빙 입력": k, "대상일 실제 값": fut, "예측 시점": av}
    for m in ("lin", "gbm"):
        p = predict(models_gen[m], G)[ev] if X is None else predict(models[m], X)[ev]
        row[f"RMSE {m}"] = rmse(p - yy)
        row[f"치우침% {m}"] = float((p - yy).sum() / yy.sum() * 100)
    res.append(row)

# 모의: 실제 예보와 같은 크기의 독립 잡음(A2 의 방식: 정규 가산 잡음, [0, 그 해 이전 최댓값] 으로 자름)
hi = np.full(len(T), np.nan)
for Y_ in range(2013, 2026):
    prev = gs[d["year"].to_numpy() < Y_]
    hi[years == Y_] = prev.max() if len(prev) else gs[d["year"].to_numpy() == 2013].max()
tgt = {"24h 크기": rmse(f1T[ev] - aT[ev]), "48h 크기": rmse(f2T[ev] - aT[ev])}
print(f"  공통 구간에서 대상일 칸의 예보 오차(ASOS 대비): 24h {tgt['24h 크기']:.3f}, 48h {tgt['48h 크기']:.3f} MJ/m2 | 상관: 24h {np.corrcoef(f1T[ev], aT[ev])[0, 1]:.3f}, 48h {np.corrcoef(f2T[ev], aT[ev])[0, 1]:.3f}")
SIG = {}
for nm, target in tgt.items():
    # 자른 뒤의 RMSE 가 목표와 같아지도록 sigma 를 이분법으로 맞춘다
    lo, hi_s = 0.5, 12.0
    for _ in range(30):
        mid = (lo + hi_s) / 2
        rs = []
        for rep in range(20):
            rng = np.random.default_rng(1000 + rep)
            fT = np.clip(aT + rng.normal(0, mid, len(T)), 0, hi)
            rs.append(rmse(fT[ev] - aT[ev]))
        if np.mean(rs) < target:
            lo = mid
        else:
            hi_s = mid
    sig = (lo + hi_s) / 2
    SIG[nm] = sig
    acc = {m: [] for m in ("lin", "gbm")}
    bia = {m: [] for m in ("lin", "gbm")}
    cg, cf = [], []
    for rep in range(20):
        rng = np.random.default_rng(1000 + rep)
        fT = np.clip(aT + rng.normal(0, sig, len(T)), 0, hi)
        fT1 = np.clip(aT1 + rng.normal(0, SIG.get("24h 크기", sig), len(T)), 0, hi)   # T-1 칸은 두 경우 모두 24h 크기의 잡음
        X = variant(fT, fT1)
        cg.append(np.corrcoef(fT[ev], yy)[0, 1])
        cf.append(np.corrcoef(fT[ev], aT[ev])[0, 1])
        for m in ("lin", "gbm"):
            p = predict(models[m], X)[ev]
            acc[m].append(rmse(p - yy))
            bia[m].append(float((p - yy).sum() / yy.sum() * 100))
    res.append({"서빙 입력": f"모의: T-1·T 칸에 독립 잡음({nm}, sigma {sig:.2f}, 20회 평균)", "대상일 실제 값": True, "예측 시점": "받을 수 없음(실제 값을 가공)",
                "RMSE lin": float(np.mean(acc["lin"])), "RMSE gbm": float(np.mean(acc["gbm"])), "치우침% lin": float(np.mean(bia["lin"])), "치우침% gbm": float(np.mean(bia["gbm"]))})
    print(f"  모의 잡음({nm}): sigma {sig:.2f} MJ/m2, 모의 예보와 ASOS 의 상관 {np.mean(cf):.3f}, 모의 예보와 같은 날 발전량의 상관 {np.mean(cg):.3f}")
print(f"  실제 값들과 같은 날 발전량의 상관(공통 구간): ASOS {np.corrcoef(aT[ev], yy)[0, 1]:.3f}, 24h 예보 {np.corrcoef(f1T[ev], yy)[0, 1]:.3f}, 48h 예보 {np.corrcoef(f2T[ev], yy)[0, 1]:.3f}")
OUT = pd.DataFrame(res)
OUT.to_csv(HERE / "t4_forecast_vs_sim.csv", index=False)
print("\n  공통 구간 898일, A2 식 가벼운 모델(광양 ASOS 실제 일사량으로 학습, 그 해 이전 해로만 학습)")
print(OUT.round(2).to_string(index=False))

# 예보 오차가 '독립 잡음'이 아닌 정도: 예보 오차와 발전량 잔차의 관계
print("\n[3] 예보와 ASOS 의 차이가 모두 '발전량을 설명하지 못하는 잡음'인지")
e24 = f1T[ev] - aT[ev]
# 발전량을 ASOS 로 설명하고 남은 잔차가 (예보 - ASOS) 와 상관이 있으면, 예보가 ASOS 에 없는 정보(발전소 쪽 하늘)를 조금 갖고 있다는 뜻이다
A = np.vstack([np.ones(ev.sum()), aT[ev]]).T
resid = yy - A @ np.linalg.lstsq(A, yy, rcond=None)[0]
print(f"  (24h 예보 - ASOS) 와 'ASOS 로 설명하고 남은 발전량 잔차'의 상관: {np.corrcoef(e24, resid)[0, 1]:+.3f} (독립 잡음이면 0)")
print(f"  독립 잡음 가정에서 기대되는 예보-발전량 상관 = ASOS-발전량 상관 x 예보-ASOS 상관 = {np.corrcoef(aT[ev], yy)[0, 1] * np.corrcoef(f1T[ev], aT[ev])[0, 1]:.3f} (실제 {np.corrcoef(f1T[ev], yy)[0, 1]:.3f})")
