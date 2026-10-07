"""T4: 게이트의 비교 기준(7일 평균, 20일 평균, 규칙C)을 업로드 파일의 20행 창만으로 계산할 수 있는지 확인한다.

실습 코드는 업로드 파일의 연속 20행(Close, Volume)을 입력으로, 다음 행의 Close 를 정답으로 쓴다.
예보 업로드 파일(merged/gap1/hadong_upload_forecast_jma.csv)은 d 행의 Volume 에 d+1 일에 대한 24시간 전 예보를 둔다.
그러면 창 안의 값만으로 다음 세 가지를 만들 수 있다(대상일 T, 창의 행은 T-20 ~ T-1).
  7일 평균  = mean(Close[-7:])
  20일 평균 = mean(Close)
  규칙C     = Volume[-1] x sum(Close[-7:]) / sum(Volume[-8:-1])     (Volume[-1] 이 T 일 예보, Volume[-8:-1] 이 T-7 ~ T-1 일 예보)
이 값들이 원자료와 날씨 파일에서 직접 계산한 값(t4_01_unify.py)과 같은지, 실습 절차의 시험 구간(뒤 20%)에서 본다.
같은 계산을 ASOS 상한 파일(asos/hadong_upload_forecast_proxy.csv)에도 해 본다(그 파일에서는 Volume 이 실제 관측이므로 '규칙 상한'이 된다).
"""
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
D = pd.read_pickle(HERE / "t4_preds.pkl")
P, Y = D["P"], D["Y"]
SEQ = 20


def rmse(e):
    return float(np.sqrt(np.mean(np.asarray(e, float) ** 2)))


def from_file(path):
    f = pd.read_csv(path, parse_dates=["Date"])
    c, v = f["Close"].to_numpy(float), f["Volume"].to_numpy(float)
    n = len(f) - SEQ
    cut = int(n * 0.8)
    rows = []
    for i in range(n):
        wc, wv = c[i:i + SEQ], v[i:i + SEQ]
        rows.append((f["Date"].iloc[i + SEQ], c[i + SEQ], wc[-7:].mean(), wc.mean(), wv[-1] * wc[-7:].sum() / wv[-8:-1].sum()))
    T = pd.DataFrame(rows, columns=["date", "y", "m7", "m20", "rule"]).iloc[cut:].reset_index(drop=True)
    return f, T


for name, path, ref_rule in [
    ("예보 업로드 파일", ROOT / "merged" / "gap1" / "hadong_upload_forecast_jma.csv", "규칙C 7일 효율(24h 예보) x 24h 예보"),
    ("ASOS 상한 파일", ROOT / "asos" / "hadong_upload_forecast_proxy.csv", "규칙 상한 7일 효율(ASOS) x 대상일 실제 ASOS"),
    ("ASOS 현실 조건 파일", ROOT / "asos" / "hadong_upload.csv", None),
]:
    f, T = from_file(path)
    idx = pd.DatetimeIndex(T["date"])
    assert np.allclose(T["y"].to_numpy(), Y.reindex(idx).to_numpy(), atol=2e-3)
    y = T["y"].to_numpy()
    print(f"\n{name}: {len(f)}행, 시험 {len(T)}문제 ({idx.min().date()} ~ {idx.max().date()}), 하루 평균 {y.mean():.1f} kWh")
    print(f"  창에서 계산: 7일 평균 RMSE {rmse(T['m7'] - y):.2f}, 20일 평균 {rmse(T['m20'] - y):.2f}" + (f", 규칙 {rmse(T['rule'] - y):.2f}" if ref_rule else ""))
    d7 = np.abs(T["m7"].to_numpy() - P["기준 7일 평균"][0].reindex(idx).to_numpy()).max()
    d20 = np.abs(T["m20"].to_numpy() - P["기준 20일 평균"][0].reindex(idx).to_numpy()).max()
    msg = f"  원자료에서 계산한 값과의 최대차: 7일 평균 {d7:.2e}, 20일 평균 {d20:.2e}"
    if ref_rule:
        dr = np.abs(T["rule"].to_numpy() - P[ref_rule][0].reindex(idx).to_numpy())
        msg += f", 규칙 {np.nanmax(dr):.2e} kWh"
    print(msg)
    lo = min(rmse(T["m7"] - y), rmse(T["m20"] - y))
    print(f"  게이트 문턱(kWh): 7일·20일 평균 중 낮은 쪽 {lo:.2f} | 7일 평균의 80% {0.8 * rmse(T['m7'] - y):.2f}" + (f" | 규칙의 105% {1.05 * rmse(T['rule'] - y):.2f}" if ref_rule else ""))
