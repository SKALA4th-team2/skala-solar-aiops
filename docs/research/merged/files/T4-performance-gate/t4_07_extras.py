"""T4: 절에 쓸 보조 수치. 오전 예측용 기준, 조건별 범위 요약, 구조별 게이트 문턱의 kWh 환산."""
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
D = pd.read_pickle(HERE / "t4_preds.pkl")
P, META, Y = D["P"], D["META"], D["Y"]


def rmse(e):
    return float(np.sqrt(np.mean(np.asarray(e, float) ** 2)))


idx = Y.loc["2023-07-17":"2025-12-30"].index
y = Y.loc[idx].to_numpy()
print("[오전 예측용 기준: 그날 발전량을 모르는 경우] 공통 898일")
for nm, s in [("그저께 값(T-2)", Y.shift(2)), ("7일 평균(T-8 ~ T-2)", Y.shift(2).rolling(7).mean()), ("20일 평균(T-21 ~ T-2)", Y.shift(2).rolling(20).mean())]:
    p = s.reindex(idx).to_numpy()
    print(f"  {nm:22s} RMSE {rmse(p - y):.2f} 합계 오차율 {np.abs(p - y).sum() / y.sum() * 100:.2f}%")

T = pd.read_csv(HERE / "t4_table_C898.csv")
print("\n[조건 x 모델 종류별 범위] 공통 898일. RMSE 는 예측별 시드 평균의 최소~최대, 합계 오차율도 같다")
g = T.groupby(["cond", "family"], sort=False).agg(n=("label", "size"), rmse_lo=("RMSE", "min"), rmse_hi=("RMSE", "max"), wape_lo=("WAPE", "min"), wape_hi=("WAPE", "max"),
                                                  seed_lo=("min", "min"), seed_hi=("max", "max"), b55_lo=("MAE_cap55", "min"), b55_hi=("MAE_cap55", "max"))
pd.set_option("display.width", 200)
print(g.round(2).to_string())

print("\n[실제 예보 24h 가운데 예측 시점에 채울 수 있는 배치만] 공통 898일")
t = T[(T["cond"] == "실제 예보 24h") & T["avail"].str.startswith("받을 수 있음")]
print(t[["family", "label", "n_seed", "RMSE", "sd", "WAPE", "bias_pct", "avail"]].round(2).to_string(index=False))

print("\n[구조별 게이트 문턱을 kWh 로 바꾼 값] 업로드 파일의 실습 시험 구간 기준")
for nm, a, b in [("예보 업로드 파일 시험 264일", "2025-06-09", "2026-02-27"), ("ASOS 업로드 파일 시험 946일", "2023-05-30", "2025-12-30"), ("공통 898일", "2023-07-17", "2025-12-30")]:
    ii = Y.loc[a:b].index
    yy = Y.loc[ii].to_numpy()
    m7 = rmse(P["기준 7일 평균"][0].reindex(ii).to_numpy() - yy)
    m20 = rmse(P["기준 20일 평균"][0].reindex(ii).to_numpy() - yy)
    rc = rmse(P["규칙C 7일 효율(24h 예보) x 24h 예보"][0].reindex(ii).to_numpy() - yy)
    rc48 = rmse(P["규칙C48 7일 효율(24h 예보) x 48h 예보"][0].reindex(ii).to_numpy() - yy)
    print(f"  {nm}: 7일 평균 {m7:.2f}, 20일 평균 {m20:.2f}, 규칙C {rc:.2f}, 규칙C48 {rc48:.2f} | 발전량만 구조 문턱 {min(m7, m20):.2f} | 예보 구조 문턱 min(7일x0.8 {0.8 * m7:.2f}, 규칙Cx1.05 {1.05 * rc:.2f}) = {min(0.8 * m7, 1.05 * rc):.2f}"
          f" | 48h 예보를 쓸 때 규칙C48x1.05 {1.05 * rc48:.2f}")

print("\n[20일 평균과 7일 평균 가운데 어느 쪽이 더 낮은가: 달력 해와 계절]")
for nm, ii in [("2023(07-17~)", idx[idx.year == 2023]), ("2024", idx[idx.year == 2024]), ("2025(~12-30)", idx[idx.year == 2025]),
               ("3~5월", idx[idx.month.isin([3, 4, 5])]), ("6~8월", idx[idx.month.isin([6, 7, 8])]), ("9~11월", idx[idx.month.isin([9, 10, 11])]), ("12~2월", idx[idx.month.isin([12, 1, 2])])]:
    yy = Y.loc[ii].to_numpy()
    out = [f"{k} {rmse(P[lab][0].reindex(ii).to_numpy() - yy):.1f}" for k, lab in [("7일", "기준 7일 평균"), ("20일", "기준 20일 평균"), ("규칙C", "규칙C 7일 효율(24h 예보) x 24h 예보")]]
    for k, lab in [("LSTM 발전량만", "보완 LSTM(T1): 발전량+상수(2013~ 학습)"), ("LSTM 예보", "보완 LSTM(T1): 발전량+24h 일사량 예보(358개 학습)"), ("LSTM ASOS학습·예보서빙", "보완 LSTM(서빙 교체): ASOS 실제로 학습, T-1·T 칸을 24h 예보로 서빙"),
                   ("LSTM 상한(ASOS)", "ASOS LSTM(실습 절차): forecast_proxy.csv, 발전량+대상일 실제 광양 일사량")]:
        out.append(f"{k} {np.mean([rmse(s.reindex(ii).to_numpy() - yy) for s in P[lab].values()]):.1f}")
    print(f"  {nm:14s} n {len(ii):3d} | " + " | ".join(out))
