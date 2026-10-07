"""검토자: hadong_upload_forecast_jma.csv 를 원자료와 따로 쓴 코드로 전 행 대조한다. 분석자의 모듈을 import 하지 않는다."""
import csv
import numpy as np
import pandas as pd

BASE = "/private/tmp/claude-501/-Users-psm-workspace-skala-aiops/695898c3-d8ce-4232-8761-3e7f55247d4a/scratchpad"
RAW = BASE + "/solar/data_15043409.csv"
WX = BASE + "/solar/d2r/wx_prevruns_daily.csv"
WXH = BASE + "/solar/d2r/wx_prevruns_hourly.csv"
FILE = BASE + "/merged/gap1/hadong_upload_forecast_jma.csv"

# 원자료
raw = pd.read_csv(RAW, encoding="cp949")
print("원자료 열:", list(raw.columns)[:8], "행", len(raw), "호기 값:", raw["호기"].unique()[:5])
raw["d"] = pd.to_datetime(raw["년월일"])
print("원자료 날짜 중복:", int(raw["d"].duplicated().sum()), "범위", raw["d"].min().date(), "~", raw["d"].max().date())
gen = dict(zip(raw["d"], raw["총량(kw)"].astype(float)))
# 총량이 시간별 합과 같은지
hc = [str(i) for i in range(1, 25)]
hs = raw[hc].apply(pd.to_numeric, errors="coerce").sum(axis=1)
print("총량 - 시간별 합: 최대 절대차", float((raw["총량(kw)"] - hs).abs().max()), " 차가 0.01 넘는 날", int(((raw["총량(kw)"] - hs).abs() > 0.01).sum()))

wx = pd.read_csv(WX)
wx["d"] = pd.to_datetime(wx["date"])
fc1 = dict(zip(wx["d"], wx["shortwave_radiation_previous_day1"]))
fc2 = dict(zip(wx["d"], wx["shortwave_radiation_previous_day2"]))
fc0 = dict(zip(wx["d"], wx["shortwave_radiation"]))

# 시간값에서 하루 합계를 내가 다시 만든다
hh = pd.read_csv(WXH)
hh["t"] = pd.to_datetime(hh["time"])
hh["d"] = hh["t"].dt.normalize()
g = hh.groupby("d")["shortwave_radiation_previous_day1"]
mine = (g.sum(min_count=24) * 3600 / 1e6)
cnt = g.count()
mine = mine[cnt == 24]
dd = [abs(mine[d] - fc1[d]) for d in mine.index]
print(f"시간값 24칸 합 x3600/1e6 대 일별 파일: {len(dd)}일, 최대차 {max(dd):.2e}; 일별 파일의 값 있는 날 {int(wx['shortwave_radiation_previous_day1'].notna().sum())}")
# 밤 시간(21~04시) 값이 0 인지: 시간대가 한국 시각인지 확인
night = hh[(hh["t"].dt.hour >= 21) | (hh["t"].dt.hour <= 4)]["shortwave_radiation_previous_day1"].dropna()
noon = hh[(hh["t"].dt.hour >= 11) & (hh["t"].dt.hour <= 14)]["shortwave_radiation_previous_day1"].dropna()
print(f"밤(21~04시) 예보 일사량 최대 {night.max():.1f} W/m2, 한낮(11~14시) 평균 {noon.mean():.1f} W/m2 -> 시간 축은 한국 시각")

# 파일 전 행 대조
rows = list(csv.DictReader(open(FILE, encoding="utf-8")))
print("파일 열:", list(rows[0].keys()), "행", len(rows), rows[0]["Date"], "~", rows[-1]["Date"])
n_close_bad = n_vol_bad = n_vol_same = n_vol_prev = n_vol2 = 0
maxdv = 0.0
prev = None
gaps = 0
for r in rows:
    d = pd.Timestamp(r["Date"])
    if prev is not None and (d - prev).days != 1:
        gaps += 1
    prev = d
    c, v = float(r["Close"]), float(r["Volume"])
    if c != gen[d]:
        n_close_bad += 1
    t = fc1[d + pd.Timedelta(days=1)]
    dv = abs(v - t)
    maxdv = max(maxdv, dv)
    if dv > 5.1e-5:
        n_vol_bad += 1
    if abs(v - fc1.get(d, np.nan)) <= 5.1e-5:
        n_vol_same += 1          # 같은 날 예보와 우연히 같은 행
    if abs(v - fc1.get(d + pd.Timedelta(days=2), np.nan)) <= 5.1e-5:
        n_vol_prev += 1
    if abs(v - fc2.get(d + pd.Timedelta(days=1), np.nan)) <= 5.1e-5:
        n_vol2 += 1
print(f"날짜 간격이 하루가 아닌 곳 {gaps}곳")
print(f"Close 가 원자료의 같은 날 총량과 다른 행: {n_close_bad} / {len(rows)}")
print(f"Volume 이 '다음 날(d+1)의 24시간 전 예보'와 다른 행(반올림 4자리 허용): {n_vol_bad} / {len(rows)}, 최대차 {maxdv:.2e}")
print(f"Volume 이 같은 날(d)의 24시간 전 예보와 같은 행: {n_vol_same}, d+2 일 예보와 같은 행: {n_vol_prev}, d+1 일의 48시간 전 예보와 같은 행: {n_vol2}")
print("Stop 합:", sum(int(r["Stop"]) for r in rows), " Close 최소:", min(float(r["Close"]) for r in rows), " Close<10 인 행:", [(r["Date"], r["Close"]) for r in rows if float(r["Close"]) < 10])
print("빈 문자열 칸:", sum(1 for r in rows for k in r if r[k] == ""))

# 실습 코드의 창(옮겨 적지 않고 정의대로 내가 다시 씀): 표본 i 의 입력 = 행 i..i+19, 정답 = 행 i+20 의 Close
N = len(rows)
D = [pd.Timestamp(r["Date"]) for r in rows]
n_s = N - 20
split = int(n_s * 0.8)
leak_target_in_input = 0
wx_last_is_T = 0
wx_max_offset = []
for i in range(n_s):
    T = D[i + 20]
    in_dates = D[i:i + 20]
    if T in in_dates:
        leak_target_in_input += 1
    # 날씨 칸의 출처 날짜 = 행 날짜 + 1
    src = [x + pd.Timedelta(days=1) for x in in_dates]
    wx_max_offset.append((max(src) - T).days)
    if src[-1] == T:
        wx_last_is_T += 1
    assert in_dates[-1] == T - pd.Timedelta(days=1) and in_dates[0] == T - pd.Timedelta(days=20)
print(f"표본 {n_s}개 (학습 {split}: 정답일 {D[20].date()} ~ {D[20+split-1].date()}, 시험 {n_s-split}: 정답일 {D[20+split].date()} ~ {D[-1].date()})")
print(f"정답일의 발전량(Close)이 입력 창에 든 표본: {leak_target_in_input}개")
print(f"날씨 칸의 출처 날짜가 정답일을 넘는 표본: {sum(1 for o in wx_max_offset if o > 0)}개, 마지막 날씨 칸의 출처가 정답일(T)인 표본: {wx_last_is_T}개 (모든 표본에서 날씨 칸 = T-19 ~ T 의 24시간 전 예보)")

# 시차 상관
c = np.array([float(r["Close"]) for r in rows]); v = np.array([float(r["Volume"]) for r in rows])
for k in (-1, 0, 1, 2):
    if k > 0: a, b = c[k:], v[:-k]
    elif k < 0: a, b = c[:k], v[-k:]
    else: a, b = c, v
    print(f"상관 Close[d{k:+d}] 대 Volume[d]: {np.corrcoef(a, b)[0,1]:+.3f}")
# 스케일러 범위: 전체 행 대 학습 구간 행
tr_rows = rows[:20 + split]
print("전체 행 min/max:", c.min(), c.max(), v.min(), v.max(), "| 학습 구간 행(앞", 20 + split, "행):", min(float(r["Close"]) for r in tr_rows), max(float(r["Close"]) for r in tr_rows), min(float(r["Volume"]) for r in tr_rows), max(float(r["Volume"]) for r in tr_rows))
# 주의: 학습 구간 마지막 행(i=split-1+19 까지의 입력 행 + 정답 행 split-1+20)
print("  (학습 표본이 쓰는 행은 0 ~", split - 1 + 20, "번 행)")

# fc1 이 fc0 / fc2 와 같은 날의 수(24시간 전 예보가 실제로 다른 실행분인지)
w = wx.dropna(subset=["shortwave_radiation_previous_day1", "shortwave_radiation_previous_day2"])
print(f"일별: fc1==fc0 인 날 {int((w['shortwave_radiation_previous_day1'] == w['shortwave_radiation']).sum())}, fc1==fc2 인 날 {int((w['shortwave_radiation_previous_day1'] == w['shortwave_radiation_previous_day2']).sum())} / {len(w)}")
h2 = hh.dropna(subset=["shortwave_radiation_previous_day1", "shortwave_radiation_previous_day2"])
day = h2[(h2["t"].dt.hour >= 7) & (h2["t"].dt.hour <= 18)]
print(f"낮 시간값: fc1==fc0 {((day['shortwave_radiation_previous_day1'] == day['shortwave_radiation']).mean()*100):.1f}%, fc1==fc2 {((day['shortwave_radiation_previous_day1'] == day['shortwave_radiation_previous_day2']).mean()*100):.1f}%")
# 시각별로 fc1==fc0 비율 (실행 시각 구조를 엿본다)
for hr in range(5, 21):
    x = h2[h2["t"].dt.hour == hr]
    print(f"  {hr:02d}시: fc1==fc0 {((x['shortwave_radiation_previous_day1'] == x['shortwave_radiation']).mean()*100):5.1f}%  fc1==fc2 {((x['shortwave_radiation_previous_day1'] == x['shortwave_radiation_previous_day2']).mean()*100):5.1f}%  |fc1-fc0| 평균 {(x['shortwave_radiation_previous_day1'] - x['shortwave_radiation']).abs().mean():6.1f}  |fc2-fc1| 평균 {(x['shortwave_radiation_previous_day2'] - x['shortwave_radiation_previous_day1']).abs().mean():6.1f}")
