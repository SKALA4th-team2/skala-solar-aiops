"""기획서에 적는 데이터 관련 수치를 저장소의 파일에서 직접 다시 계산한다.

서버나 모델을 돌리지 않는다. 결과는 docs/proposal/evidence/data_checks.json 과 data_checks.txt 에 남긴다.

실행 (저장소 루트에서, pandas 가 있는 파이썬으로):
    python tools/proposal/data_checks.py
"""
import datetime as dt
import json

import numpy as np
import pandas as pd

from common import (DATASETS, EVIDENCE, SEQ_LEN, baseline_365, baselines_for_targets, bias_pct, gate, load_daily_full,
                    load_raw_generation, load_upload, pi, practice_split, rmse, total_error_pct)

R = {"computed_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
     "versions": {"pandas": pd.__version__, "numpy": np.__version__}}
lines = []


def say(s=""):
    lines.append(s)
    print(s)


raw = load_raw_generation()
full = load_daily_full()
hours = [str(h) for h in range(1, 25)]

# ---------------------------------------------------------------- A. 업로드 파일
say("A. 업로드 파일의 모양과 원본 대조")
fc1 = pd.read_csv(DATASETS / "raw" / "wx_prevruns_daily.csv", parse_dates=["date"]).set_index("date")["shortwave_radiation_previous_day1"]
R["upload_files"] = {}
for name in ("hadong_upload_forecast_jma.csv", "hadong_upload.csv", "hadong_upload_forecast_proxy.csv"):
    u = load_upload(name)
    d = u["Date"]
    info = {
        "rows": len(u), "start": str(d.min().date()), "end": str(d.max().date()),
        "date_gaps": int((d.diff().dropna().dt.days != 1).sum()), "duplicates": int(d.duplicated().sum()),
        "missing_cells": int(u[["Close", "Volume"]].isna().sum().sum()),
        "close_min": float(u.Close.min()), "close_max": float(u.Close.max()),
        "volume_min": float(u.Volume.min()), "volume_max": float(u.Volume.max()),
        "close_zero_rows": int((u.Close == 0).sum()), "stop_rows": int(u.Stop.sum()),
        "close_vs_raw_max_abs_diff": float((u.Close.values - raw["총량(kw)"].reindex(d).values).__abs__().max()),
        "volume_fraction_non_integer": float((u.Volume % 1 != 0).mean()),
    }
    if "jma" in name:
        info["volume_vs_next_day_forecast_max_abs_diff"] = float(np.nanmax(np.abs(u.Volume.values - fc1.reindex(d + pd.Timedelta(days=1)).values)))
        c, v = u.Close.values, u.Volume.values
        info["corr_volume_d_with_close_d_plus_1"] = float(np.corrcoef(v[:-1], c[1:])[0, 1])
        info["corr_volume_d_with_close_d"] = float(np.corrcoef(v, c)[0, 1])
    R["upload_files"][name] = info
    say(f"  {name}: {info['rows']}행 {info['start']} ~ {info['end']}, 날짜 공백 {info['date_gaps']}, 중복 {info['duplicates']}, 빈 값 {info['missing_cells']}, "
        f"Close {info['close_min']} ~ {info['close_max']}, Volume {info['volume_min']} ~ {info['volume_max']}, Close 가 0 인 행 {info['close_zero_rows']}, "
        f"원본 총량과의 최대 차이 {info['close_vs_raw_max_abs_diff']:.2e}, Volume 이 소수인 행의 비율 {info['volume_fraction_non_integer']:.3f}")
j = R["upload_files"]["hadong_upload_forecast_jma.csv"]
say(f"  예보 파일의 Volume[d] 와 d+1 일 예보 원본의 최대 차이 {j['volume_vs_next_day_forecast_max_abs_diff']:.2e}")
say(f"  예보 파일에서 Volume[d] 와 Close[d+1] 의 상관 {j['corr_volume_d_with_close_d_plus_1']:.3f}, 같은 행끼리의 상관 {j['corr_volume_d_with_close_d']:.3f}")

# ---------------------------------------------------------------- B. 실습 코드의 창과 분할
say("\nB. 실습 코드와 같은 창·분할 (예보 업로드 파일)")
u = load_upload()
close, vol, dates = u.Close.values, u.Volume.values, u.Date
n_samples, train_t, test_t = practice_split(len(u))
R["practice_split"] = {
    "rows": len(u), "samples": n_samples, "train_samples": len(train_t), "test_samples": len(test_t),
    "train_target_start": str(dates[train_t[0]].date()), "train_target_end": str(dates[train_t[-1]].date()),
    "test_target_start": str(dates[test_t[0]].date()), "test_target_end": str(dates[test_t[-1]].date()),
    "test_months_present": sorted({int(m) for m in dates[test_t].dt.month}),
    "window_close_rows": f"T-{SEQ_LEN} ~ T-1", "window_volume_forecast_target_days": f"T-{SEQ_LEN - 1} ~ T",
    "scaler_minmax_same_when_fit_on_train_rows_only": bool(
        close[:train_t[-1] + 1].min() == close.min() and close[:train_t[-1] + 1].max() == close.max()
        and vol[:train_t[-1] + 1].min() == vol.min() and vol[:train_t[-1] + 1].max() == vol.max()),
}
# 표본마다 창과 정답의 날짜를 직접 확인한다. 표본 i 의 창은 행 i ~ i+19, 정답은 행 i+20 이다(data/features.py 의 build_sequences).
dv = dates.values
first_in_window, last_in_window, target_day = dv[: len(u) - SEQ_LEN], dv[SEQ_LEN - 1: len(u) - 1], dv[SEQ_LEN:]
day = np.timedelta64(1, "D")
R["practice_split"]["window_checks"] = {
    "samples_checked": int(len(target_day)),
    "target_is_the_day_after_window_end_for_all": bool(((target_day - last_in_window) == day).all()),
    "window_is_20_consecutive_days_for_all": bool(((last_in_window - first_in_window) == 19 * day).all()),
    "last_train_target_before_first_test_target": bool(dv[train_t[-1]] < dv[test_t[0]]),
}
s = R["practice_split"]
say(f"  행 {s['rows']}, 표본 {s['samples']}, 학습 {s['train_samples']}문제(정답일 {s['train_target_start']} ~ {s['train_target_end']}), "
    f"시험 {s['test_samples']}문제(정답일 {s['test_target_start']} ~ {s['test_target_end']})")
say(f"  시험 구간에 들어 있는 달: {s['test_months_present']}")
say(f"  입력 창: 발전량은 {s['window_close_rows']}, 예보는 대상일 {s['window_volume_forecast_target_days']} 치")
w = s["window_checks"]
say(f"  표본 {w['samples_checked']}개를 하나씩 확인: 정답일이 창의 마지막 날 바로 다음 날인가 {w['target_is_the_day_after_window_end_for_all']}, "
    f"창이 이어진 20일인가 {w['window_is_20_consecutive_days_for_all']}, 학습의 마지막 정답일이 시험의 첫 정답일보다 앞인가 {w['last_train_target_before_first_test_target']}")
say(f"  스케일러를 학습 행만으로 맞춰도 최소·최대가 같은가: {s['scaler_minmax_same_when_fit_on_train_rows_only']}")

# ---------------------------------------------------------------- C. 같은 시험 구간의 기준 예측과 게이트 문턱
say("\nC. 같은 시험 구간(264일)의 학습 없는 기준 예측")
y = close[test_t]
base = baselines_for_targets(close, vol, test_t)
R["baselines_test264"] = {k: {"rmse_kwh": round(rmse(y, p), 4), "total_error_pct": round(total_error_pct(y, p), 2), "bias_pct": round(bias_pct(y, p), 2)}
                          for k, p in base.items()}
R["baselines_test264"]["actual_mean_kwh"] = round(float(y.mean()), 2)
for k, v in R["baselines_test264"].items():
    if isinstance(v, dict):
        say(f"  {k}: RMSE {v['rmse_kwh']:.2f}kWh, 합계 오차율 {v['total_error_pct']:.1f}%, 치우침 {v['bias_pct']:+.1f}%")
say(f"  시험 구간의 하루 평균 발전량 {R['baselines_test264']['actual_mean_kwh']}kWh")
r7, rc = R["baselines_test264"]["7일 평균"]["rmse_kwh"], R["baselines_test264"]["규칙C"]["rmse_kwh"]
R["relative_gate_test264"] = {"0.80_x_7day_mean_rmse": round(0.8 * r7, 2), "1.05_x_ruleC_rmse": round(1.05 * rc, 2),
                              "threshold_kwh": round(min(0.8 * r7, 1.05 * rc), 2)}
g = R["relative_gate_test264"]
say(f"  상대 게이트(제안)의 문턱: 7일 평균의 80% = {g['0.80_x_7day_mean_rmse']}kWh, 규칙C 의 105% = {g['1.05_x_ruleC_rmse']}kWh, 둘 다 만족하려면 {g['threshold_kwh']}kWh 이하")
reg = EVIDENCE / "registry" / "registry_3-after-hadong-train.json"
if reg.exists():
    runs = json.loads(reg.read_text(encoding="utf-8"))["runs"]
    measured = runs[-1]["metrics"]["rmse"]
    R["measured_lstm_test264_seed42_rmse_kwh"] = measured
    say(f"  이번에 저장소 코드로 직접 학습한 실습 LSTM(시드 42)의 같은 구간 RMSE: {measured}kWh "
        f"(7일 평균의 {measured / r7 * 100:.1f}%, 규칙C 의 {measured / rc * 100:.1f}%, 현재 코드의 게이트 4.00 대비 {measured / 4.0:.1f}배)")

# ---------------------------------------------------------------- D. 성능 지표
say("\nD. 성능 지표(실제 ÷ 그날 관측 날씨로 계산한 기대 발전량). 대상일의 관측을 쓰는 사후 지표다")
x, e = full.gen_kwh, full.pi_expected_kwh
out, hold, valid = gate(x, e)
R["gate_counts"] = {"days": len(full), "expected_available_days": int(e.notna().sum()), "zero_generation_days": int((x == 0).sum()),
                    "outage_days": int(out.sum()), "hold_days": int(hold.sum()), "valid_days": int(valid.sum()),
                    "matches_file_columns": bool((valid == full.pi_valid.astype(bool)).all())}
c = R["gate_counts"]
say(f"  전체 {c['days']}일, 기대 발전량이 있는 날 {c['expected_available_days']}일, 발전량 0 인 날 {c['zero_generation_days']}일, 정지 {c['outage_days']}일, 보류 {c['hold_days']}일, 유효 {c['valid_days']}일 (파일의 열과 일치: {c['matches_file_columns']})")

b21, n21 = baseline_365(x, e, valid, "2021-04-01")
normal, n_n = pi(x, e, valid, "2021-04-22", "2021-05-12")
drift, n_d = pi(x, e, valid, "2021-06-07", "2021-06-27")
R["pi_2021"] = {"baseline_365d_to_2021-04-01": round(b21, 4), "baseline_valid_days": n21,
                "normal_batch_target_2021-04-22_05-12": {"pi": round(normal, 4), "valid_days": n_n, "deviation_pct": round((normal / b21 - 1) * 100, 1)},
                "drift_batch_target_2021-06-07_06-27": {"pi": round(drift, 4), "valid_days": n_d, "deviation_pct": round((drift / b21 - 1) * 100, 1)},
                "threshold_pi_at_-7.5pct": round(b21 * 0.925, 4)}
p = R["pi_2021"]
say(f"  2021년: 기준선(2021-04-01 까지 365일) {p['baseline_365d_to_2021-04-01']}, 정상 배치 {p['normal_batch_target_2021-04-22_05-12']}, 하락 배치 {p['drift_batch_target_2021-06-07_06-27']}")
ref = pd.Timestamp("2021-05-18")
pre, _ = pi(x, e, valid, ref - pd.Timedelta(days=365), ref - pd.Timedelta(days=1))
post, _ = pi(x, e, valid, ref, ref + pd.Timedelta(days=364))
ref24 = pd.Timestamp("2024-03-22")
pre24, _ = pi(x, e, valid, ref24 - pd.Timedelta(days=365), ref24 - pd.Timedelta(days=1))
post24, _ = pi(x, e, valid, ref24, ref24 + pd.Timedelta(days=364))
R["level_changes"] = {"2021-05-18_pre365_vs_post365_pct": round((post / pre - 1) * 100, 1), "2021_pre": round(pre, 4), "2021_post": round(post, 4),
                      "2024-03-22_pre365_vs_post365_pct": round((post24 / pre24 - 1) * 100, 1), "2024_pre": round(pre24, 4), "2024_post": round(post24, 4)}
lv = R["level_changes"]
say(f"  수준 변화(앞 365일 대 뒤 365일): 2021-05-18 기준 {lv['2021-05-18_pre365_vs_post365_pct']:+.1f}% ({lv['2021_pre']} → {lv['2021_post']}), "
    f"2024-03-22 기준 {lv['2024-03-22_pre365_vs_post365_pct']:+.1f}% ({lv['2024_pre']} → {lv['2024_post']})")

# ---------------------------------------------------------------- E. 2025년 주입 장면 (고정 기준선)
say("\nE. 2025년 인위 주입 장면. 주입 시작 2025-06-21, 판정 대상 2025-07-11 ~ 07-31")
fixed, n_fixed = baseline_365(x, e, valid, "2025-02-28")
st = pd.Timestamp("2025-06-21")
R["injection_2025"] = {"fixed_baseline_365d_to_2025-02-28": round(fixed, 6), "fixed_baseline_valid_days": n_fixed, "start": str(st.date()),
                       "target": "2025-07-11 ~ 2025-07-31", "batch_rows": "2025-06-21 ~ 2025-07-31 (41행)", "factors": {}}
for f in (1.0, 0.86, 0.80, 0.70):
    xx = x.copy()
    xx.loc[st:] *= f
    _, hh, vv = gate(xx, e)
    val, n = pi(xx, e, vv, st + pd.Timedelta(days=20), st + pd.Timedelta(days=40))
    per_start, _ = pi(xx, e, vv, st - pd.Timedelta(days=365), st - pd.Timedelta(days=1))
    R["injection_2025"]["factors"][str(f)] = {
        "pi": round(val, 4), "valid_days_of_21": n, "judgeable(valid>=15)": bool(n >= 15),
        "deviation_vs_fixed_baseline_pct": round((val / fixed - 1) * 100, 1),
        "deviation_vs_per_start_baseline_pct": round((val / per_start - 1) * 100, 1),
        "hold_days_in_target": int(hh.loc[st + pd.Timedelta(days=20): st + pd.Timedelta(days=40)].sum()),
    }
say(f"  고정 기준선(2025-02-28 까지 365일): {R['injection_2025']['fixed_baseline_365d_to_2025-02-28']} (유효 {n_fixed}일)")
for f, v in R["injection_2025"]["factors"].items():
    say(f"  배율 {f}: 성능 지표 {v['pi']}, 유효 {v['valid_days_of_21']}/21일, 고정 기준선 대비 {v['deviation_vs_fixed_baseline_pct']:+.1f}%, 주입 직전 365일 기준선 대비 {v['deviation_vs_per_start_baseline_pct']:+.1f}%, 대상 구간의 보류일 {v['hold_days_in_target']}")
tail = load_upload()
tail = tail[tail.Date <= "2025-07-31"].tail(41)
R["injection_2025"]["last_41_rows_of_file_cut_at_2025-07-31"] = {"start": str(tail.Date.min().date()), "end": str(tail.Date.max().date()), "rows": len(tail)}
say(f"  2025-07-31 에서 자른 예보 파일의 마지막 41행: {tail.Date.min().date()} ~ {tail.Date.max().date()}")

# ---------------------------------------------------------------- F. 설비 이상 후보 하루
day = pd.Timestamp("2025-03-31")
R["equipment_day_2025-03-31"] = {"actual_kwh": float(x[day]), "expected_kwh": round(float(e[day]), 1), "ratio": round(float(x[day] / e[day]), 2),
                                 "outage": bool(out[day]), "low_day(<70%)": bool(e[day] >= 80 and x[day] < 0.7 * e[day]),
                                 "one_day_alert(<50%)": bool(e[day] >= 80 and x[day] < 0.5 * e[day]), "hold": bool(hold[day])}
say(f"\nF. 설비 이상 후보의 예 2025-03-31: {R['equipment_day_2025-03-31']}")

# ---------------------------------------------------------------- G. 하루 발전이 몇 시에 끝나는가
ok = raw["총량(kw)"] >= 1
h = raw.loc[ok, hours]
cum = h.cumsum(axis=1).sum(axis=0) / h.values.sum() * 100
R["hourly_completion_pct"] = {f"{k}시까지": round(float(cum[str(k)]), 2) for k in (9, 10, 14, 16, 17, 18, 19, 20, 21)}
R["hourly_completion_days"] = int(ok.sum())
say(f"\nG. 하루 발전량이 그 시각까지 끝난 비율(발전량 가중, 하루 합계 1kWh 이상 {int(ok.sum())}일): {R['hourly_completion_pct']}")

# ---------------------------------------------------------------- H. 요청 값의 범위를 정할 때 쓸 수치
# 대기권 밖 수평면이 하루에 받는 일사량. 땅에 닿는 일사량은 이 값을 넘을 수 없다.
LAT = np.radians(35.05885)                    # 발전소의 공식 좌표(위도)
doy = np.arange(1, 366)
decl = np.radians(23.44) * np.sin(2 * np.pi * (284 + doy) / 365)
e0 = 1 + 0.033 * np.cos(2 * np.pi * doy / 365)
ws = np.arccos(-np.tan(LAT) * np.tan(decl))
h0 = (86400 / np.pi) * 1361 * e0 * (np.cos(LAT) * np.cos(decl) * np.sin(ws) + ws * np.sin(LAT) * np.sin(decl)) / 1e6   # MJ/m2
asos = load_upload("hadong_upload.csv")
R["value_ranges"] = {
    "generation_kwh": {"capacity_kw": 55, "capacity_x_24h_kwh": 55 * 24, "observed_max_kwh": float(raw["총량(kw)"].max()),
                       "observed_min_kwh": float(raw["총량(kw)"].min())},
    "irradiance_mj_m2": {"forecast_file_max": float(load_upload().Volume.max()), "forecast_file_min": float(load_upload().Volume.min()),
                         "observed_max_gwangyang": float(asos.Volume.max()),
                         "extraterrestrial_daily_max_at_35.06N": round(float(h0.max()), 1),
                         "extraterrestrial_daily_min_at_35.06N": round(float(h0.min()), 1)},
}
v = R["value_ranges"]
say(f"\nH. 요청 값의 범위를 정할 때 쓸 수치")
say(f"  하루 발전량: 원본의 최솟값 {v['generation_kwh']['observed_min_kwh']}kWh, 최댓값 {v['generation_kwh']['observed_max_kwh']}kWh. 용량 55kW 가 24시간 내내 돌면 {v['generation_kwh']['capacity_x_24h_kwh']}kWh")
say(f"  하루 일사량: 예보 파일 {v['irradiance_mj_m2']['forecast_file_min']} ~ {v['irradiance_mj_m2']['forecast_file_max']}MJ/m2, 광양 관측의 최댓값 {v['irradiance_mj_m2']['observed_max_gwangyang']}MJ/m2. "
    f"이 위도(35.06N)의 대기권 밖 수평면 일사량은 연중 {v['irradiance_mj_m2']['extraterrestrial_daily_min_at_35.06N']} ~ {v['irradiance_mj_m2']['extraterrestrial_daily_max_at_35.06N']}MJ/m2 (태양상수 1361W/m2 로 계산)")

(EVIDENCE / "data_checks.json").write_text(json.dumps(R, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
(EVIDENCE / "data_checks.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
