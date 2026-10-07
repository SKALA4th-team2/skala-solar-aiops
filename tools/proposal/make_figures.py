"""기획서에 넣는 그래프를 저장소의 자료에서 직접 그린다.

그림마다 단위, 기간, 출처, 조건을 그림 안에 적는다. 그림에 적힌 숫자는 docs/proposal/evidence/figures_data.json 에도 남긴다.
색은 파랑(#2563eb)과 주황(#d97706) 두 가지만 구분용으로 쓰고, 회색은 참고용 막대에만 쓴다(색각 이상에서의 구분은 검증 스크립트로 확인했다).

실행 (저장소 루트에서, pandas 와 matplotlib 이 있는 파이썬으로):
    python tools/proposal/make_figures.py
"""
import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from common import (ASSETS, DATASETS, EVIDENCE, baseline_365, baselines_for_targets, gate, injection_scan, load_daily_full,
                    load_raw_generation, load_upload, pi, practice_split, rmse)

BLUE, AMBER, GRAY, INK, MUTED, GRID = "#2563eb", "#d97706", "#9ca3af", "#111827", "#6b7280", "#e5e7eb"
plt.rcParams.update({
    "font.family": "Apple SD Gothic Neo", "axes.unicode_minus": False, "font.size": 10.5,
    "axes.edgecolor": "#d1d5db", "axes.linewidth": 0.8, "axes.spines.top": False, "axes.spines.right": False,
    "xtick.color": MUTED, "ytick.color": MUTED, "axes.labelcolor": MUTED, "text.color": INK,
    "figure.facecolor": "white", "axes.facecolor": "white", "savefig.dpi": 200,
})
ASSETS.mkdir(parents=True, exist_ok=True)
DATA = {}


def finish(fig, name, note, title=None):
    if title:
        fig.text(0.012, 0.985, title, fontsize=12.5, fontweight="bold", color=INK, va="top", ha="left")
    fig.text(0.012, 0.012, note, fontsize=8.2, color=MUTED, va="bottom", ha="left", linespacing=1.45)
    fig.savefig(ASSETS / name, bbox_inches="tight", pad_inches=0.18)
    plt.close(fig)
    print("저장:", name)


full = load_daily_full()
x, e = full.gen_kwh, full.pi_expected_kwh
out, hold, valid = gate(x, e)

# ------------------------------------------------------------------ 1. 성능 지표의 흐름
z = x.clip(0.5 * e, 1.5 * e)
num = z.where(valid, 0).rolling(30, min_periods=1).sum()
den = e.where(valid, 0).rolling(30, min_periods=1).sum()
cnt = valid.astype(int).rolling(30, min_periods=1).sum()
p30 = (num / den).where(cnt >= 21)["2019-01-01":"2025-12-31"]

ev21, ev24 = pd.Timestamp("2021-05-18"), pd.Timestamp("2024-03-22")
lv = {}
for key, ref in (("2021", ev21), ("2024", ev24)):
    pre, _ = pi(x, e, valid, ref - pd.Timedelta(days=365), ref - pd.Timedelta(days=1))
    post, _ = pi(x, e, valid, ref, ref + pd.Timedelta(days=364))
    lv[key] = (pre, post, (post / pre - 1) * 100)

fig, ax = plt.subplots(figsize=(9.6, 4.6))
fig.subplots_adjust(bottom=0.24, top=0.88)
ax.plot(p30.index, p30.values, color=BLUE, lw=1.6)
for key, ref, label in (("2021", ev21, "2021년 5월 중순\n출력 수준 하락 (원인 미확인)"), ("2024", ev24, "2024-03-22 (추정)\n인버터 교체 무렵")):
    pre, post, pct = lv[key]
    ax.axvline(ref, color=INK, lw=0.9, ls=(0, (4, 3)))
    ax.hlines(pre, ref - pd.Timedelta(days=365), ref, color=AMBER, lw=2.0)
    ax.hlines(post, ref, ref + pd.Timedelta(days=364), color=AMBER, lw=2.0)
    ax.annotate(label, (ref, 1.115), xytext=(6, 0), textcoords="offset points", fontsize=9, va="top", ha="left")
    ax.annotate(f"앞 365일 {pre:.3f} → 뒤 365일 {post:.3f} ({pct:+.1f}%)", (ref, 0.775), xytext=(6, 0), textcoords="offset points",
                fontsize=9, color=INK, va="center", ha="left")
ax.set_ylim(0.70, 1.12)
ax.set_xlim(pd.Timestamp("2018-09-01"), pd.Timestamp("2026-09-01"))
ax.set_ylabel("성능 지표 (실제 ÷ 기대 발전량)")
ax.yaxis.grid(True, color=GRID, lw=0.8)
ax.set_axisbelow(True)
ax.xaxis.set_major_locator(mdates.YearLocator())
ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
ax.plot([], [], color=BLUE, lw=1.6, label="성능 지표, 최근 30일")
ax.plot([], [], color=AMBER, lw=2.0, label="사건 앞뒤 365일의 수준")
ax.legend(loc="lower left", frameon=False, fontsize=9, ncol=1)
finish(fig, "pi_timeline.png", title="날씨를 보정해도 남는 출력 수준의 변화: 하동하수처리장 태양광, 2019 ~ 2025년", note=
       "자료: datasets/hadong_daily_full.csv (발전 실적은 한국남부발전 공개 자료, 날씨는 기상청 광양 관측). 기대 발전량은 2013 ~ 2014년 자료로 맞춘 식의 값이다.\n"
       "최근 30일 가운데 유효일이 21일 이상일 때만 그렸다. 그날의 관측 날씨로 계산하는 사후 지표이고 예측 입력이 아니다. 여름마다 낮아지는 모양은 계절 차이다.")
DATA["pi_timeline"] = {"window_days": 30, "min_valid_days": 21, "period": "2019-01-01 ~ 2025-12-31",
                       "level_2021-05-18": {"pre365": round(lv["2021"][0], 4), "post365": round(lv["2021"][1], 4), "change_pct": round(lv["2021"][2], 1)},
                       "level_2024-03-22": {"pre365": round(lv["2024"][0], 4), "post365": round(lv["2024"][1], 4), "change_pct": round(lv["2024"][2], 1)}}

# ------------------------------------------------------------------ 2. 같은 시험 구간의 예측 오차
u = load_upload()
close, vol = u.Close.values, u.Volume.values
_, _, test_t = practice_split(len(u))
y = close[test_t]
base = {k: rmse(y, p) for k, p in baselines_for_targets(close, vol, test_t).items()}
measured = None
reg = EVIDENCE / "registry" / "registry_3-after-hadong-train.json"
if reg.exists():
    measured = json.loads(reg.read_text(encoding="utf-8"))["runs"][-1]["metrics"]["rmse"]
gate_kwh = min(0.8 * base["7일 평균"], 1.05 * base["규칙C"])
bars = [("어제 값 그대로", base["어제 값"], GRAY), ("최근 20일 평균", base["20일 평균"], GRAY), ("최근 7일 평균", base["7일 평균"], GRAY),
        ("규칙C: 최근 7일 효율 × 내일 예보\n(학습 없음)", base["규칙C"], AMBER)]
if measured is not None:
    bars.append(("실습 LSTM: 발전량 + 내일 일사량 예보\n(저장소 코드로 직접 학습, 시드 42)", measured, BLUE))
fig, ax = plt.subplots(figsize=(9.6, 4.4))
fig.subplots_adjust(left=0.34, bottom=0.27, top=0.89)
ypos = np.arange(len(bars))[::-1]
ax.barh(ypos, [b[1] for b in bars], color=[b[2] for b in bars], height=0.56)
for yy, (name, val, _) in zip(ypos, bars):
    ax.text(val + 1.2, yy, f"{val:.1f}", va="center", fontsize=10, color=INK, zorder=5,
            bbox=dict(facecolor="white", edgecolor="none", pad=1.5))
ax.set_yticks(ypos)
ax.set_yticklabels([b[0] for b in bars], color=INK, fontsize=9.6)
ax.axvline(gate_kwh, color=INK, lw=1.0, ls=(0, (4, 3)), zorder=3)
ax.text(gate_kwh + 1.2, len(bars) - 0.36, f"제안하는 상대 게이트: {gate_kwh:.1f}kWh 이하", fontsize=9, ha="left", va="center")
ax.set_ylim(-0.6, len(bars) - 0.1)
ax.set_xlim(0, 96)
ax.set_xlabel("RMSE (하루 kWh, 낮을수록 좋음)")
ax.xaxis.grid(True, color=GRID, lw=0.8)
ax.set_axisbelow(True)
ax.tick_params(axis="y", length=0)
finish(fig, "quality_test264.png", title="같은 264일에서 견준 다음 날 발전량 예측 오차", note=
       "자료: datasets/hadong_upload_forecast_jma.csv. 시험 구간 2025-06-09 ~ 2026-02-27 (실습 코드의 뒤 20% 분할, 3 ~ 5월이 없다). 시험 구간의 하루 평균 발전량은 194.2kWh.\n"
       "모든 예측은 대상일 전날까지의 발전량과 대상일에 대한 하루 전 예보만 쓴다. 게이트 문턱은 '7일 평균의 80% 이하이면서 규칙C 의 105% 이하'를 이 구간에서 계산한 값이고, 팀이 확정한 값이 아니다.")
DATA["quality_test264"] = {"period": "2025-06-09 ~ 2026-02-27", "n": int(len(test_t)), "rmse_kwh": {k: round(v, 2) for k, v in base.items()},
                           "measured_lstm_seed42_rmse_kwh": measured, "proposed_relative_gate_kwh": round(gate_kwh, 2)}

# ------------------------------------------------------------------ 3. 실제 사건과 인위 주입에서의 성능 지표 편차
b21, _ = baseline_365(x, e, valid, "2021-04-01")
n21, _ = pi(x, e, valid, "2021-04-22", "2021-05-12")
d21, _ = pi(x, e, valid, "2021-06-07", "2021-06-27")
b25, _ = baseline_365(x, e, valid, "2025-02-28")
st = pd.Timestamp("2025-06-21")
dev25 = {}
for f in (1.0, 0.86):
    xx = x.copy()
    xx.loc[st:] *= f
    _, _, vv = gate(xx, e)
    val, _ = pi(xx, e, vv, st + pd.Timedelta(days=20), st + pd.Timedelta(days=40))
    dev25[f] = (val / b25 - 1) * 100
rows = [("실제 사건 (2021년)\n하락 전 배치, 대상 04-22 ~ 05-12", (n21 / b21 - 1) * 100, BLUE),
        ("실제 사건 (2021년)\n하락 뒤 배치, 대상 06-07 ~ 06-27", (d21 / b21 - 1) * 100, AMBER),
        ("인위 주입 (2025년)\n주입 없음, 대상 07-11 ~ 07-31", dev25[1.0], BLUE),
        ("인위 주입 (2025년)\n발전량 × 0.86, 대상 07-11 ~ 07-31", dev25[0.86], AMBER)]
fig, ax = plt.subplots(figsize=(9.6, 4.2))
fig.subplots_adjust(left=0.33, bottom=0.29, top=0.84)
ypos = np.arange(len(rows))[::-1]
ax.barh(ypos, [r[1] for r in rows], color=[r[2] for r in rows], height=0.56)
for yy, (_, val, _) in zip(ypos, rows):
    ax.text(val - 0.35, yy, f"{val:+.1f}%", va="center", ha="right", fontsize=10, color=INK)
ax.set_yticks(ypos)
ax.set_yticklabels([r[0] for r in rows], color=INK, fontsize=9.4)
ax.axvline(-7.5, color=INK, lw=1.0, ls=(0, (4, 3)))
ax.text(-7.5 - 0.25, len(rows) - 0.36, "제안하는 한도 -7.5%", fontsize=9, ha="right", va="center")
ax.set_ylim(-0.6, len(rows) - 0.1)
ax.set_xticks([-20, -15, -10, -5, 0])
ax.set_xticklabels(["-20%", "-15%", "-10%", "-5%", "0%"])
ax.axvline(0, color="#d1d5db", lw=0.8)
ax.set_xlim(-20, 1.5)
ax.set_xlabel("기준선 대비 성능 지표의 편차")
ax.xaxis.grid(True, color=GRID, lw=0.8)
ax.set_axisbelow(True)
ax.tick_params(axis="y", length=0)
ax.plot([], [], color=BLUE, lw=6, label="변화가 없는 배치")
ax.plot([], [], color=AMBER, lw=6, label="수준이 내려간 배치")
ax.legend(loc="lower left", bbox_to_anchor=(-0.47, 1.0), frameon=False, fontsize=9, ncol=2, handlelength=1.2)
finish(fig, "pi_deviation_scenes.png", title="21일 배치의 성능 지표가 기준선에서 벗어난 정도", note=
       f"자료: datasets/hadong_daily_full.csv. 기준선은 배포 시점 직전 365일의 성능 지표다 (2021년 장면은 2021-04-01 까지 {b21:.4f}, 2025년 장면은 2025-02-28 까지 {b25:.4f}).\n"
       "성능 지표는 그날의 관측 날씨로 계산하는 사후 지표다. 2025년 장면은 2025-06-21 부터의 발전량에 0.86 을 곱한 인위적인 값이다.\n"
       "한도 -7.5% 는 조사에서 전체 기간을 보고 고른 제안값이고, 장면의 날짜도 결과를 보고 골랐다. 독립된 성능 평가가 아니다.")
DATA["pi_deviation_scenes"] = {"baseline_2021-04-01": round(b21, 4), "baseline_2025-02-28": round(b25, 6),
                               "deviation_pct": {"2021_normal": round((n21 / b21 - 1) * 100, 1), "2021_drift": round((d21 / b21 - 1) * 100, 1),
                                                 "2025_no_injection": round(dev25[1.0], 1), "2025_x0.86": round(dev25[0.86], 1)},
                               "proposed_limit_pct": -7.5}

# ------------------------------------------------------------------ 4. 입력 센서의 수준 변화 (적량 ÷ 광양)
jr = pd.read_csv(DATASETS / "jeokryang_daily.csv", parse_dates=["date"]).set_index("date")["gsr_mj"]
okd = (full.stop_day == 0) & (full.pi_outage.fillna(0) == 0)
both = pd.DataFrame({"jr": jr.reindex(full.index), "gy": full.gy_gsr})[okd].dropna()
grp = both.groupby(pd.Grouper(freq="MS"))
ratio = (grp.jr.sum() / grp.gy.sum()).where(grp.jr.count() >= 15)
ratio = ratio["2013-01-01":"2025-12-31"]
fig, ax = plt.subplots(figsize=(9.6, 4.2))
fig.subplots_adjust(bottom=0.26, top=0.88)
ax.plot(ratio.index, ratio.values, color=BLUE, lw=1.4, marker="o", ms=3.2)
ax.axvspan(pd.Timestamp("2018-04-11"), pd.Timestamp("2021-10-20"), color="#f3f4f6", lw=0)
ax.text(pd.Timestamp("2020-01-15"), 0.93, "적량 자료 없음\n2018-04-11 ~ 2021-10-20", ha="center", va="top", fontsize=9, color=MUTED)
for d, label, dy, side in ((pd.Timestamp("2014-08-09"), "2014-08\n+34%", 0.90, "right"), (pd.Timestamp("2015-05-03"), "2015-05\n-13%", 0.55, "left"),
                           (pd.Timestamp("2024-02-01"), "2024-02\n+30%", 0.87, "left")):
    ax.axvline(d, color=INK, lw=0.9, ls=(0, (4, 3)))
    ax.text(d + pd.Timedelta(days=25 if side == "left" else -25), dy, label, fontsize=8.8, va="center", ha=side)
ax.set_ylim(0.40, 0.96)
ax.set_ylabel("적량 일사량 ÷ 광양 일사량 (월 합계의 비)")
ax.yaxis.grid(True, color=GRID, lw=0.8)
ax.set_axisbelow(True)
ax.xaxis.set_major_locator(mdates.YearLocator())
ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
finish(fig, "sensor_ratio.png", title="입력 자료도 변한다: 가까운 관측소(적량면) 일사량 센서의 수준", note=
       "자료: datasets/jeokryang_daily.csv, datasets/hadong_daily_full.csv 의 광양 관측 일사량. 두 곳 모두 값이 있는 날이 15일 이상인 달만 그렸다.\n"
       "점선은 앞뒤 30일 비율의 중앙값이 가장 크게 달라진 날이다. 같은 기간에 광양은 재분석 자료 대비 0.97 ~ 1.02 로 일정했다. 센서의 교체나 수리 기록은 확인하지 못했다.")
DATA["sensor_ratio"] = {"months_plotted": int(ratio.notna().sum()), "min": round(float(ratio.min()), 2), "max": round(float(ratio.max()), 2)}

# ------------------------------------------------------------------ 5. 하루 발전이 끝나는 시각
raw = load_raw_generation()
hours = [str(h) for h in range(1, 25)]
h = raw.loc[raw["총량(kw)"] >= 1, hours]
cum = h.cumsum(axis=1).sum(axis=0) / h.values.sum() * 100
fig, ax = plt.subplots(figsize=(9.6, 4.0))
fig.subplots_adjust(bottom=0.27, top=0.88)
ax.plot(range(1, 25), cum.values, color=BLUE, lw=1.8, marker="o", ms=3.4)
for hh, label, ytext in ((10, "제도의 1차 제출 마감 10시", 6), (17, "제도의 2차\n제출 마감 17시", 60), (20, "이 과제의 예측 시각\n20시 이후", 60)):
    ax.axvline(hh, color=INK, lw=0.9, ls=(0, (4, 3)))
    ax.text(hh + 0.25, ytext, f"{label}\n그때까지 {cum[str(hh)]:.1f}%", fontsize=8.8, va="center", ha="left")
ax.set_xticks(range(1, 25))
ax.set_xlim(0.5, 24.5)
ax.set_ylim(-3, 108)
ax.set_xlabel("시각 (h 는 h-1 시부터 h 시까지 쌓인 발전량)")
ax.set_ylabel("그 시각까지 끝난 하루 발전량 (%)")
ax.yaxis.grid(True, color=GRID, lw=0.8)
ax.set_axisbelow(True)
finish(fig, "hourly_completion.png", title="하루 발전량은 몇 시에 끝나는가", note=
       f"자료: datasets/raw/data_15043409.csv 의 시간대별 값. 2013-01-01 ~ 2026-02-28 가운데 하루 합계가 1kWh 이상인 {len(h):,}일을 발전량으로 가중해 합쳤다.\n"
       "시간 열의 구간은 공식 정의가 없어 값의 관계에서 추정한 것이다. 발전이 끝나는 시각과 계량 자료를 받을 수 있는 시각은 다르다. 20시 이후에 실적을 받는다는 것은 이 과제의 가정이다.")
DATA["hourly_completion"] = {"days": int(len(h)), "cum_pct": {f"{k}시": round(float(cum[str(k)]), 2) for k in (10, 14, 17, 19, 20)}}

# ------------------------------------------------------------------ 6. 임계값에 따른 오경보와 감지
starts = pd.date_range("2025-03-08", "2025-11-15", freq="7D")
limits = [-5.0, -7.5, -10.0, -12.5]
scan = injection_scan(x, e, [1.0, 0.915, 0.86], starts, b25)


def flagged_pct(devs, limit):
    return 100 * sum(1 for d in devs if d is not None and d * 100 < limit) / len(devs)


series = [(0.86, "발전량을 14% 낮춘 배치 (감지)", BLUE, "-", "o"), (0.915, "발전량을 8.5% 낮춘 배치 (감지)", BLUE, (0, (4, 2)), "s"),
          (1.0, "그대로 둔 배치 (오경보)", AMBER, "-", "o")]
fig, ax = plt.subplots(figsize=(9.6, 4.9))
fig.subplots_adjust(right=0.74, bottom=0.37, top=0.87)
xs = np.arange(len(limits))
sweep = {}
for f, label, color, ls, marker in series:
    ys = [flagged_pct(scan[f], lim) for lim in limits]
    sweep[str(f)] = [round(v, 1) for v in ys]
    ax.plot(xs, ys, color=color, lw=1.9, ls=ls, marker=marker, ms=5.5, mfc="white" if marker == "s" else color, mec=color, mew=1.4)
    ax.text(xs[-1] + 0.12, ys[-1], label, fontsize=9.2, va="center", ha="left", color=INK)
    ax.annotate(f"{ys[1]:.1f}%", (xs[1], ys[1]), xytext=(7, 7), textcoords="offset points", fontsize=9.2, color=INK,
                bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none"))
ax.axvline(1, color=INK, lw=0.9, ls=(0, (4, 3)), zorder=0)
ax.text(1, 108, "제안하는 한도 -7.5%", fontsize=9, ha="center", va="bottom")
ax.set_xticks(xs)
ax.set_xticklabels(["-5%\n(민감)", "-7.5%", "-10%", "-12.5%\n(둔감)"])
ax.set_xlim(-0.3, 3.15)
ax.set_ylim(-4, 106)
ax.set_yticks([0, 25, 50, 75, 100])
ax.set_yticklabels(["0%", "25%", "50%", "75%", "100%"])
ax.set_xlabel("경보를 내는 한도 (기준선 대비 성능 지표의 편차가 이 값 아래일 때)")
ax.set_ylabel("한도를 넘은 배치의 비율")
ax.yaxis.grid(True, color=GRID, lw=0.8)
ax.set_axisbelow(True)
finish(fig, "threshold_tradeoff.png", title="한도를 바꾸면 오경보와 놓침이 함께 움직인다", note=
       f"자료: datasets/hadong_daily_full.csv. 기준선은 2025-02-28 까지 365일로 고정했다({b25:.3f}). 2025-03-08 ~ 11-15 의 7일 간격 시작일 {len(starts)}개에서\n"
       "그날부터 발전량에 배율을 곱하고 시작일+20 ~ +40 의 21일을 판정했다. 배치가 37개라 한 개가 2.7%p 다. 성능 지표는 대상일의 관측 날씨로\n"
       "계산하는 사후 값이다. 한도와 기간을 같은 자료에서 보고 고른 표본 안 계산이며, 다른 해로 검증한 값이 아니다.")
DATA["threshold_tradeoff"] = {"baseline_2025-02-28": round(b25, 6), "batches": int(len(starts)), "limits_pct": limits, "flagged_pct_by_factor": sweep}

(EVIDENCE / "figures_data.json").write_text(json.dumps(DATA, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps(DATA, ensure_ascii=False))
