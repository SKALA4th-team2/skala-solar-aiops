"""T1 발전소와 데이터의 정의: 두 조사(사전 조사, ASOS 분석)가 어긋난 곳을 원자료로 다시 계산한다.

실행(쓰기 금지 폴더는 읽기만 한다)
  cd .../scratchpad/merged/T1-plant-data
  PYTHONDONTWRITEBYTECODE=1 /Users/psm/workspace/skala-aiops/mlflow/.venv/bin/python t1_01_recompute.py > t1_01_recompute.txt

읽는 파일
  발전 실적 원본        ../../solar/data_15043409.csv (CP949)
  이웃 발전소 4곳 원본   ../../solar/verify1a/r2/data_1504340{4,5,6,8}.csv (사전 조사 검증 단계가 받아 둔 사본)
  ASOS 쪽 결합 자료      ../../asos/hadong_daily_full.csv, ../../asos/hadong_upload.csv, ../../asos/a3/a3_daily.csv
"""
import os
import warnings

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge

warnings.filterwarnings("ignore")
pd.set_option("display.width", 250)
pd.set_option("display.max_rows", 200)

HERE = os.path.dirname(os.path.abspath(__file__))
SP = os.path.abspath(os.path.join(HERE, "..", ".."))
RAW = os.path.join(SP, "solar", "data_15043409.csv")
SIB_DIR = os.path.join(SP, "solar", "verify1a", "r2")
ASOS_FULL = os.path.join(SP, "asos", "hadong_daily_full.csv")
ASOS_UP = os.path.join(SP, "asos", "hadong_upload.csv")
A3_DAILY = os.path.join(SP, "asos", "a3", "a3_daily.csv")
HC = [str(i) for i in range(1, 25)]
LAT, LON, TZ = 35.05885, 127.7799, 9.0     # 남부발전 '태양광발전소 위치 정보' CSV 의 하동 하수처리장 행


def sec(t):
    print("\n" + "=" * 8 + " " + t + " " + "=" * 8)


def load(path):
    d = pd.read_csv(path, encoding="cp949")
    d["date"] = pd.to_datetime(d["년월일"])
    return d.sort_values(["date", "호기"]).reset_index(drop=True)


df = load(RAW)
H = df[HC].values.astype(float)
tot = H.sum(axis=1)
n = len(df)

# ------------------------------------------------------------------ 1
sec("1. 원본 구조와 요약 열의 뜻")
print("열 이름:", list(df.columns[:8]), "+ 1~24")
full = pd.date_range(df.date.min(), df.date.max())
print(f"행 {n}, 기간 {df.date.min().date()} ~ {df.date.max().date()}, 달력 일수 {len(full)}, 빠진 날 {len(full.difference(df.date))}, 겹친 날 {int(df.date.duplicated().sum())}, 호기 값 {sorted(df['호기'].unique())}")
print("결측 셀", int(df[HC].isna().sum().sum()), "음수 셀", int((H < 0).sum()))
print("총량(kw) - 시간값 합: 최대 절대 차이", float(np.abs(df["총량(kw)"].values - tot).max()))
print("최대(kw) - 시간값 최댓값: 최대 절대 차이", float(np.abs(df["최대(kw)"].values - H.max(axis=1)).max()))
print("최소(kw) - 시간값 최솟값: 최대 절대 차이", float(np.abs(df["최소(kw)"].values - H.min(axis=1)).max()), "/ 최소(kw) 가 0 이 아닌 날", int((df["최소(kw)"] != 0).sum()))
avg = df["평균(kw)"].values
q = tot / 24
segs = [("2013-01-01", "2020-07-31"), ("2020-08-01", "2021-07-31"), ("2021-08-01", "2026-02-28")]
for a, b in segs:
    m = ((df.date >= a) & (df.date <= b)).values
    print(f"  평균(kw) {a}~{b} ({m.sum()}일): 정수 반올림과 일치 {int((np.abs(avg[m] - np.round(q[m])) < 1e-9).sum())}일, "
          f"소수 3자리 반올림과 일치 {int((np.abs(avg[m] - np.round(q[m], 3)) < 1e-9).sum())}일, 총량/24 와의 최대 차이 {np.abs(avg[m] - q[m]).max():.6f}")
print(f"일 합계: 평균 {tot.mean():.2f}, 중앙값 {np.median(tot):.2f}, 최대 {tot.max():.3f} ({df.date[tot.argmax()].date()})")

# ------------------------------------------------------------------ 2
sec("2. 설비 용량: 50kW 와 55kW 중 어느 쪽이 원자료와 맞는가")
pos = H[H > 0]
i, j = np.unravel_index(H.argmax(), H.shape)
print(f"0보다 큰 시간값 {len(pos)}개, 최대 {H.max():.3f} ({df.date[i].date()} 열 {j + 1})")
for thr in (50, 52, 55):
    m = H > thr
    days = df.date[m.any(axis=1)]
    print(f"  {thr} 초과 시간 {int(m.sum())}개, {len(days)}일" + (f", 연도 {sorted(days.dt.year.unique())}, 월 {sorted(days.dt.month.unique())}, 마지막 {days.max().date()}" if len(days) else ""))
print("  구간별 시간 수:", {f"{a}~{a + 1}": int(((H > a) & (H <= a + 1)).sum()) for a in range(46, 55)})
for cap in (50.0, 55.0):
    yr = df.date.dt.year.values
    cf = {int(y): tot[yr == y].sum() / (cap * 24 * (yr == y).sum()) * 100 for y in range(2013, 2026)}
    print(f"  용량 {cap:.0f}kW: 시간 최대/용량 = {H.max() / cap * 100:.1f}%, 일 최대/(용량x24) = {tot.max() / (cap * 24) * 100:.1f}%, "
          f"전체 평균 이용률 {tot.mean() / (cap * 24) * 100:.2f}%, 2013년 {cf[2013]:.2f}%, 2013~2025 연 이용률 범위 {min(cf.values()):.2f}~{max(cf.values()):.2f}%")
ymax = pd.Series(H.max(axis=1)).groupby(df.date.dt.year.values).max().round(2)
print("  연도별 시간 최대:", ymax.to_dict())
# ASOS 쪽이 만든 결합 자료의 peak_kw 가 50 을 넘는지(그쪽 자료 안에서도 50kW 가정과 어긋나는지)
af = pd.read_csv(ASOS_FULL, parse_dates=["date"])
print(f"  ASOS 결합 자료 hadong_daily_full.csv 의 peak_kw: 최대 {af.peak_kw.max():.3f}, 50 초과인 날 {int((af.peak_kw > 50).sum())}일")

# ------------------------------------------------------------------ 3
sec("3. 같은 형식의 이웃 발전소 4곳(하동군): 시간 최대가 공식 용량의 몇 %까지 올라가는가")
SIBS = {"15043404": ("하동공설운동장", 369.85), "15043405": ("하동변전소", 48.3), "15043406": ("하동보건소", 40.0), "15043408": ("하동정수장", 93.02)}
zero_days = df.date[tot == 0]
rows = []
for k, (nm, cap) in SIBS.items():
    p = os.path.join(SIB_DIR, f"data_{k}.csv")
    s = load(p)
    hs = s[HC].values.astype(float)
    st = hs.sum(axis=1)
    totcol = [c for c in s.columns if c.startswith("총량")][0]
    on_zero = s.set_index("date").loc[zero_days, HC].sum(axis=1)
    rows.append({"발전소": nm, "공식 용량(kW)": cap, "행": len(s), "시작": s.date.min().date(), "끝": s.date.max().date(), "호기": sorted(s["호기"].unique()),
                 "총량-합 최대차": round(float(np.abs(s[totcol].values - st).max()), 6), "열 이름에 (kw)": "(kw)" in totcol,
                 "합계 0인 날": int((st == 0).sum()), "시간 최대": round(float(hs.max()), 3), "시간 최대/용량 %": round(float(hs.max()) / cap * 100, 1),
                 "하수처리장이 0인 24일 중 이 발전소도 0인 날": int((on_zero == 0).sum())})
print(pd.DataFrame(rows).to_string(index=False))
print(f"  하수처리장: 시간 최대 {H.max():.3f} -> 55kW 의 {H.max() / 55 * 100:.1f}%, 50kW 의 {H.max() / 50 * 100:.1f}%")

# ------------------------------------------------------------------ 4
sec("4. 시간대 열 h 의 구간: (h-1)~h 시(A) 대 h~(h+1) 시(B), 남부발전 공개 좌표로 다시 계산")


def solar_table(dates, lat=LAT, lon=LON, tz=TZ):
    d = pd.DatetimeIndex(dates)
    jd = d.to_julian_date().values + 0.5 - tz / 24.0
    T = (jd - 2451545.0) / 36525.0
    L0 = np.mod(280.46646 + T * (36000.76983 + 0.0003032 * T), 360.0)
    M = 357.52911 + T * (35999.05029 - 0.0001537 * T)
    e = 0.016708634 - T * (0.000042037 + 0.0000001267 * T)
    Mr = np.radians(M)
    C = (np.sin(Mr) * (1.914602 - T * (0.004817 + 0.000014 * T)) + np.sin(2 * Mr) * (0.019993 - 0.000101 * T) + np.sin(3 * Mr) * 0.000289)
    omega = np.radians(125.04 - 1934.136 * T)
    lam = np.radians(L0 + C - 0.00569 - 0.00478 * np.sin(omega))
    eps0 = 23 + (26 + (21.448 - T * (46.815 + T * (0.00059 - T * 0.001813))) / 60) / 60
    eps = np.radians(eps0 + 0.00256 * np.cos(omega))
    decl = np.arcsin(np.sin(eps) * np.sin(lam))
    y = np.tan(eps / 2) ** 2
    L0r = np.radians(L0)
    eot = 4 * np.degrees(y * np.sin(2 * L0r) - 2 * e * np.sin(Mr) + 4 * e * y * np.sin(Mr) * np.cos(2 * L0r) - 0.5 * y * y * np.sin(4 * L0r) - 1.25 * e * e * np.sin(2 * Mr))
    latr = np.radians(lat)
    c = (np.sin(np.radians(-0.833)) - np.sin(latr) * np.sin(decl)) / (np.cos(latr) * np.cos(decl))
    ha = np.degrees(np.arccos(np.clip(c, -1, 1)))
    noon = (720 - 4 * lon - eot + tz * 60) / 60.0
    return noon - ha * 4 / 60, noon, noon + ha * 4 / 60


rise, noon, sset = solar_table(df.date)
mon = df.date.dt.month.values
gen_day = tot > 0
w = H / np.where(tot > 0, tot, np.nan)[:, None]
cen_A = (w * (np.arange(1, 25) - 0.5)).sum(axis=1)       # 열 h 의 중심 = h - 0.5 시
cen_B = (w * (np.arange(1, 25) + 0.5)).sum(axis=1)       # 열 h 의 중심 = h + 0.5 시
print(f"발전일 {int(gen_day.sum())}일. 발전량 가중 중심 시각 - 남중 시각: A 평균 {np.nanmean(cen_A - noon):+.3f}시간, B 평균 {np.nanmean(cen_B - noon):+.3f}시간")
for m_, nm in ((12, "12월"), (6, "6월")):
    mm = (mon == m_)
    print(f"  {nm} {int(mm.sum())}일: 일출 {rise[mm].min():.2f}~{rise[mm].max():.2f}시, 일몰 {sset[mm].min():.2f}~{sset[mm].max():.2f}시. "
          + ", ".join(f"열 {h} 에 값이 있는 날 {int((H[mm][:, h - 1] > 0).sum())}일(최대 {H[mm][:, h - 1].max():.3f})" for h in ((8, 9, 18, 19) if m_ == 12 else (5, 6, 20, 21))))
# 구간이 일몰 뒤에 시작하는데 0.5 이상인 값
for name, off in (("A", -1), ("B", 0)):
    start = np.arange(1, 25) + off            # 열 h 구간의 시작 시각
    after = (start[None, :] >= sset[:, None]) & (H >= 0.5)
    before = ((start[None, :] + 1) <= rise[:, None]) & (H >= 0.5)
    print(f"  가설 {name}: 구간 전체가 일몰 뒤인데 0.5 이상인 셀 {int(after.sum())}개({int(after.any(axis=1).sum())}일), 구간 전체가 일출 전인데 0.5 이상인 셀 {int(before.sum())}개")

# ------------------------------------------------------------------ 5
sec("5. 자료 품질: 0인 날, 사실상 정지, 복사·수기 입력이 의심되는 날, ASOS 쪽 정지 표시와의 대조")
z = df.date[tot == 0]
print(f"합계가 정확히 0인 날 {len(z)}일: {z.min().date()}~ … 목록 {[str(x.date()) for x in z]}")
nz = df[(tot > 0) & (tot < 1)]
print(f"0 초과 1 미만인 날 {len(nz)}일: {[(str(a.date()), round(float(b), 3)) for a, b in zip(nz.date, tot[nz.index])]}")
m15 = ((df.date >= '2015-04-20') & (df.date <= '2015-05-08')).values
print("2015-04-20~05-08 일 합계:", [(str(a.date())[5:], round(float(b), 2)) for a, b in zip(df.date[m15], tot[m15])])
# (가) 24시간 값이 통째로 같은 날 쌍(합계 0 제외)
key = pd.Series([tuple(np.round(r, 3)) for r in H])
dup = key[(tot > 0)].duplicated(keep=False)
grp = key[(tot > 0)][dup]
pairs = {}
for idx_, k_ in grp.items():
    pairs.setdefault(k_, []).append(str(df.date[idx_].date()))
print("24시간 값이 통째로 같은 날 묶음(합계 0 제외):", [(v, round(sum(k_), 3)) for k_, v in pairs.items()])
a_ = df.set_index("date")
same_summary = (a_.loc["2016-12-28", list(df.columns[2:8])].values == a_.loc["2015-12-28", list(df.columns[2:8])].values).all()
print("  2016-12-28 과 2015-12-28: 24시간 값 같음", bool((a_.loc["2016-12-28", HC].values == a_.loc["2015-12-28", HC].values).all()), "/ 요약 6열 같음", bool(same_summary),
      "/ 앞뒤 날 합계", {str(d_.date()): round(float(a_.loc[d_, HC].sum()), 2) for d_ in pd.date_range("2016-12-20", "2016-12-31")})
# (나) 0.006 의 배수가 아닌 셀
r = np.abs(H / 0.006 - np.round(H / 0.006))
bad = (r > 1e-6) & (H > 0)
bi, bj = np.where(bad)
print(f"0.006 의 정수배가 아닌 0 초과 셀 {int(bad.sum())}개 / 0 초과 셀 {int((H > 0).sum())}개:",
      [(str(df.date[i_].date()), int(j_ + 1), float(H[i_, j_])) for i_, j_ in zip(bi, bj)])
for d_ in ("2016-02-24", "2016-02-25", "2016-02-26"):
    print(f"  {d_}: 일 합계 {a_.loc[d_, HC].sum():.3f}, 시간값 {[float(x) for x in a_.loc[d_, HC].values if x > 0]}")
# (다) ASOS 쪽 정지 표시 43일과 사전 조사 쪽 40일(0인 24일 + 사실상 정지 16일)의 차이
asos_stop = set(af.date[af.stop_day == 1])
pre_near = set(pd.date_range("2015-04-23", "2015-05-05")) | set(pd.to_datetime(["2018-07-04", "2018-07-07", "2018-07-12"]))
pre_stop = set(z) | pre_near
print(f"ASOS 쪽 stop_day {len(asos_stop)}일(zero_gen {int(af.zero_gen.sum())}, near_zero_stop {int(af.near_zero_stop.sum())}), 사전 조사 쪽 {len(pre_stop)}일")
only_asos = sorted(asos_stop - pre_stop)
only_pre = sorted(pre_stop - asos_stop)
print("  ASOS 쪽에만 있는 날:", [(str(d_.date()), round(float(a_.loc[d_, HC].sum()), 2), "광양 일사량", float(af.set_index('date').loc[d_, 'gy_gsr'])) for d_ in only_asos])
print("  사전 조사 쪽에만 있는 날:", [(str(d_.date()), round(float(a_.loc[d_, HC].sum()), 2)) for d_ in only_pre])
print("  복사 의심일 2016-12-28 의 ASOS 쪽 표시: stop_day =", int(af.set_index("date").loc["2016-12-28", "stop_day"]),
      "/ 수기 입력 의심일 2016-02-24~26 의 stop_day =", af.set_index("date").loc["2016-02-24":"2016-02-26", "stop_day"].tolist())

# ------------------------------------------------------------------ 6
sec("6. ASOS 쪽이 만든 파일과 원본의 대조(발전 실적 부분만)")
print(f"hadong_daily_full.csv: 행 {len(af)}, {af.date.min().date()}~{af.date.max().date()}, gen_kwh - 원본 총량 최대 차이 {np.abs(af.gen_kwh.values - np.round(tot, 3)).max():.6f}, peak_kw - 원본 시간 최대 최대 차이 {np.abs(af.peak_kw.values - np.round(H.max(axis=1), 3)).max():.6f}")
up = pd.read_csv(ASOS_UP, parse_dates=["Date"])
mm = a_.loc[up.Date, HC].sum(axis=1).values
print(f"hadong_upload.csv: 행 {len(up)}, {up.Date.min().date()}~{up.Date.max().date()}, 열 {list(up.columns)}, Close - 원본 총량 최대 차이 {np.abs(up.Close.values - np.round(mm, 3)).max():.6f}, Close 범위 {up.Close.min()}~{up.Close.max()}, Stop=1 {int(up.Stop.sum())}일")

# ------------------------------------------------------------------ 7
sec("7. 용량을 분모로 쓰는 오차율이 용량 값(50, 55kW)에 따라 어떻게 달라지는가")
CAPS = (50.0, 55.0)
print("[7-1] 일 단위: MAE / (용량 x 24h). ASOS 쪽 분할 A(평가 2023-05-31~2025-12-31) 의 단순 예측")
a3 = pd.read_csv(A3_DAILY)
gen = a3.gen.values
sun = a3.sun.values
dates = a3.date.values
out = (gen < 1.0) | ((gen < 30.0) & (sun >= 5.0))             # a3_common.outage_flag 와 같은 식
targets = np.arange(21, len(gen))
k = int(len(targets) * 0.8)
tr_t, te_t = targets[:k], targets[k:]
train_days = np.arange(0, tr_t[-1] + 1)
tmean = gen[train_days[~out[train_days]]].mean()
cs = np.cumsum(np.insert(gen, 0, 0.0))
preds = {"학습 구간 평균(고정값)": np.full(len(te_t), tmean), "20일 평균": (cs[te_t] - cs[te_t - 20]) / 20, "7일 평균": (cs[te_t] - cs[te_t - 7]) / 7, "어제 값": gen[te_t - 1]}
print(f"  평가 {dates[te_t[0]]}~{dates[te_t[-1]]} ({len(te_t)}일), 실제 평균 {gen[te_t].mean():.1f}kWh, 학습 구간 평균 {tmean:.2f}kWh")
for nm, p in preds.items():
    e = p - gen[te_t]
    mae, rmse = np.abs(e).mean(), np.sqrt((e ** 2).mean())
    print(f"  {nm}: RMSE {rmse:.2f}, MAE {mae:.2f} -> 50kW 기준 {mae / 1200 * 100:.2f}%, 55kW 기준 {mae / 1320 * 100:.2f}% (합계 대비 절대오차율 {np.abs(e).sum() / gen[te_t].sum() * 100:.1f}% 는 용량과 무관)")

print("\n[7-2] 일 단위: 사전 조사 쪽 대리 모형(Ridge, 직전 20일 합계 입력, 앞 80% 학습·뒤 20% 평가)")
SEQ = 20
t_idx = np.arange(SEQ, n)
split = int(len(t_idx) * 0.8)
X = np.stack([tot[t - SEQ:t] for t in t_idx]) / 380.0
y = tot[t_idx]
te = np.zeros(len(t_idx), bool)
te[split:] = True
mdl = Ridge(alpha=1.0).fit(X[~te], y[~te])
p_day = mdl.predict(X)
mae_day = np.abs(p_day[te] - y[te]).mean()
print(f"  평가 {df.date[t_idx[split]].date()}~{df.date[t_idx[-1]].date()} ({int(te.sum())}일), MAE {mae_day:.2f} -> 50kW 기준 {mae_day / 1200 * 100:.2f}%, 55kW 기준 {mae_day / 1320 * 100:.2f}%")

print("\n[7-3] 시간 단위(예측제도식): 시간대별 |예측-실제| / 용량, 실제 이용률 10% 이상인 시간만 평균. 같은 평가 구간")
tr_days = np.zeros(n, bool)
tr_days[: t_idx[split - 1] + 1] = True
share = np.zeros((13, 24))
for m_ in range(1, 13):
    mm_ = tr_days & (mon == m_) & (tot > 0)
    share[m_] = H[mm_].sum(axis=0) / H[mm_].sum()
Ht = H[t_idx]
Hs = pd.DataFrame(H)
hour_preds = {"Ridge 일 예측 x 월별 평균 시간 비중": p_day[:, None] * share[mon[t_idx]],
              "어제 같은 시간 값": Hs.shift(1).values[t_idx],
              "최근 7일 같은 시간 평균": Hs.rolling(7).mean().shift(1).values[t_idx]}
res = {}
for cap in CAPS:
    elig = (Ht >= 0.1 * cap) & te[:, None]
    for nm, ph in hour_preds.items():
        e = np.abs(ph - Ht) / cap * 100
        res[(nm, cap)] = (e[elig].mean(), int(elig.sum()), elig[te].sum(axis=1).mean())
for nm in hour_preds:
    a50, a55 = res[(nm, 50.0)], res[(nm, 55.0)]
    print(f"  {nm}: 50kW 기준 {a50[0]:.2f}% (대상 {a50[1]}시간, 하루 평균 {a50[2]:.2f}시간) / 55kW 기준 {a55[0]:.2f}% (대상 {a55[1]}시간, 하루 평균 {a55[2]:.2f}시간) / 비 {a50[0] / a55[0]:.3f}")
for cap in CAPS:
    el = H >= 0.1 * cap
    print(f"  전체 기간, 용량 {cap:.0f}kW: 이용률 10% 이상(시간값 {0.1 * cap:.1f} 이상)인 시간 하루 평균 {el.sum(axis=1).mean():.2f}시간, 그 시간들의 발전량 비중 {H[el].sum() / H.sum() * 100:.1f}%")

print("\n[7-4] ASOS 쪽 파일에 적힌 '용량 대비 MAE %'(50kW x 24h 기준)를 55kW 로 바꾼 값 = 원래 값 x 50/55")
for nm, v in (("고정값 예측(분할 A, r3_baselines.txt train_mean)", 5.51), ("20일 평균(분할 A)", 5.51), ("LSTM 발전량+하루 최대 출력 ga(분할 A, r3_gate_check.txt)", 5.20),
              ("LSTM 일조 시간 과거 값 na(분할 A)", 5.22), ("LSTM 상한 da(분할 A, 대상일 실제 일조 사용)", 1.70)):
    print(f"  {nm}: {v:.2f}% -> {v * 50 / 55:.2f}%")
