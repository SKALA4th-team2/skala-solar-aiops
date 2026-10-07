"""T4 성능·게이트: 두 묶음과 보완 조사가 남긴 예측 파일을 한 곳에 모아 같은 날짜, 같은 지표로 다시 계산한다.

이 스크립트는 다른 폴더의 모듈을 import 하지 않는다. 발전 실적 원본과 예측 파일만 읽는다(읽기 전용).
정의
  RMSE          : 하루 발전량(kWh) 오차의 제곱평균제곱근
  합계 오차율   : sum|예측-실제| / sum(실제) x 100
  치우침%       : sum(예측-실제) / sum(실제) x 100 (양수면 높게 예측)
  용량 대비     : MAE / (용량 x 24h), RMSE / (용량 x 24h). 용량은 50kW 와 55kW 둘 다
구간
  C898 : 2023-07-17 ~ 2025-12-30 (사전 조사 T1 평가, ASOS 분할 A, ASOS 실습 절차 시험 구간이 모두 겹치는 날)
  P264 : 2025-06-09 ~ 2026-02-27 (예보 업로드 파일을 실습 절차로 학습했을 때의 시험 구간)
  O205 : 2025-06-09 ~ 2025-12-30 (P264 와 ASOS 자료가 겹치는 날)
출력: t4_preds.pkl(다음 스크립트용), t4_table_*.csv, t4_per_seed_*.csv, 표준출력(로그)
"""
import glob
import json
import os
import re
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
SOLAR, ASOS, GAP1 = ROOT / "solar", ROOT / "asos", ROOT / "merged" / "gap1"
pd.set_option("display.width", 260)
pd.set_option("display.max_columns", 40)
pd.set_option("display.max_rows", 400)
pd.set_option("display.max_colwidth", 70)

# ------------------------------------------------------------------ 원자료
raw = pd.read_csv(SOLAR / "data_15043409.csv", encoding="cp949")
raw["date"] = pd.to_datetime(raw["년월일"])
raw = raw.sort_values("date").reset_index(drop=True)
assert raw["date"].diff().dropna().dt.days.eq(1).all()
Y = pd.Series(raw["총량(kw)"].to_numpy(float), index=raw["date"], name="y")
HC = [str(i) for i in range(1, 25)]
assert np.allclose(raw[HC].sum(axis=1).to_numpy(), Y.to_numpy(), atol=1e-6), "총량과 시간별 합이 다르다"
print(f"발전 실적 원본: {len(Y)}일 {Y.index.min().date()} ~ {Y.index.max().date()}, 시간값 최대 {raw[HC].to_numpy().max():.3f} kW, 50kW 초과 칸 {(raw[HC].to_numpy() > 50).sum()}개")

arch = pd.read_csv(SOLAR / "d2r" / "wx_archive_daily.csv", parse_dates=["date"]).set_index("date")["shortwave_radiation_sum"].reindex(Y.index)
pr = pd.read_csv(SOLAR / "d2r" / "wx_prevruns_daily.csv", parse_dates=["date"]).set_index("date")
fc0 = pr["shortwave_radiation"].reindex(Y.index)
fc1 = pr["shortwave_radiation_previous_day1"].reindex(Y.index)
fc2 = pr["shortwave_radiation_previous_day2"].reindex(Y.index)
full = pd.read_csv(ASOS / "hadong_daily_full.csv", parse_dates=["date"]).set_index("date")
assert np.allclose(full["gen_kwh"].reindex(Y.index).to_numpy(), Y.to_numpy(), atol=1e-6), "ASOS 결합 자료의 발전량이 원본과 다르다"
gsr = full["gy_gsr"].reindex(Y.index)
stop = full["stop_day"].reindex(Y.index).fillna(0).astype(int)

WIN = {
    "C898": ("2023-07-17", "2025-12-30"),
    "P264": ("2025-06-09", "2026-02-27"),
    "O205": ("2025-06-09", "2025-12-30"),
    "T1_958": ("2023-07-17", "2026-02-28"),
    "A946": ("2023-05-31", "2025-12-31"),
    "P946": ("2023-05-30", "2025-12-30"),
}
for k, (a, b) in WIN.items():
    idx = Y.loc[a:b].index
    print(f"구간 {k}: {a} ~ {b} {len(idx)}일, 하루 평균 {Y.loc[a:b].mean():.1f} kWh, 표준편차 {Y.loc[a:b].std(ddof=0):.1f}, 정지 표시일 {int(stop.loc[a:b].sum())}, 10kWh 미만 {int((Y.loc[a:b] < 10).sum())}일")

# ------------------------------------------------------------------ 예측 모으기
P = {}      # label -> {seed: Series(date -> pred)}
META = {}   # label -> dict


def add(label, seed, dates, pred, **meta):
    s = pd.Series(np.asarray(pred, float), index=pd.to_datetime(dates))
    s = s[~s.isna()]
    P.setdefault(label, {})[seed] = s
    if label not in META:
        META[label] = meta


def meta(bundle, family, cond, future, avail, train):
    """bundle: 사전 조사 / ASOS 분석 / 보완 조사 / 이번 계산. future: 대상일의 실제 값을 입력에 썼는가. avail: 예측 시점(대상일 전날 저녁)에 받을 수 있는 입력인가."""
    return dict(bundle=bundle, family=family, cond=cond, future=future, avail=avail, train=train)


# --- (1) 학습 없는 기준과 규칙: 원자료에서 직접
ys = Y
add("기준 어제 값", 0, Y.index, ys.shift(1), **meta("이번 계산", "규칙", "발전량만", False, "받을 수 있음", "학습 없음"))
add("기준 7일 평균", 0, Y.index, ys.shift(1).rolling(7).mean(), **meta("이번 계산", "규칙", "발전량만", False, "받을 수 있음", "학습 없음"))
add("기준 20일 평균", 0, Y.index, ys.shift(1).rolling(20).mean(), **meta("이번 계산", "규칙", "발전량만", False, "받을 수 있음", "학습 없음"))
s7 = ys.shift(1).rolling(7).sum()
effC = s7 / fc1.shift(1).rolling(7).sum()
effB = s7 / fc0.shift(1).rolling(7).sum()
effA = s7 / arch.shift(1).rolling(7).sum()
effG = s7 / gsr.shift(1).rolling(7).sum()
effC48 = s7 / fc2.shift(1).rolling(7).sum()
CAL_BEFORE = pd.Timestamp("2023-07-17")
pre = (Y.index < CAL_BEFORE) & fc1.notna().to_numpy() & arch.notna().to_numpy()
b1, b0 = np.polyfit(fc1[pre], arch[pre], 1)
pre_g = (Y.index < CAL_BEFORE) & fc1.notna().to_numpy() & gsr.notna().to_numpy()
g1, g0 = np.polyfit(fc1[pre_g], gsr[pre_g], 1)
print(f"보정식(창 이전 {int(pre.sum())}일): 재분석 = {b0:.3f} + {b1:.4f} x 24h 예보 | ASOS = {g0:.3f} + {g1:.4f} x 24h 예보 ({int(pre_g.sum())}일)")
add("규칙C 7일 효율(24h 예보) x 24h 예보", 0, Y.index, effC * fc1, **meta("이번 계산", "규칙", "실제 예보 24h", False, "받을 수 있음(추정)", "학습 없음"))
add("규칙B 7일 효율(최신 실행분) x 24h 예보", 0, Y.index, effB * fc1, **meta("이번 계산", "규칙", "실제 예보 24h", False, "전날 치 최신 실행분을 전날 저녁에 받는지 확인하지 못함", "학습 없음"))
add("규칙A 7일 효율(재분석) x 보정한 24h 예보", 0, Y.index, effA * (b0 + b1 * fc1), **meta("이번 계산", "규칙", "실제 예보 24h", False, "전날 치 재분석을 전날 저녁에 받는지 확인하지 못함", "학습 없음"))
add("규칙C48 7일 효율(24h 예보) x 48h 예보", 0, Y.index, effC * fc2, **meta("이번 계산", "규칙", "실제 예보 48h", False, "받을 수 있음(추정)", "학습 없음"))
# ASOS 는 T-2 까지만 받을 수 있다: 효율은 T-8 ~ T-2 의 7일, 대상일은 ASOS 수준으로 보정한 24h 예보
effG2 = ys.shift(2).rolling(7).sum() / gsr.shift(2).rolling(7).sum()
add("규칙D 7일 효율(ASOS, T-2 까지) x 보정한 24h 예보", 0, Y.index, effG2 * (g0 + g1 * fc1), **meta("이번 계산", "규칙", "실제 예보 24h", False, "받을 수 있음(추정)", "학습 없음"))
add("규칙 상한 7일 효율(재분석) x 대상일 실제 재분석", 0, Y.index, effA * arch, **meta("이번 계산", "규칙", "상한(재분석)", True, "받을 수 없음(대상일 실제 값)", "학습 없음"))
add("규칙 상한 7일 효율(ASOS) x 대상일 실제 ASOS", 0, Y.index, effG * gsr, **meta("이번 계산", "규칙", "상한(ASOS)", True, "받을 수 없음(대상일 실제 값)", "학습 없음"))

# --- (2) 사전 조사 D2 의 가벼운 모델 (80/20 분할, 학습 ~2023-07-16)
s1 = pd.read_csv(SOLAR / "d2r" / "preds_s1.csv", parse_dates=["date"])
t1 = pd.read_csv(SOLAR / "d2r" / "preds_T1_fc.csv", parse_dates=["date"])
assert np.allclose(s1["y"].to_numpy(), Y.reindex(s1["date"]).to_numpy(), atol=1e-6) and np.allclose(t1["y"].to_numpy(), Y.reindex(t1["date"]).to_numpy(), atol=1e-6)
D2 = [
    (s1, "발전량만", "발전량만", False, "받을 수 있음"),
    (s1, "(나) 발전량+전날까지 일사량", "지난 날씨(재분석, T-1 까지)", False, "전날 치 재분석을 전날 저녁에 받는지 확인하지 못함"),
    (s1, "(가) 발전량+대상일 실제 일사량", "상한(재분석)", True, "받을 수 없음(대상일 실제 값)"),
    (t1, "(다-A) 일사량 24시간 전 예보 대입, 보정", "실제 예보 24h", False, "전날 치 재분석을 전날 저녁에 받는지 확인하지 못함"),
    (t1, "(다-A) 일사량 24시간 전 예보 대입, 보정 없음", "실제 예보 24h", False, "전날 치 재분석을 전날 저녁에 받는지 확인하지 못함"),
    (t1, "(다-B) 일사량 24시간 전 예보로 직접 학습 [2022-07~2023-07]", "실제 예보 24h", False, "받을 수 있음(추정)"),
    (t1, "(다-A) 일사량 48시간 전 예보 대입, 보정", "실제 예보 48h", False, "전날 치 재분석을 전날 저녁에 받는지 확인하지 못함"),
    (t1, "(다-B) 일사량 48시간 전 예보로 직접 학습 [2022-07~2023-07]", "실제 예보 48h", False, "받을 수 있음(추정)"),
]
for d, col, cond, fut, av in D2:
    for m, mn in (("ridge", "Ridge"), ("hgb", "부스팅")):
        add(f"사전 D2 {mn}: {col}", 0, d["date"], d[f"{col}|{m}"], **meta("사전 조사", "가벼운 모델", cond, fut, av, "80/20, 학습 ~2023-07-16"))

# --- (3) ASOS A2 의 가벼운 모델 (연도별 걸어가기: 그 해 이전 자료로만 학습)
z = np.load(ASOS / "a2_rev2" / "preds_wf.npz", allow_pickle=True)
zd = pd.to_datetime(z["dates"])
assert np.allclose(z["y"], Y.reindex(zd).to_numpy(), atol=1e-6)
A2 = [
    ("A", "발전량만", "발전량만", False, "받을 수 있음"),
    ("A_lag", "발전량만(T-2 까지, 오전 예측)", "발전량만(오전)", False, "받을 수 있음"),
    ("C_gy_sumGsr", "발전량+광양 일사량(T-2 까지)", "지난 날씨(ASOS, T-2 까지)", False, "받을 수 있음"),
    ("C0_gy_sumGsr", "발전량+광양 일사량(T-1 까지)", "지난 날씨(ASOS, T-1 까지)", False, "받을 수 없음(T-1 ASOS 는 다음 날 11시 이후)"),
    ("D_gy_sumGsr", "발전량+대상일 실제 광양 일사량", "상한(ASOS)", True, "받을 수 없음(대상일 실제 값)"),
    ("D_gy_sumSsHr", "발전량+대상일 실제 광양 일조시간", "상한(ASOS 일조)", True, "받을 수 없음(대상일 실제 값)"),
]
for key, lab, cond, fut, av in A2:
    for m, mn in (("lin", "선형"), ("gbm", "부스팅")):
        add(f"ASOS A2 {mn}: {lab}", 0, zd, z[f"{key}|{m}|zero+near"], **meta("ASOS 분석", "가벼운 모델", cond, fut, av, "걸어가기(그 해 이전 해로 학습)"))

# --- (4) 실습 LSTM: 사전 조사 쪽 보완(g1_lstm, gap1). 표본 i 의 목표일 = 원자료의 (i+20)번째 날
tdates = Y.index[20:]
LS = [
    ("ga_const_full", "발전량+상수(2013~ 학습)", "발전량만", False, "받을 수 있음"),
    ("ga_const_3y", "발전량+상수(최근 3년 학습)", "발전량만", False, "받을 수 있음"),
    ("ga_const_fc", "발전량+상수(358개 학습)", "발전량만", False, "받을 수 있음"),
    ("na_sin_full", "발전량+sin(연중 일수)", "발전량만", False, "받을 수 있음"),
    ("da_fc1_full", "발전량+24h 일사량 예보(358개 학습)", "실제 예보 24h", False, "받을 수 있음(추정)"),
    ("ra_cloud_full", "발전량+하루 전 구름양 예보(2016~ 학습)", "실제 예보(구름양)", False, "일부는 전날 저녁에 받을 수 없음(추정)"),
    ("ma_sw_full", "발전량+대상일 실제 재분석 일사량(2013~ 학습)", "상한(재분석)", True, "받을 수 없음(대상일 실제 값)"),
    ("ma_sw_fc", "발전량+대상일 실제 재분석 일사량(358개 학습)", "상한(재분석)", True, "받을 수 없음(대상일 실제 값)"),
]
for key, lab, cond, fut, av in LS:
    for d in (SOLAR / "g1_lstm" / "runs", GAP1 / "runs"):
        for f in sorted(glob.glob(str(d / f"T1_{key}_s*.npz"))):
            if f.endswith("_repro.npz"):
                continue
            seed = int(re.search(r"_s(\d+)\.npz$", f).group(1))
            zz = np.load(f, allow_pickle=False)
            assert len(zz["pred"]) == len(tdates)
            p = pd.Series(zz["pred"], index=tdates)
            p = p[~zz["train_mask"]]          # 학습 표본의 예측은 쓰지 않는다
            add(f"보완 LSTM(T1): {lab}", seed, p.index, p.to_numpy(), **meta("보완 조사(사전 조사 자료)", "실습 LSTM", cond, fut, av, f"학습 ~2023-07-16, {int(zz['n_train'])}개"))

# --- (5) 실습 LSTM: ASOS A3 분할 A (학습 ~2023-05-30)
A3 = [
    ("a3_review", "gen_only", "발전량만(둘째 열 0)", "발전량만", False, "받을 수 있음"),
    ("a3_review", "na_lag", "발전량+광양 일조(T-2 까지)", "지난 날씨(ASOS, T-2 까지)", False, "받을 수 있음"),
    ("a3", "ga", "발전량+하루 최대 출력", "발전량만", False, "받을 수 있음"),
    ("a3", "na", "발전량+광양 일조(T-1 까지)", "지난 날씨(ASOS, T-1 까지)", False, "받을 수 없음(T-1 ASOS 는 다음 날 11시 이후)"),
    ("a3", "na_strict", "발전량(T-2 까지)+일조(T-2 까지), 오전 예측", "발전량만(오전)", False, "받을 수 있음"),
    ("a3", "da", "발전량+대상일 실제 광양 일조", "상한(ASOS 일조)", True, "받을 수 없음(대상일 실제 값)"),
    ("a3", "ra_bin3", "모의 예보: 일조 3분위 범주로 학습", "모의 예보", True, "받을 수 없음(대상일 실제 값을 가공)"),
    ("a3", "ra_n2", "모의 예보: 일조 잡음 2시간으로 학습", "모의 예보", True, "받을 수 없음(대상일 실제 값을 가공)"),
    ("a3", "ra_n4", "모의 예보: 일조 잡음 4시간으로 학습", "모의 예보", True, "받을 수 없음(대상일 실제 값을 가공)"),
]
for folder, key, lab, cond, fut, av in A3:
    for f in sorted(glob.glob(str(ASOS / folder / "results" / f"A_{key}_s?_pred.csv"))):
        seed = int(re.search(r"_s(\d+)_pred\.csv$", f).group(1))
        d = pd.read_csv(f, parse_dates=["date"])
        assert np.allclose(d["actual"].to_numpy(), Y.reindex(d["date"]).to_numpy(), atol=2e-3), f
        add(f"ASOS LSTM(분할 A): {lab}", seed, d["date"], d["pred"], **meta("ASOS 분석", "실습 LSTM", cond, fut, av, "학습 ~2023-05-30, 3,649개"))

# --- (6) 실습 LSTM: ASOS 가 만든 업로드 파일을 실습 절차로 학습(train_check)
TC = [
    ("lag_gsr", "hadong_upload.csv, 발전량+광양 일사량(T-2 까지)", "지난 날씨(ASOS, T-2 까지)", False, "받을 수 있음"),
    ("lag_ss", "일조 판, 발전량+광양 일조(T-2 까지)", "지난 날씨(ASOS, T-2 까지)", False, "받을 수 있음"),
    ("proxy_gsr", "forecast_proxy.csv, 발전량+대상일 실제 광양 일사량", "상한(ASOS)", True, "받을 수 없음(대상일과 그 전날의 실제 값)"),
    ("proxy_ss", "일조 판, 발전량+대상일 실제 광양 일조", "상한(ASOS 일조)", True, "받을 수 없음(대상일과 그 전날의 실제 값)"),
]
for key, lab, cond, fut, av in TC:
    d = pd.read_csv(ASOS / "hadong_build" / "train_check" / f"{key}_pred.csv", parse_dates=["date"])
    assert np.allclose(d["actual"].to_numpy(), Y.reindex(d["date"]).to_numpy(), atol=2e-3)
    for seed in (42, 43, 44):
        add(f"ASOS LSTM(실습 절차): {lab}", seed, d["date"], d[f"pred_s{seed}"], **meta("ASOS 분석", "실습 LSTM", cond, fut, av, "실습 절차, 학습 ~2023-05-29, 3,780문제"))

# --- (7) 보완 조사: 실제 값으로 학습한 LSTM 에 서빙 때만 예보를 넣은 예측
sv = pd.read_csv(GAP1 / "preds_serve_variants.csv", parse_dates=["date"])
assert np.allclose(sv["y"].to_numpy(), Y.reindex(sv["date"]).to_numpy(), atol=1e-6)
SV = [
    ("asosproxy", "T1T", "ASOS 실제로 학습, T-1·T 칸을 24h 예보로 서빙", "실제 예보 24h", False, "받을 수 있음(추정)"),
    ("asosproxy", "all", "ASOS 실제로 학습, 20칸 모두 24h 예보로 서빙", "실제 예보 24h", False, "받을 수 있음(추정)"),
    ("asosproxy", "T1T_cal", "ASOS 실제로 학습, T-1·T 칸을 보정한 24h 예보로 서빙", "실제 예보 24h", False, "받을 수 있음(추정)"),
    ("asosproxy", "T", "ASOS 실제로 학습, T 칸만 24h 예보(T-1 은 ASOS 실제)", "실제 예보 24h", False, "받을 수 없음(T-1 ASOS 는 다음 날 11시 이후)"),
    ("asosproxy", "T1T_48", "ASOS 실제로 학습, T 칸 48h 예보·T-1 칸 24h 예보", "실제 예보 48h", False, "받을 수 있음(추정)"),
    ("asosproxy", "actual", "ASOS 실제로 학습·서빙(보완 조사 재학습)", "상한(ASOS)", True, "받을 수 없음(대상일과 그 전날의 실제 값)"),
    ("T1_ma_sw_full", "T1T", "재분석 실제로 학습, T-1·T 칸을 24h 예보로 서빙", "실제 예보 24h", False, "받을 수 있음(추정). T-2 재분석은 확인하지 못함"),
    ("T1_ma_sw_full", "all", "재분석 실제로 학습, 20칸 모두 24h 예보로 서빙", "실제 예보 24h", False, "받을 수 있음(추정)"),
    ("T1_ma_sw_full", "T1T_48", "재분석 실제로 학습, T 칸 48h 예보·T-1 칸 24h 예보", "실제 예보 48h", False, "받을 수 있음(추정). T-2 재분석은 확인하지 못함"),
]
for model, how, lab, cond, fut, av in SV:
    g = sv[(sv["모델"] == model) & (sv["방법"] == how)]
    for seed, gg in g.groupby("시드"):
        tr = "실습 절차, 학습 ~2023-05-29" if model == "asosproxy" else "학습 ~2023-07-16, 3,699개"
        add(f"보완 LSTM(서빙 교체): {lab}", int(seed), gg["date"], gg["pred"], **meta("보완 조사", "실습 LSTM", cond, fut, av, tr))

# --- (8) 보완 조사: 실습 절차 그대로 학습한 5종(runs_practice)
RP = [
    ("jma", "예보 업로드 파일(발전량+24h 예보)", "실제 예보 24h", False, "받을 수 있음(추정)", "실습 절차, 학습 ~2025-06-08, 1,053문제"),
    ("const", "예보 업로드 파일의 발전량만(둘째 열 상수)", "발전량만", False, "받을 수 있음", "실습 절차, 학습 ~2025-06-08, 1,053문제"),
    ("era_next", "같은 행에 대상일 실제 재분석 일사량", "상한(재분석)", True, "받을 수 없음(대상일 실제 값)", "실습 절차, 학습 ~2025-06-08, 1,053문제"),
    ("era_next_asosrows", "ASOS 파일의 행·분할에 재분석 일사량(출처 대조)", "상한(재분석)", True, "받을 수 없음(대상일 실제 값)", "실습 절차, 학습 ~2023-05-29, 3,780문제"),
    ("asosproxy", "forecast_proxy.csv 재학습(발전량+대상일 실제 광양 일사량)", "상한(ASOS)", True, "받을 수 없음(대상일과 그 전날의 실제 값)", "실습 절차, 학습 ~2023-05-29, 3,780문제"),
]
for key, lab, cond, fut, av, tr in RP:
    for seed in (42, 43, 44):
        zz = np.load(GAP1 / "runs_practice" / f"{key}_s{seed}.npz", allow_pickle=False)
        dd = pd.to_datetime(zz["test_dates"])
        assert np.allclose(zz["y_test"], Y.reindex(dd).to_numpy(), atol=1e-6)
        add(f"보완 LSTM(실습 절차): {lab}", seed, dd, zz["pred"], **meta("보완 조사", "실습 LSTM", cond, fut, av, tr))

print(f"\n모은 예측: {len(P)}종, 줄 수 {sum(len(v) for v in P.values())}")
pd.to_pickle({"P": P, "META": META, "Y": Y, "fc0": fc0, "fc1": fc1, "fc2": fc2, "arch": arch, "gsr": gsr}, HERE / "t4_preds.pkl")


# ------------------------------------------------------------------ 지표
def metr(y, p):
    e = p - y
    r = float(np.sqrt((e ** 2).mean()))
    mae = float(np.abs(e).mean())
    return dict(RMSE=r, MAE=mae, WAPE=float(np.abs(e).sum() / y.sum() * 100), bias_pct=float(e.sum() / y.sum() * 100),
                MAE_cap50=mae / 1200 * 100, MAE_cap55=mae / 1320 * 100, RMSE_cap50=r / 1200 * 100, RMSE_cap55=r / 1320 * 100, pmin=float(p.min()))


def table(win):
    a, b = WIN[win]
    idx = Y.loc[a:b].index
    y = Y.loc[idx].to_numpy()
    rows, per = [], []
    ref = {}
    for k in ("기준 7일 평균", "기준 20일 평균", "규칙C 7일 효율(24h 예보) x 24h 예보"):
        s = P[k][0].reindex(idx)
        ref[k] = metr(y, s.to_numpy())["RMSE"] if s.notna().all() else np.nan
    for lab, seeds in P.items():
        ms = []
        for seed, s in seeds.items():
            s = s.reindex(idx)
            if s.isna().any():
                continue
            m = metr(y, s.to_numpy())
            m.update(label=lab, seed=seed)
            ms.append(m)
            per.append({**META[lab], **m, "window": win})
        if not ms:
            continue
        M = pd.DataFrame(ms)
        r = M["RMSE"]
        rows.append({**META[lab], "label": lab, "n_days": len(idx), "n_seed": len(M),
                     "RMSE": r.mean(), "sd": r.std(ddof=1) if len(M) > 1 else np.nan, "min": r.min(), "max": r.max(),
                     "WAPE": M["WAPE"].mean(), "bias_pct": M["bias_pct"].mean(), "bias_min": M["bias_pct"].min(), "bias_max": M["bias_pct"].max(),
                     "MAE": M["MAE"].mean(), "MAE_cap50": M["MAE_cap50"].mean(), "MAE_cap55": M["MAE_cap55"].mean(),
                     "RMSE_cap50": M["RMSE_cap50"].mean(), "RMSE_cap55": M["RMSE_cap55"].mean(),
                     "vs_mean7": r.mean() / ref["기준 7일 평균"], "vs_mean20": r.mean() / ref["기준 20일 평균"],
                     "vs_ruleC": r.mean() / ref["규칙C 7일 효율(24h 예보) x 24h 예보"], "pred_min": M["pmin"].min()})
    T = pd.DataFrame(rows)
    order = {"규칙": 0, "가벼운 모델": 1, "실습 LSTM": 2}
    corder = ["발전량만", "발전량만(오전)", "지난 날씨(재분석, T-1 까지)", "지난 날씨(ASOS, T-2 까지)", "지난 날씨(ASOS, T-1 까지)", "실제 예보 24h", "실제 예보 48h", "실제 예보(구름양)", "모의 예보",
              "상한(재분석)", "상한(ASOS)", "상한(ASOS 일조)"]
    T["o1"] = T["cond"].map({c: i for i, c in enumerate(corder)})
    T["o2"] = T["family"].map(order)
    T = T.sort_values(["o1", "o2", "RMSE"]).drop(columns=["o1", "o2"]).reset_index(drop=True)
    T.to_csv(HERE / f"t4_table_{win}.csv", index=False)
    pd.DataFrame(per).to_csv(HERE / f"t4_per_seed_{win}.csv", index=False)
    print(f"\n{'=' * 20} 구간 {win}: {a} ~ {b}, {len(idx)}일, 하루 평균 {y.mean():.1f} kWh | 7일 평균 {ref['기준 7일 평균']:.2f}, 20일 평균 {ref['기준 20일 평균']:.2f}, 규칙C {ref['규칙C 7일 효율(24h 예보) x 24h 예보']:.2f}")
    show = T[["cond", "family", "label", "n_seed", "RMSE", "sd", "min", "max", "WAPE", "bias_pct", "MAE_cap50", "MAE_cap55", "vs_mean7", "vs_mean20", "vs_ruleC", "future"]].copy()
    for c in ["RMSE", "sd", "min", "max", "WAPE", "bias_pct", "MAE_cap50", "MAE_cap55"]:
        show[c] = show[c].round(2)
    for c in ["vs_mean7", "vs_mean20", "vs_ruleC"]:
        show[c] = show[c].round(3)
    print(show.to_string(index=False))
    return T


for w in ("C898", "P264", "O205"):
    table(w)

# 자기 구간에서의 재현 확인(보고된 값과 대조)
print("\n" + "=" * 20, "보고된 값의 재현 확인(각자의 평가 구간)")
CHK = [
    ("사전 D2 Ridge: 발전량만", "T1_958", 75.64), ("사전 D2 부스팅: (가) 발전량+대상일 실제 일사량", "T1_958", 30.96),
    ("사전 D2 Ridge: (다-A) 일사량 24시간 전 예보 대입, 보정", "T1_958", 50.74), ("사전 D2 부스팅: (다-B) 일사량 24시간 전 예보로 직접 학습 [2022-07~2023-07]", "T1_958", 46.73),
    ("기준 7일 평균", "T1_958", 80.98), ("기준 20일 평균", "T1_958", 80.62), ("기준 어제 값", "T1_958", 92.45),
    ("규칙C 7일 효율(24h 예보) x 24h 예보", "T1_958", 46.40), ("규칙B 7일 효율(최신 실행분) x 24h 예보", "T1_958", 43.94), ("규칙A 7일 효율(재분석) x 보정한 24h 예보", "T1_958", 48.55),
    ("규칙 상한 7일 효율(재분석) x 대상일 실제 재분석", "T1_958", 33.4),
    ("보완 LSTM(T1): 발전량+상수(2013~ 학습)", "T1_958", 77.42), ("보완 LSTM(T1): 발전량+24h 일사량 예보(358개 학습)", "T1_958", 44.92),
    ("보완 LSTM(T1): 발전량+대상일 실제 재분석 일사량(2013~ 학습)", "T1_958", 30.75),
    ("ASOS LSTM(분할 A): 발전량만(둘째 열 0)", "A946", 78.5), ("ASOS LSTM(분할 A): 발전량+대상일 실제 광양 일조", "A946", 27.6),
    ("ASOS LSTM(분할 A): 모의 예보: 일조 잡음 2시간으로 학습", "A946", 44.6), ("ASOS LSTM(분할 A): 모의 예보: 일조 3분위 범주로 학습", "A946", 42.1),
    ("기준 7일 평균", "A946", 81.66), ("기준 20일 평균", "A946", 81.45), ("기준 20일 평균", "P946", 81.58), ("기준 7일 평균", "P946", 81.73),
    ("ASOS LSTM(실습 절차): hadong_upload.csv, 발전량+광양 일사량(T-2 까지)", "P946", 79.17), ("ASOS LSTM(실습 절차): forecast_proxy.csv, 발전량+대상일 실제 광양 일사량", "P946", 23.06),
    ("보완 LSTM(서빙 교체): ASOS 실제로 학습, T-1·T 칸을 24h 예보로 서빙", "P946", 45.20), ("보완 LSTM(서빙 교체): ASOS 실제로 학습, T 칸 48h 예보·T-1 칸 24h 예보", "P946", 51.67),
    ("보완 LSTM(실습 절차): 예보 업로드 파일(발전량+24h 예보)", "P264", 42.84), ("보완 LSTM(실습 절차): 예보 업로드 파일의 발전량만(둘째 열 상수)", "P264", 68.66),
]
for lab, w, rep in CHK:
    a, b = WIN[w]
    idx = Y.loc[a:b].index
    vals = []
    for seed, s in P[lab].items():
        s = s.reindex(idx)
        if s.notna().all():
            vals.append(metr(Y.loc[idx].to_numpy(), s.to_numpy())["RMSE"])
    got = np.mean(vals) if vals else np.nan
    print(f"  {lab[:62]:62s} {w:7s} 보고 {rep:6.2f} | 다시 계산 {got:6.2f} (시드 {len(vals)}) | 차 {got - rep:+.2f}")
