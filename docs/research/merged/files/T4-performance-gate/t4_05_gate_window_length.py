"""T4: 게이트를 재는 구간의 길이에 따라 '모델이 그대로인데도 떨어지는' 비율이 얼마나 되는가.

실습 코드의 재학습(fine_tune) 게이트는 41행으로 문제 21개를 만들고 그 뒤 20%(5개)로 RMSE 를 잰다.
여기서는 공통 구간 898일에서 길이 N 의 연속 창을 하루씩 밀며, 구조별로 고른 기준에 못 미치는 창의 비율을 센다(시드별 평균).
창이 서로 겹치므로 비율은 확률이 아니라 '이 구간에서 그런 창이 얼마나 흔했는가'로 읽는다.
입력: t4_preds.pkl. 출력: t4_gate_window_length.csv, 표준출력
"""
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
D = pd.read_pickle(HERE / "t4_preds.pkl")
P, Y = D["P"], D["Y"]
idx = Y.loc["2023-07-17":"2025-12-30"].index
y = Y.loc[idx].to_numpy()
m7 = P["기준 7일 평균"][0].reindex(idx).to_numpy()
m20 = P["기준 20일 평균"][0].reindex(idx).to_numpy()
rc = P["규칙C 7일 효율(24h 예보) x 24h 예보"][0].reindex(idx).to_numpy()


def roll(e, N):
    return np.sqrt(pd.Series(np.asarray(e, float) ** 2).rolling(N).mean().dropna().to_numpy())


CASES = {
    "발전량만: 실습 LSTM(2013~ 학습)": ("보완 LSTM(T1): 발전량+상수(2013~ 학습)", "gen"),
    "발전량만: 실습 LSTM(ASOS 파일, 일사량 T-2)": ("ASOS LSTM(실습 절차): hadong_upload.csv, 발전량+광양 일사량(T-2 까지)", "gen"),
    "실제 예보: 실습 LSTM(예보로 학습)": ("보완 LSTM(T1): 발전량+24h 일사량 예보(358개 학습)", "fc"),
    "실제 예보: 실습 LSTM(ASOS 로 학습, 예보로 서빙)": ("보완 LSTM(서빙 교체): ASOS 실제로 학습, T-1·T 칸을 24h 예보로 서빙", "fc"),
    "상한: 실습 LSTM(ASOS 실제 일사량)": ("ASOS LSTM(실습 절차): forecast_proxy.csv, 발전량+대상일 실제 광양 일사량", "up"),
}
rows = []
for name, (lab, kind) in CASES.items():
    for N in (5, 21, 60, 90, 180, 365):
        b7, b20, brc = roll(m7 - y, N), roll(m20 - y, N), roll(rc - y, N)
        acc = {}
        for seed, s in P[lab].items():
            r = roll(s.reindex(idx).to_numpy() - y, N)
            res = {"창 RMSE 5%": np.quantile(r, .05), "창 RMSE 중앙": np.median(r), "창 RMSE 95%": np.quantile(r, .95), "창 RMSE 최대": r.max()}
            if kind == "gen":
                res["탈락%: 7일·20일 평균 중 낮은 쪽 미만"] = (~(r < np.minimum(b7, b20))).mean() * 100
                res["탈락%: 7일 평균의 97% 이하"] = (~(r <= 0.97 * b7)).mean() * 100
            if kind == "fc":
                res["탈락%: 7일 평균의 80% 이하"] = (~(r <= 0.80 * b7)).mean() * 100
                res["탈락%: 규칙C 의 105% 이하"] = (~(r <= 1.05 * brc)).mean() * 100
                res["탈락%: 두 조건 모두"] = (~((r <= 0.80 * b7) & (r <= 1.05 * brc))).mean() * 100
            if kind == "up":
                res["탈락%: 절댓값 32"] = (~(r <= 32)).mean() * 100
                res["탈락%: 절댓값 35"] = (~(r <= 35)).mean() * 100
                res["탈락%: 7일 평균의 45% 이하"] = (~(r <= 0.45 * b7)).mean() * 100
            for k, v in res.items():
                acc.setdefault(k, []).append(v)
        rows.append({"예측": name, "창 길이(일)": N, "창 수": len(b7), "시드 수": len(P[lab]), **{k: float(np.mean(v)) for k, v in acc.items()}})
T = pd.DataFrame(rows)
T.to_csv(HERE / "t4_gate_window_length.csv", index=False)
pd.set_option("display.width", 240)
pd.set_option("display.max_colwidth", 50)
for name in CASES:
    t = T[T["예측"] == name].dropna(axis=1, how="all")
    print(f"\n=== {name} (공통 구간 898일, 시드 평균)")
    print(t.drop(columns=["예측"]).round(1).to_string(index=False))
