"""t3_02: 두 번째 입력 후보와 같은 날 발전량의 상관을 한 표로 맞춘다.

두 조사가 서로 다른 날 집합과 기간으로 상관을 적었으므로(예: 재분석 0.79, 광양 수평면 일사량 0.846, 공통 구간 0.863)
같은 정의로 다시 계산한다.
 - 날 집합: (가) 발전량 0 인 24일만 제외, (나) ASOS 분석의 정지 표시 43일 제외
 - 기간: 후보마다 자료가 있는 전 기간 / 모든 후보가 겹치는 공통 구간(2022-07-03 ~ 2025-12-30)
같은 날 상관은 대상일의 실제 값을 쓰는 것이므로 '입력으로 쓸 수 있다'는 뜻이 아니다. 예보 열만 예측 시점에 받을 수 있다.
"""
import numpy as np
import pandas as pd

import t3_common as c

pd.set_option("display.width", 250)

full = c.load_full()
arc = c.load_archive()
sat, _ = c.load_himawari()
pw = c.load_power()
pr = c.load_prevruns_daily()
gsm = c.load_gsm_cloud_daily(7, 18)
tca = c.load_asos_cloud()

# MSM 구름양 예보는 낮 07~18시 평균으로 다시 만든다(일 평균은 밤이 섞인다)
h = c.load_prevruns_hourly()
h["date"] = h["time"].dt.normalize()
h["hour"] = h["time"].dt.hour
dd = h[(h["hour"] >= 7) & (h["hour"] <= 18)]
g = dd.groupby("date")["cloud_cover_previous_day1"]
msm_cloud = g.mean().where(g.count() == 12).rename("msm_cloud_fc1").reset_index()

df = full
for x in [arc, sat, pw, pr, gsm, tca, msm_cloud]:
    df = df.merge(x, on="date", how="left")
df["month"] = df["date"].dt.month
df["year"] = df["date"].dt.year

# 원본 대조: full 의 gen_kwh 가 발전 실적 원본의 하루 합계와 같은지
raw = pd.read_csv(c.SOLAR / "data_15043409.csv", encoding="cp949")
print("발전 실적 원본 열:", list(raw.columns)[:6], "...", list(raw.columns)[-3:], "| 행", len(raw))
num = raw.select_dtypes("number")
hour_cols = [x for x in raw.columns if any(ch.isdigit() for ch in str(x))][:24]
tot_col = [x for x in raw.columns if "총" in str(x)]
print("  합계 열:", tot_col, "| 시간 열 수:", len(hour_cols))
date_col = raw.columns[[i for i, x in enumerate(raw.columns) if "일" in str(x) or "date" in str(x).lower()][0]]
rr = pd.DataFrame({"date": pd.to_datetime(raw[date_col]), "tot": raw[tot_col[0]].astype(float)})
chk = df.merge(rr, on="date", how="left")
print("  full.gen_kwh 와 원본 합계의 최대 차이:", float((chk["gen_kwh"] - chk["tot"]).abs().max()), "| 맞춘 날", int(chk["tot"].notna().sum()))

CAND = [
    ("광양 ASOS 수평면 일사량(관측)", "gy_gsr", "MJ/m2", "관측"),
    ("광양 ASOS 일사량 27도 경사면 환산", "gy_gsr_tilt27", "MJ/m2", "관측"),
    ("광양 ASOS 일조 시간(관측)", "gy_ss", "시간", "관측"),
    ("광양 ASOS 맑음 지수 kt", "gy_kt", "-", "관측"),
    ("광양 ASOS 전운량(관측, 2018-07-31~)", "gy_tca", "1/10", "관측"),
    ("여수 ASOS 전운량(관측)", "ys_tca", "1/10", "관측"),
    ("Open-Meteo 보관 자료 일사량(기본값)", "om_gsr", "MJ/m2", "재분석"),
    ("Open-Meteo ERA5 일사량", "era5_gsr", "MJ/m2", "재분석"),
    ("Open-Meteo 히마와리 위성 일사량", "sat_gsr", "MJ/m2", "위성"),
    ("NASA POWER 일사량", "power_gsr", "MJ/m2", "위성·재분석"),
    ("Open-Meteo 보관 자료 일조 시간(계산값)", "om_ss", "시간", "재분석"),
    ("Open-Meteo 보관 자료 구름양", "om_cloud", "%", "재분석"),
    ("JMA MSM 최신 실행분 일사량(예보 아님)", "fc0_gsr", "MJ/m2", "분석값에 가까움"),
    ("JMA MSM 24시간 전 일사량 예보", "fc1_gsr", "MJ/m2", "예보"),
    ("JMA MSM 48시간 전 일사량 예보", "fc2_gsr", "MJ/m2", "예보"),
    ("JMA MSM 24시간 전 구름양 예보(07~18시)", "msm_cloud_fc1", "%", "예보"),
    ("JMA GSM 하루 전 구름양 예보(07~18시)", "gsm_cloud_fc1", "%", "예보"),
]


def corr(m, col):
    mm = m & df[col].notna() & df["gen_kwh"].notna()
    if mm.sum() < 30:
        return np.nan, int(mm.sum())
    return float(np.corrcoef(df.loc[mm, "gen_kwh"], df.loc[mm, col])[0, 1]), int(mm.sum())


def within_month(m, col):
    rs = []
    for (_, _), g in df[m & df[col].notna()].groupby(["year", "month"]):
        if len(g) >= 20 and g[col].std() > 0:
            rs.append(np.corrcoef(g["gen_kwh"], g[col])[0, 1])
    return (float(np.mean(rs)), len(rs)) if rs else (np.nan, 0)


ex_zero = df["zero_gen"] == 0
ex_stop = df["stop_day"] == 0
common = (df["date"] >= "2022-07-03") & (df["date"] <= "2025-12-30")
allc = common.copy()
for _, col, _, _ in CAND:
    allc &= df[col].notna()
print("\n공통 구간(2022-07-03 ~ 2025-12-30)에서 17개 후보가 모두 있는 날:", int((allc & ex_stop).sum()),
      "| 그 가운데 정지 표시 날:", int((allc & ~ex_stop).sum()))

rows = []
for name, col, unit, kind in CAND:
    r1, n1 = corr(ex_zero, col)
    r2, n2 = corr(ex_stop, col)
    r3, n3 = corr(allc & ex_stop, col)
    wm, nm = within_month(ex_stop, col)
    first = df.loc[df[col].notna(), "date"].min().date()
    last = df.loc[df[col].notna(), "date"].max().date()
    rows.append(dict(후보=name, 종류=kind, 단위=unit, 자료_시작=first, 자료_끝=last,
                     상관_0인날제외=round(r1, 3), n1=n1, 상관_정지43일제외=round(r2, 3), n2=n2,
                     상관_공통구간=round(r3, 3), n3=n3, 같은달안_평균상관=round(wm, 3), 달수=nm))
t = pd.DataFrame(rows)
print("\n[1] 같은 날 발전량과의 피어슨 상관")
print(t.to_string(index=False))
t.to_csv(c.HERE / "t3_02_corr_table.csv", index=False)

print("\n[2] 사전 조사와 같은 정의로 다시 계산(발전량 0 초과인 날 전부, 2013-01-01 ~ 2026-02-28)")
pos = df["gen_kwh"] > 0
for name, col in [("ERA5 일사량", "era5_gsr"), ("보관 자료 기본값", "om_gsr"), ("히마와리(2015-07~)", "sat_gsr"),
                  ("POWER 일사량", "power_gsr"), ("JMA 24시간 전(2022-07-03~)", "fc1_gsr"), ("JMA 48시간 전", "fc2_gsr"),
                  ("GSM 구름양 예보(2016-01-03~)", "gsm_cloud_fc1")]:
    r, n = corr(pos, col)
    print(f"  {name:28s} 상관 {r:+.3f} (n={n})")

print("\n[3] ASOS 분석과 같은 정의로 다시 계산(발전량 0 인 24일 제외, 2013-01-01 ~ 2025-12-31, 광양 값이 있는 날)")
m3 = ex_zero & (df["date"] <= "2025-12-31")
for name, col in [("광양 수평면 일사량", "gy_gsr"), ("광양 경사면 27도 환산", "gy_gsr_tilt27"), ("광양 일조 시간", "gy_ss"),
                  ("광양 kt", "gy_kt"), ("광양 전운량", "gy_tca"), ("같은 날들의 보관 자료 기본값", "om_gsr"),
                  ("같은 날들의 ERA5", "era5_gsr")]:
    r, n = corr(m3 & df["gy_gsr"].notna(), col)
    print(f"  {name:26s} 상관 {r:+.3f} (n={n})")

print("\n[4] 보완 조사 1 의 공통 구간(2023-07-17 ~ 2025-12-30, 898일)에서 다시 계산")
m4 = (df["date"] >= "2023-07-17") & (df["date"] <= "2025-12-30")
print("  일수:", int(m4.sum()), "| 정지 표시:", int((m4 & ~ex_stop).sum()))
for name, col in [("광양 수평면 일사량", "gy_gsr"), ("보관 자료 기본값", "om_gsr"), ("히마와리", "sat_gsr"),
                  ("JMA 24시간 전 예보", "fc1_gsr"), ("JMA 48시간 전 예보", "fc2_gsr"), ("GSM 구름양 예보", "gsm_cloud_fc1"),
                  ("광양 일조 시간", "gy_ss"), ("광양 경사면 환산", "gy_gsr_tilt27")]:
    r, n = corr(m4, col)
    print(f"  {name:22s} 상관 {r:+.3f} (n={n})")

print("\n[5] 예보 열의 날짜 정렬: d 일 예보값과 d+k 일 발전량의 상관(발전량 0 초과)")
for col in ["fc1_gsr", "gsm_cloud_fc1"]:
    out = []
    for k in [-1, 0, 1]:
        y = df["gen_kwh"].shift(-k)
        mm = df[col].notna() & y.notna() & (y > 0)
        out.append(f"k={k:+d}: {np.corrcoef(df.loc[mm, col], y[mm])[0, 1]:+.3f}")
    print(f"  {col}: " + ", ".join(out))

print("\n[6] 공통 구간에서 상관 차이의 7일 블록 부트스트랩(2,000번, 난수 20261007)")
rng = np.random.default_rng(20261007)
sub = df[allc & ex_stop].reset_index(drop=True)
n = len(sub)
blocks = [np.arange(i, min(i + 7, n)) for i in range(0, n, 7)]
pairs = [("gy_gsr", "om_gsr"), ("gy_gsr", "sat_gsr"), ("gy_gsr", "fc1_gsr"), ("om_gsr", "fc1_gsr"),
         ("fc1_gsr", "fc2_gsr"), ("gy_gsr_tilt27", "gy_gsr"), ("gy_gsr", "gy_ss")]
res = {p: [] for p in pairs}
for _ in range(2000):
    idx = np.concatenate([blocks[i] for i in rng.integers(0, len(blocks), len(blocks))])
    s = sub.iloc[idx]
    cc = {col: abs(np.corrcoef(s["gen_kwh"], s[col])[0, 1]) for col in set(sum(pairs, ()))}
    for a, b in pairs:
        res[(a, b)].append(cc[a] - cc[b])
for (a, b), v in res.items():
    lo, hi = np.percentile(v, [2.5, 97.5])
    base = abs(np.corrcoef(sub["gen_kwh"], sub[a])[0, 1]) - abs(np.corrcoef(sub["gen_kwh"], sub[b])[0, 1])
    print(f"  |r({a})| - |r({b})| = {base:+.3f}  95% [{lo:+.3f}, {hi:+.3f}]")
