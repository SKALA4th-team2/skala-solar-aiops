"""t3_03: 학습 없는 규칙으로 날씨 출처만 바꿔 본다(LSTM 을 다시 돌리지 않고 출처의 효과만 확인).

규칙: 예측[T] = (발전량 T-7..T-1 합) / (날씨 T-7..T-1 합) x 날씨[T]
 - '실제 값' 줄은 대상일 T 의 실제 날씨를 쓴다. 예측 시점(대상일 전날)에는 받을 수 없는 값이므로 상한이다.
 - '예보' 줄은 대상일 칸에 24시간 전(또는 48시간 전) 예보를 쓴다. 효율(앞 7일)도 같은 예보 열로 구하면 미래 정보가 없다.
 - '효율은 관측(T-2 까지), 대상일은 예보' 줄은 운영에서 실제로 조합할 수 있는 형태다(ASOS 일자료는 다음 날 오전에 올라온다).
평가 구간: (A) 보완 조사 1 의 T1 958일(2023-07-17 ~ 2026-02-28), (B) 공통 898일(2023-07-17 ~ 2025-12-30, 광양 ASOS 가 있는 구간),
          (C) 업로드 파일 실습 시험 구간 264일(2025-06-09 ~ 2026-02-27), (D) 그 가운데 ASOS 가 있는 205일(2025-06-09 ~ 2025-12-30)
"""
import numpy as np
import pandas as pd

import t3_common as c

pd.set_option("display.width", 250)
full = c.load_full()
arc = c.load_archive()
sat, _ = c.load_himawari()
pr = c.load_prevruns_daily()
gsm = c.load_gsm_cloud_daily(7, 18)
df = full
for x in [arc, sat, pr, gsm]:
    df = df.merge(x, on="date", how="left")
df = df.sort_values("date").reset_index(drop=True)
assert (df["date"].diff().dropna() == pd.Timedelta(days=1)).all()
y = df["gen_kwh"]


def rule(eff_col, tgt_col, eff_lag=1, win=7):
    """효율 = 발전량 합 / 날씨 합. eff_lag=1 이면 T-7..T-1, eff_lag=2 이면 T-8..T-2 를 쓴다."""
    gsum = y.shift(eff_lag).rolling(win, min_periods=win).sum()
    wsum = df[eff_col].shift(eff_lag).rolling(win, min_periods=win).sum()
    return (gsum / wsum * df[tgt_col]).clip(lower=0)


def rmse(p, m):
    mm = m & p.notna()
    e = p[mm] - y[mm]
    return float(np.sqrt((e ** 2).mean())), float(e.abs().sum() / y[mm].sum() * 100), float(e.sum() / y[mm].sum() * 100), int(mm.sum())


PERIODS = {
    "A T1 958일(2023-07-17~2026-02-28)": (df["date"] >= "2023-07-17") & (df["date"] <= "2026-02-28"),
    "B 공통 898일(2023-07-17~2025-12-30)": (df["date"] >= "2023-07-17") & (df["date"] <= "2025-12-30"),
    "C 실습 시험 264일(2025-06-09~2026-02-27)": (df["date"] >= "2025-06-09") & (df["date"] <= "2026-02-27"),
    "D 그중 ASOS 있는 205일(2025-06-09~2025-12-30)": (df["date"] >= "2025-06-09") & (df["date"] <= "2025-12-30"),
}

# 직선 보정(예보 -> ASOS 수준). 평가 구간 이전(2022-07-03 ~ 2023-07-16)으로만 맞춘다.
cal = (df["date"] >= "2022-07-03") & (df["date"] <= "2023-07-16") & df["fc1_gsr"].notna() & df["gy_gsr"].notna()
b1, b0 = np.polyfit(df.loc[cal, "fc1_gsr"], df.loc[cal, "gy_gsr"], 1)
df["fc1_as_asos"] = b0 + b1 * df["fc1_gsr"]
print(f"예보→ASOS 직선 보정(2022-07-03~2023-07-16, {int(cal.sum())}일): ASOS = {b0:.3f} + {b1:.3f} x 예보")

PRED = [
    # (이름, 예측, 대상일의 실제 값을 쓰는가, 예측 시점에 받을 수 없는 그 밖의 값)
    ("7일 평균(날씨 없음)", y.shift(1).rolling(7, min_periods=7).mean(), False, ""),
    ("20일 평균(날씨 없음)", y.shift(1).rolling(20, min_periods=20).mean(), False, ""),
    ("어제 값", y.shift(1), False, ""),
    ("[상한] 광양 ASOS 일사량 실제 값", rule("gy_gsr", "gy_gsr"), True, "T, T-1 관측"),
    ("[상한] 광양 ASOS 경사면 27도 환산 실제 값", rule("gy_gsr_tilt27", "gy_gsr_tilt27"), True, "T, T-1 관측"),
    ("[상한·참고] 광양 ASOS 일조 시간 실제 값(일조 0시간인 날에 예측이 0 이 되어 비율 규칙에는 맞지 않는다)", rule("gy_ss", "gy_ss"), True, "T, T-1 관측"),
    ("[상한] Open-Meteo 보관 자료 실제 값", rule("om_gsr", "om_gsr"), True, "T 재분석"),
    ("[상한] 히마와리 위성 실제 값", rule("sat_gsr", "sat_gsr"), True, "T 위성"),
    ("[상한] JMA 최신 실행분(분석값에 가까움)", rule("fc0_gsr", "fc0_gsr"), True, "T 분석값"),
    ("[예보] 24시간 전 예보(효율도 예보로)", rule("fc1_gsr", "fc1_gsr"), False, ""),
    ("[예보] 48시간 전 예보(효율도 48시간 전 예보로)", rule("fc2_gsr", "fc2_gsr"), False, ""),
    ("[예보] 효율은 24시간 전 예보, 대상일은 48시간 전", rule("fc1_gsr", "fc2_gsr"), False, ""),
    ("[예보] 효율은 ASOS 관측(T-8~T-2), 대상일은 보정한 24시간 전 예보", rule("gy_gsr", "fc1_as_asos", eff_lag=2), False, ""),
    ("[받을 수 없음] 효율은 ASOS 관측(T-7~T-1), 대상일은 보정한 24시간 전 예보", rule("gy_gsr", "fc1_as_asos", eff_lag=1), False, "T-1 관측"),
    ("[예보] 효율은 위성(T-7~T-1), 대상일은 24시간 전 예보(보정 없음)", rule("sat_gsr", "fc1_gsr"), False, "T-1 위성(받을 수 있는 시점 확인하지 못함)"),
]

rows = []
for pname, pm in PERIODS.items():
    print(f"\n== {pname}: 하루 평균 {y[pm].mean():.1f}kWh, 일수 {int(pm.sum())}")
    for name, p, upper, note in PRED:
        r, wape, bias, n = rmse(p, pm)
        if n == 0:
            continue
        flag = "대상일 실제 값 사용" if upper else ("예측 시점에 받을 수 없는 값 포함: " + note if note else "미래 정보 없음")
        print(f"  {name:48s} RMSE {r:6.2f}  합계 오차율 {wape:5.2f}%  치우침 {bias:+5.2f}%  n={n:4d}  | {flag}")
        rows.append(dict(period=pname, method=name, rmse=round(r, 2), wape_pct=round(wape, 2), bias_pct=round(bias, 2), n=n, flag=flag))
pd.DataFrame(rows).to_csv(c.HERE / "t3_03_rule_table.csv", index=False)

print("\n== 같은 날 집합으로 맞춘 비교(B 구간에서 위성·ASOS·보관 자료·예보가 모두 있는 날)")
pm = PERIODS["B 공통 898일(2023-07-17~2025-12-30)"]
keep = pm.copy()
sel = [x for x in PRED if x[0].startswith("[상한]") or x[0].startswith("[예보] 24") or x[0].startswith("7일")]
for _, p, _, _ in sel:
    keep &= p.notna()
print("  일수:", int(keep.sum()))
for name, p, upper, note in sel:
    r, wape, bias, n = rmse(p, keep)
    print(f"  {name:48s} RMSE {r:6.2f}  합계 오차율 {wape:5.2f}%  치우침 {bias:+5.2f}%")

print("\n== 구름양 예보(GSM)는 비율 규칙에 바로 넣을 수 없어 한 줄 회귀로 본다(참고)")
print("   발전량[T] = a + b x (7일 평균) + c x 구름양 예보[T], 학습 2016-01-23 ~ 2023-07-16, 평가 A·B")
tr = (df["date"] >= "2016-01-23") & (df["date"] <= "2023-07-16") & (df["stop_day"] == 0)
ma7 = y.shift(1).rolling(7, min_periods=7).mean()
for col, lab in [("gsm_cloud_fc1", "GSM 하루 전 구름양 예보"), ("fc1_gsr", "MSM 24시간 전 일사량 예보(학습 2022-07-10 ~ 2023-07-16)")]:
    m = tr & df[col].notna() & ma7.notna()
    if col == "fc1_gsr":
        m = (df["date"] >= "2022-07-10") & (df["date"] <= "2023-07-16") & df[col].notna() & ma7.notna()
    X = np.column_stack([np.ones(m.sum()), ma7[m], df.loc[m, col]])
    beta = np.linalg.lstsq(X, y[m], rcond=None)[0]
    p = (beta[0] + beta[1] * ma7 + beta[2] * df[col]).clip(lower=0)
    for pname in list(PERIODS)[:2]:
        r, wape, bias, n = rmse(p, PERIODS[pname])
        print(f"  {lab:50s} {pname[:8]} RMSE {r:6.2f} 합계 오차율 {wape:5.2f}% 치우침 {bias:+5.2f}% (학습 {int(m.sum())}일)")
