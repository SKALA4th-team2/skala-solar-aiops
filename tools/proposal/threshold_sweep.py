"""감시 임계값을 낮추거나 높이면 오경보와 놓침이 어떻게 달라지는지 센다.

배포 시점에 고정한 기준선(2025-02-28 까지 365일)을 두고, 2025년의 주 단위 시작일 37개에서
"그날부터 발전량이 배율만큼 낮아졌다"고 가정한 배치의 성능 지표 편차를 계산한다.
배율 1.0 은 아무것도 넣지 않은 배치이므로, 그 배치가 임계값을 넘으면 오경보다.

둘째로, 날마다 "가장 최근 21일"로 판정한다고 할 때 수준이 내려간 날부터 처음 임계값을 넘는 날까지
며칠이 걸리는지를 센다. 위의 배치는 내려간 뒤의 21일이 모두 찬 경우(내려간 날로부터 41일 뒤)이고,
이쪽은 내려간 직후부터 날마다 본 경우다.

성능 지표는 대상일의 관측 날씨로 계산하는 사후 값이다. 예측 시점에는 받을 수 없다.
임계값과 날짜를 같은 자료에서 보고 고른 표본 안 계산이며, 독립된 기간의 검증이 아니다.

실행 (저장소 루트에서):
    python tools/proposal/threshold_sweep.py
결과: docs/proposal/evidence/threshold_sweep.json, threshold_sweep.txt
"""
import json

import numpy as np
import pandas as pd

from common import EVIDENCE, baseline_365, gate, injection_scan, load_daily_full, pi

BASELINE_END = "2025-02-28"
STARTS = pd.date_range("2025-03-08", "2025-11-15", freq="7D")
FACTORS = [1.0, 0.95, 0.915, 0.90, 0.86, 0.80, 0.70]
THRESHOLDS = [-0.05, -0.075, -0.10, -0.125]
MIN_VALID = 15

a = load_daily_full()
x, e = a["gen_kwh"], a["pi_expected_kwh"]
_, _, valid = gate(x, e)
baseline, n_base = baseline_365(x, e, valid, BASELINE_END)
scan = injection_scan(x, e, FACTORS, STARTS, baseline, MIN_VALID)

rows = []
for f in FACTORS:
    devs = scan[f]
    judged = [d for d in devs if d is not None]
    row = {
        "factor": f,
        "drop_pct": round((1 - f) * 100, 1),
        "batches": len(devs),
        "not_judged": len(devs) - len(judged),
        "median_deviation_pct": round(float(np.median(judged)) * 100, 2) if judged else None,
        "min_deviation_pct": round(min(judged) * 100, 2) if judged else None,
        "max_deviation_pct": round(max(judged) * 100, 2) if judged else None,
        "flagged": {},
    }
    for t in THRESHOLDS:
        k = sum(1 for d in judged if d < t)
        row["flagged"][f"{t * 100:g}%"] = {"count": k, "pct_of_all_batches": round(100 * k / len(devs), 1)}
    rows.append(row)

result = {
    "what": "고정 기준선에서 임계값별로 넘는 배치의 수. 배율 1.0 은 오경보, 그 밖은 감지",
    "note": "성능 지표는 대상일 관측 날씨로 계산하는 사후 값이다. 표본 안 계산이다. 배치 37개라 한 개가 2.7%p 다",
    "baseline": {"end": BASELINE_END, "days": 365, "value": round(baseline, 6), "valid_days": n_base},
    "starts": {"first": str(STARTS[0].date()), "last": str(STARTS[-1].date()), "every_days": 7, "n": len(STARTS)},
    "target_window": "시작일 + 20일 ~ 시작일 + 40일 (21일)",
    "min_valid_days": MIN_VALID,
    "rows": rows,
    "per_start_deviation_pct": {
        str(f): [None if d is None else round(d * 100, 2) for d in scan[f]] for f in FACTORS
    },
    "start_dates": [str(s.date()) for s in STARTS],
}
# ---------------------------------------------------------------- 날마다 판정했을 때 걸리는 날 수
LIMIT = -0.075
HORIZON = 40          # 마지막 시작일(2025-11-15)에서 40일 뒤가 자료의 끝(2025-12-31) 안이다
DAILY_FACTORS = [1.0, 0.915, 0.86]


def first_alarm_day(st, f):
    """st 부터 발전량에 f 를 곱하고, 날마다 그날까지의 21일로 판정한다. 처음 임계값을 넘는 날이 st 를 1일째로 세어 며칠째인지."""
    xx = x.copy()
    xx.loc[st:] *= f
    _, _, vv = gate(xx, e)
    for k in range(HORIZON + 1):
        d = st + pd.Timedelta(days=k)
        value, n = pi(xx, e, vv, d - pd.Timedelta(days=20), d)
        if n >= MIN_VALID and value / baseline - 1 < LIMIT:
            return k + 1
    return None


daily = {}
for f in DAILY_FACTORS:
    days = [first_alarm_day(st, f) for st in STARTS]
    hit = sorted(d for d in days if d is not None)
    daily[str(f)] = {
        "first_alarm_day_per_start": days,
        "alarm_within_21_days": sum(1 for d in hit if d <= 21),
        "alarm_within_28_days": sum(1 for d in hit if d <= 28),
        "alarm_within_41_days": len(hit),
        "no_alarm_within_41_days": len(days) - len(hit),
        "median_day_among_alarmed": float(np.median(hit)) if hit else None,
    }

# 재학습을 거는 조건: 배치 41행의 앞 20일(입력 구간)과 뒤 21일(판정 구간)이 모두 임계값 아래일 때
RETRAIN_HORIZON = 45


def both_windows_day(st, f):
    """st 부터 f 를 곱하고 날마다 최근 41일을 본다. 앞 20일과 뒤 21일의 편차가 함께 임계값 아래인 첫날이 며칠째인지."""
    xx = x.copy()
    xx.loc[st:] *= f
    _, _, vv = gate(xx, e)
    for k in range(RETRAIN_HORIZON + 1):
        d = st + pd.Timedelta(days=k)
        if d > x.index.max() or pd.isna(e.get(d, np.nan)):
            return None
        tail, n1 = pi(xx, e, vv, d - pd.Timedelta(days=20), d)
        head, n2 = pi(xx, e, vv, d - pd.Timedelta(days=40), d - pd.Timedelta(days=21))
        if n1 >= MIN_VALID and n2 >= MIN_VALID and tail / baseline - 1 < LIMIT and head / baseline - 1 < LIMIT:
            return k + 1
    return None


retrain = {}
for f in DAILY_FACTORS:
    days = [both_windows_day(st, f) for st in STARTS]
    hit = sorted(d for d in days if d is not None)
    retrain[str(f)] = {"first_day_per_start": days, "reached": len(hit), "not_reached": len(days) - len(hit),
                       "min_day": hit[0] if hit else None, "median_day": float(np.median(hit)) if hit else None, "max_day": hit[-1] if hit else None}

# 시연 배치(시작 2025-06-21)의 앞 20일과 뒤 21일
demo = {}
st = pd.Timestamp("2025-06-21")
for f in (1.0, 0.86):
    xx = x.copy()
    xx.loc[st:] *= f
    _, _, vv = gate(xx, e)
    head, n2 = pi(xx, e, vv, st, st + pd.Timedelta(days=19))
    tail, n1 = pi(xx, e, vv, st + pd.Timedelta(days=20), st + pd.Timedelta(days=40))
    demo[str(f)] = {"input_20_days": {"deviation_pct": round((head / baseline - 1) * 100, 1), "valid_days": n2},
                    "target_21_days": {"deviation_pct": round((tail / baseline - 1) * 100, 1), "valid_days": n1}}

# 변화가 없어도 41일 안에 경고가 켜지는 시작일을 뺀 "깨끗한" 시작일만으로 다시 센다
clean_idx = [i for i, d in enumerate(daily["1.0"]["first_alarm_day_per_start"]) if d is None]
for f in DAILY_FACTORS:
    days = [daily[str(f)]["first_alarm_day_per_start"][i] for i in clean_idx]
    hit = sorted(d for d in days if d is not None)
    daily[str(f)]["clean_starts"] = {
        "n": len(days), "first": str(STARTS[clean_idx[0]].date()), "last": str(STARTS[clean_idx[-1]].date()),
        "alarm_within_21_days": sum(1 for d in hit if d <= 21), "alarm_within_28_days": sum(1 for d in hit if d <= 28),
        "alarm_within_41_days": len(hit), "median_day_among_alarmed": float(np.median(hit)) if hit else None,
        "starts_without_alarm": [str(STARTS[i].date()) for i in clean_idx if daily[str(f)]["first_alarm_day_per_start"][i] is None],
    }

# 변화가 없을 때 날마다 판정하면 며칠이 임계값 아래인가
_, _, v0 = gate(x, e)
dates = pd.date_range("2025-03-08", "2025-12-31")
below, judged = [], 0
for d in dates:
    value, n = pi(x, e, v0, d - pd.Timedelta(days=20), d)
    if n >= MIN_VALID:
        judged += 1
        below.append(bool(value / baseline - 1 < LIMIT))
    else:
        below.append(False)
runs = sum(1 for i, b in enumerate(below) if b and (i == 0 or not below[i - 1]))
daily["no_change_daily"] = {"period": [str(dates[0].date()), str(dates[-1].date())], "days": len(dates), "judged_days": judged,
                            "days_below_limit": int(sum(below)), "episodes": runs,
                            "dates_below_limit": [str(d.date()) for d, b in zip(dates, below) if b]}
result["daily_judgement"] = {
    "what": "날마다 그날까지의 21일로 판정할 때, 수준이 내려간 날(1일째)부터 처음 임계값을 넘는 날까지의 날 수",
    "limit_pct": LIMIT * 100, "window_days": 21, "min_valid_days": MIN_VALID, "horizon_days": HORIZON + 1,
    "note": "관측 날씨가 하루 늦게 공개되므로 실제로 알게 되는 날은 하루 뒤다. 변화가 없어도 임계값을 넘는 날이 있으므로, 배율 1.0 의 줄과 견줘 읽는다",
    "by_factor": daily,
}
result["retrain_condition"] = {
    "what": "배치 41행의 앞 20일과 뒤 21일의 편차가 함께 임계값 아래인 첫날. 내려간 날을 1일째로 센다",
    "horizon_days": RETRAIN_HORIZON + 1, "by_factor": retrain, "demo_batch_2025-06-21": demo,
}

(EVIDENCE / "threshold_sweep.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

t = [
    f"기준선: {BASELINE_END} 까지 365일의 성능 지표 {baseline:.6f} (유효일 {n_base}일)",
    f"배치: {STARTS[0].date()} ~ {STARTS[-1].date()} 의 7일 간격 시작일 {len(STARTS)}개, 대상은 시작일+20 ~ +40 의 21일, 유효일 {MIN_VALID}일 이상일 때만 판정",
    "",
    "배율(하락)      판정 불가   편차 중앙값   " + "   ".join(f"{t_ * 100:>6g}% 미만" for t_ in THRESHOLDS),
]
for r in rows:
    cells = "   ".join(f"{v['count']:>3d}개 {v['pct_of_all_batches']:>5.1f}%" for v in r["flagged"].values())
    med = "     -" if r["median_deviation_pct"] is None else f"{r['median_deviation_pct']:>+6.1f}%"
    t.append(f"{r['factor']:<5} ({r['drop_pct']:>4.1f}%)   {r['not_judged']:>3d}개      {med}      {cells}")
t += ["", f"날마다 그날까지의 21일로 판정할 때 (임계값 {LIMIT * 100:g}%, 시작일 {len(STARTS)}개, 내려간 날을 1일째로 셈)",
      "배율(하락)      21일 안   28일 안   41일 안   41일 안에 없음   넘은 것의 중앙값"]
for f in DAILY_FACTORS:
    v = daily[str(f)]
    med = "    -" if v["median_day_among_alarmed"] is None else f"{v['median_day_among_alarmed']:>4.0f}일째"
    t.append(f"{f:<5} ({(1 - f) * 100:>4.1f}%)   {v['alarm_within_21_days']:>4d}개    {v['alarm_within_28_days']:>4d}개    {v['alarm_within_41_days']:>4d}개       {v['no_alarm_within_41_days']:>4d}개          {med}")
c0 = daily["1.0"]["clean_starts"]
t += ["", f"변화가 없어도 41일 안에 경고가 켜지는 시작일 {len(STARTS) - c0['n']}개를 뺀 {c0['n']}개({c0['first']} ~ {c0['last']})만으로 세면",
      "배율(하락)      21일 안   28일 안   41일 안   넘은 것의 중앙값   41일 안에 넘지 못한 시작일"]
for f in DAILY_FACTORS[1:]:
    v = daily[str(f)]["clean_starts"]
    med = "    -" if v["median_day_among_alarmed"] is None else f"{v['median_day_among_alarmed']:>4.0f}일째"
    miss = ", ".join(v["starts_without_alarm"]) or "없음"
    t.append(f"{f:<5} ({(1 - f) * 100:>4.1f}%)   {v['alarm_within_21_days']:>4d}개    {v['alarm_within_28_days']:>4d}개    {v['alarm_within_41_days']:>4d}개       {med}        {miss}")
nc = daily["no_change_daily"]
t.append(f"변화가 없을 때 {nc['period'][0]} ~ {nc['period'][1]} 의 {nc['days']}일을 날마다 판정하면 임계값 아래인 날이 {nc['days_below_limit']}일, {nc['episodes']}번의 구간이다")
t += ["", f"재학습의 조건(배치 41행의 앞 20일과 뒤 21일이 함께 임계값 아래)이 처음 채워지는 날. 시작일 {len(STARTS)}개, {RETRAIN_HORIZON + 1}일 안",
      "배율(하락)      채워짐   채워지지 않음   가장 이른 날   가운데   가장 늦은 날"]
for f in DAILY_FACTORS:
    v = retrain[str(f)]
    if v["reached"]:
        t.append(f"{f:<5} ({(1 - f) * 100:>4.1f}%)   {v['reached']:>4d}개       {v['not_reached']:>4d}개        {v['min_day']:>3d}일째    {v['median_day']:>3.0f}일째     {v['max_day']:>3d}일째")
    else:
        t.append(f"{f:<5} ({(1 - f) * 100:>4.1f}%)   {v['reached']:>4d}개       {v['not_reached']:>4d}개")
for f, v in demo.items():
    t.append(f"시연 배치(2025-06-21 ~ 07-31), 배율 {f}: 앞 20일 {v['input_20_days']['deviation_pct']:+.1f}% (유효 {v['input_20_days']['valid_days']}일), "
             f"뒤 21일 {v['target_21_days']['deviation_pct']:+.1f}% (유효 {v['target_21_days']['valid_days']}일)")
(EVIDENCE / "threshold_sweep.txt").write_text("\n".join(t) + "\n", encoding="utf-8")
print("\n".join(t))
