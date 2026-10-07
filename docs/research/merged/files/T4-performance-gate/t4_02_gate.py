"""T4 배포 게이트: 두 묶음이 제안한 기준(절댓값 32·35kWh, 상대 기준)을 같은 예측에 걸어 본다.

입력: t4_preds.pkl (t4_01_unify.py 가 만든 것). 새로 학습하지 않는다.
보는 것
  1. 구조별(발전량만 / 실제 예보 / 상한 시연) 시드별 통과 여부: 공통 898일, 각 구조의 실습 시험 구간
  2. 겹치지 않는 구간으로 나눈 통과 수(공통 898일을 5등분, 약 180일씩). 이동 창과 달리 서로 겹치지 않는다
  3. 기준이 '아무것도 배우지 않은 예측'을 걸러 내는가(학습 구간 평균 고정값, 7일 평균, 20일 평균, 규칙)
  4. 치우침(합계 기준 %)을 보조 조건으로 걸면 몇 개가 떨어지는가
출력: t4_gate_pass.csv, t4_gate_blocks.csv, 표준출력
"""
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
D = pd.read_pickle(HERE / "t4_preds.pkl")
P, META, Y = D["P"], D["META"], D["Y"]
pd.set_option("display.width", 250)
pd.set_option("display.max_rows", 400)
pd.set_option("display.max_colwidth", 80)


def rmse(e):
    return float(np.sqrt(np.mean(np.asarray(e, float) ** 2)))


M7, M20, RC = P["기준 7일 평균"][0], P["기준 20일 평균"][0], P["규칙C 7일 효율(24h 예보) x 24h 예보"][0]

GATES = {
    "절댓값 32": lambda r, b: r <= 32,
    "절댓값 35": lambda r, b: r <= 35,
    "7일 평균의 45% 이하": lambda r, b: r <= 0.45 * b["m7"],
    "7일 평균의 80% 이하": lambda r, b: r <= 0.80 * b["m7"],
    "7일 평균의 97% 이하": lambda r, b: r <= 0.97 * b["m7"],
    "20일 평균 미만": lambda r, b: r < b["m20"],
    "7일·20일 평균 중 낮은 쪽 미만": lambda r, b: r < min(b["m7"], b["m20"]),
    "7일·20일 평균 중 낮은 쪽의 97% 이하": lambda r, b: r <= 0.97 * min(b["m7"], b["m20"]),
    "규칙C 의 105% 이하": lambda r, b: (r <= 1.05 * b["rc"]) if np.isfinite(b["rc"]) else np.nan,
    "규칙C 의 100% 이하": lambda r, b: (r <= 1.00 * b["rc"]) if np.isfinite(b["rc"]) else np.nan,
}

STRUCT = {
    "발전량만(지난 관측 포함)": [
        "보완 LSTM(T1): 발전량+상수(2013~ 학습)", "보완 LSTM(T1): 발전량+상수(최근 3년 학습)", "보완 LSTM(T1): 발전량+상수(358개 학습)", "보완 LSTM(T1): 발전량+sin(연중 일수)",
        "ASOS LSTM(분할 A): 발전량만(둘째 열 0)", "ASOS LSTM(분할 A): 발전량+하루 최대 출력", "ASOS LSTM(분할 A): 발전량+광양 일조(T-2 까지)",
        "ASOS LSTM(실습 절차): hadong_upload.csv, 발전량+광양 일사량(T-2 까지)", "ASOS LSTM(실습 절차): 일조 판, 발전량+광양 일조(T-2 까지)",
        "보완 LSTM(실습 절차): 예보 업로드 파일의 발전량만(둘째 열 상수)",
    ],
    "실제 예보 24h": [
        "보완 LSTM(T1): 발전량+24h 일사량 예보(358개 학습)", "보완 LSTM(실습 절차): 예보 업로드 파일(발전량+24h 예보)",
        "보완 LSTM(서빙 교체): ASOS 실제로 학습, T-1·T 칸을 24h 예보로 서빙", "보완 LSTM(서빙 교체): ASOS 실제로 학습, 20칸 모두 24h 예보로 서빙",
        "보완 LSTM(서빙 교체): 재분석 실제로 학습, T-1·T 칸을 24h 예보로 서빙",
    ],
    "실제 예보 48h·구름양": [
        "보완 LSTM(서빙 교체): ASOS 실제로 학습, T 칸 48h 예보·T-1 칸 24h 예보", "보완 LSTM(서빙 교체): 재분석 실제로 학습, T 칸 48h 예보·T-1 칸 24h 예보",
        "보완 LSTM(T1): 발전량+하루 전 구름양 예보(2016~ 학습)",
    ],
    "상한 시연(대상일 실제 값)": [
        "ASOS LSTM(실습 절차): forecast_proxy.csv, 발전량+대상일 실제 광양 일사량", "ASOS LSTM(실습 절차): 일조 판, 발전량+대상일 실제 광양 일조",
        "ASOS LSTM(분할 A): 발전량+대상일 실제 광양 일조", "보완 LSTM(T1): 발전량+대상일 실제 재분석 일사량(2013~ 학습)",
        "보완 LSTM(T1): 발전량+대상일 실제 재분석 일사량(358개 학습)", "보완 LSTM(실습 절차): ASOS 파일의 행·분할에 재분석 일사량(출처 대조)",
        "보완 LSTM(실습 절차): 같은 행에 대상일 실제 재분석 일사량",
    ],
    "모의 예보(ASOS)": [
        "ASOS LSTM(분할 A): 모의 예보: 일조 3분위 범주로 학습", "ASOS LSTM(분할 A): 모의 예보: 일조 잡음 2시간으로 학습", "ASOS LSTM(분할 A): 모의 예보: 일조 잡음 4시간으로 학습",
    ],
}
WIN = {"C898": ("2023-07-17", "2025-12-30"), "P946": ("2023-05-30", "2025-12-30"), "P264": ("2025-06-09", "2026-02-27"), "T1_958": ("2023-07-17", "2026-02-28")}


def base(idx):
    y = Y.loc[idx].to_numpy()
    rc = RC.reindex(idx)
    return dict(m7=rmse(M7.reindex(idx).to_numpy() - y), m20=rmse(M20.reindex(idx).to_numpy() - y), rc=rmse(rc.to_numpy() - y) if rc.notna().all() else np.nan)


# ---------------------------------------------------------------- 1. 시드별 통과
rows = []
for st, labs in STRUCT.items():
    for lab in labs:
        for w, (a, b) in WIN.items():
            idx = Y.loc[a:b].index
            bb = base(idx)
            y = Y.loc[idx].to_numpy()
            rs, bs = [], []
            for seed, s in P[lab].items():
                s = s.reindex(idx)
                if s.isna().any():
                    continue
                rs.append(rmse(s.to_numpy() - y))
                bs.append(float((s.to_numpy() - y).sum() / y.sum() * 100))
            if not rs:
                continue
            row = {"구조": st, "예측": lab, "구간": w, "시드 수": len(rs), "RMSE 최소": min(rs), "RMSE 최대": max(rs), "7일 평균": bb["m7"], "20일 평균": bb["m20"], "규칙C": bb["rc"],
                   "7일 대비 비 최대": max(rs) / bb["m7"], "규칙C 대비 비 최대": max(rs) / bb["rc"] if np.isfinite(bb["rc"]) else np.nan,
                   "치우침% 최소": min(bs), "치우침% 최대": max(bs), "|치우침| 5% 이내 시드": int(sum(abs(v) <= 5 for v in bs))}
            for g, f in GATES.items():
                v = [f(r, bb) for r in rs]
                row[g] = np.nan if any(isinstance(x, float) and np.isnan(x) for x in v) else int(sum(v))
            rows.append(row)
G = pd.DataFrame(rows)
G.to_csv(HERE / "t4_gate_pass.csv", index=False)
gcols = list(GATES)
for st in STRUCT:
    print("\n" + "=" * 12, st, "| 칸의 숫자는 통과한 시드 수")
    g = G[G["구조"] == st]
    for w in WIN:
        gw = g[g["구간"] == w]
        if gw.empty:
            continue
        bb = gw.iloc[0]
        print(f"\n  [구간 {w}] 7일 평균 {bb['7일 평균']:.2f} / 20일 평균 {bb['20일 평균']:.2f} / 규칙C {bb['규칙C']:.2f}"
              f" | 문턱: 80% {0.8 * bb['7일 평균']:.1f}, 97% {0.97 * bb['7일 평균']:.1f}, 45% {0.45 * bb['7일 평균']:.1f}, 규칙C 105% {1.05 * bb['규칙C']:.1f}")
        for _, r in gw.iterrows():
            print(f"    {r['예측'][:60]:60s} 시드 {int(r['시드 수'])} RMSE {r['RMSE 최소']:.2f}~{r['RMSE 최대']:.2f} 치우침 {r['치우침% 최소']:+.1f}~{r['치우침% 최대']:+.1f}% | "
                  + ", ".join(f"{k} {'-' if pd.isna(r[k]) else int(r[k])}" for k in gcols) + f" | 치우침 5% 이내 {int(r['|치우침| 5% 이내 시드'])}")

# ---------------------------------------------------------------- 2. 겹치지 않는 구간
print("\n" + "=" * 12, "겹치지 않는 구간(공통 898일을 5등분) 통과 수: 칸 = 통과한 (시드 x 구간) 수 / 전체")
idx_all = Y.loc["2023-07-17":"2025-12-30"].index
blocks = np.array_split(np.arange(len(idx_all)), 5)
print("  구간 경계:", [f"{idx_all[b[0]].date()}~{idx_all[b[-1]].date()}({len(b)}일)" for b in blocks])
bb_blocks = [base(idx_all[b]) for b in blocks]
print("  구간별 7일 평균 RMSE:", [round(x["m7"], 1) for x in bb_blocks], "| 20일 평균:", [round(x["m20"], 1) for x in bb_blocks], "| 규칙C:", [round(x["rc"], 1) for x in bb_blocks])
brow = []
for st, labs in STRUCT.items():
    for lab in labs:
        cnt = {g: 0 for g in GATES}
        tot = 0
        rr = []
        for seed, s in P[lab].items():
            s = s.reindex(idx_all)
            if s.isna().any():
                continue
            for b, bb in zip(blocks, bb_blocks):
                r = rmse(s.to_numpy()[b] - Y.loc[idx_all[b]].to_numpy())
                rr.append(r)
                tot += 1
                for g, f in GATES.items():
                    cnt[g] += int(bool(f(r, bb)))
        if tot == 0:
            continue
        brow.append({"구조": st, "예측": lab, "전체": tot, "구간 RMSE 최소": min(rr), "구간 RMSE 최대": max(rr), **cnt})
B = pd.DataFrame(brow)
B.to_csv(HERE / "t4_gate_blocks.csv", index=False)
for st in STRUCT:
    b = B[B["구조"] == st]
    if b.empty:
        continue
    print(f"\n  -- {st}")
    for _, r in b.iterrows():
        print(f"    {r['예측'][:60]:60s} 구간 RMSE {r['구간 RMSE 최소']:.1f}~{r['구간 RMSE 최대']:.1f} | " + ", ".join(f"{k} {int(r[k])}/{int(r['전체'])}" for k in gcols))

# ---------------------------------------------------------------- 3. 아무것도 배우지 않은 예측이 통과하는가
print("\n" + "=" * 12, "학습하지 않은 예측에 같은 기준을 걸면(1 = 통과)")
NAIVE = {"어제 값": P["기준 어제 값"][0], "7일 평균": M7, "20일 평균": M20, "규칙C(예보)": RC, "규칙C48(48h 예보)": P["규칙C48 7일 효율(24h 예보) x 48h 예보"][0],
         "규칙 상한(ASOS 실제)": P["규칙 상한 7일 효율(ASOS) x 대상일 실제 ASOS"][0], "규칙 상한(재분석 실제)": P["규칙 상한 7일 효율(재분석) x 대상일 실제 재분석"][0]}
for w, (a, b) in WIN.items():
    idx = Y.loc[a:b].index
    y = Y.loc[idx].to_numpy()
    bb = base(idx)
    tm = Y.loc[:pd.Timestamp(a) - pd.Timedelta(days=1)].mean()           # 구간 이전 전체 평균(고정값)
    cand = dict(NAIVE)
    cand["구간 이전 평균 고정값"] = pd.Series(tm, index=idx)
    print(f"\n  [구간 {w}] 7일 {bb['m7']:.2f} 20일 {bb['m20']:.2f} 규칙C {bb['rc']:.2f}")
    for k, s in cand.items():
        s = s.reindex(idx)
        if s.isna().any():
            print(f"    {k:22s} 값 없음(자료 기간 밖)")
            continue
        r = rmse(s.to_numpy() - y)
        print(f"    {k:22s} RMSE {r:6.2f} | " + ", ".join(f"{g} {'-' if (isinstance(f(r, bb), float) and np.isnan(f(r, bb))) else int(bool(f(r, bb)))}" for g, f in GATES.items()))

# ---------------------------------------------------------------- 4. 해마다 절댓값이 얼마나 움직이는가 (6월~2월 같은 달끼리)
print("\n" + "=" * 12, "같은 달(6월 9일 ~ 다음 해 2월 27일)끼리 본 RMSE: 절댓값 기준의 흔들림")
SE = {"2023-24": ("2023-07-17", "2024-02-27"), "2024-25": ("2024-06-09", "2025-02-27"), "2025-26": ("2025-06-09", "2026-02-27")}
for lab in ["기준 7일 평균", "기준 20일 평균", "규칙C 7일 효율(24h 예보) x 24h 예보", "보완 LSTM(T1): 발전량+상수(2013~ 학습)", "보완 LSTM(T1): 발전량+24h 일사량 예보(358개 학습)",
            "보완 LSTM(T1): 발전량+대상일 실제 재분석 일사량(2013~ 학습)", "ASOS LSTM(실습 절차): forecast_proxy.csv, 발전량+대상일 실제 광양 일사량",
            "보완 LSTM(서빙 교체): ASOS 실제로 학습, T-1·T 칸을 24h 예보로 서빙"]:
    out = []
    for k, (a, b) in SE.items():
        idx = Y.loc[a:b].index
        vals = [rmse(s.reindex(idx).to_numpy() - Y.loc[idx].to_numpy()) for s in P[lab].values() if s.reindex(idx).notna().all()]
        out.append(f"{k} {np.mean(vals):.2f}" if vals else f"{k} 없음")
    print(f"  {lab[:60]:60s} " + " | ".join(out))
# 연도별(달력 해) RMSE
print("\n  달력 해별 RMSE (2023 은 07-17 부터, 2025 는 12-30 까지)")
for lab in ["기준 7일 평균", "규칙C 7일 효율(24h 예보) x 24h 예보", "보완 LSTM(T1): 발전량+상수(2013~ 학습)", "ASOS LSTM(분할 A): 발전량만(둘째 열 0)", "보완 LSTM(T1): 발전량+24h 일사량 예보(358개 학습)",
            "보완 LSTM(서빙 교체): ASOS 실제로 학습, T-1·T 칸을 24h 예보로 서빙", "ASOS LSTM(실습 절차): forecast_proxy.csv, 발전량+대상일 실제 광양 일사량",
            "보완 LSTM(T1): 발전량+대상일 실제 재분석 일사량(2013~ 학습)", "ASOS LSTM(분할 A): 발전량+대상일 실제 광양 일조"]:
    out = []
    for yr in (2023, 2024, 2025):
        idx = idx_all[idx_all.year == yr]
        vals = [rmse(s.reindex(idx).to_numpy() - Y.loc[idx].to_numpy()) for s in P[lab].values() if s.reindex(idx).notna().all()]
        out.append(f"{yr} {np.mean(vals):.2f} [{min(vals):.2f}~{max(vals):.2f}]")
    print(f"  {lab[:60]:60s} " + " | ".join(out))
