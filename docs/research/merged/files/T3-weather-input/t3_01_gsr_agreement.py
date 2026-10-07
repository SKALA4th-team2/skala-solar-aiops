"""t3_01: 광양(266) ASOS 관측 일사량과 Open-Meteo 일사량이 같은 날 얼마나 일치하는가.

기준(관측): asos/hadong_daily_full.csv 의 gy_gsr_obs (광양 실제 관측값만. 진주·의령으로 메운 5일은 빠진다)
비교: solar/d2r/wx_archive_daily.csv (Open-Meteo 보관 자료 기본값: 2016년까지 ERA5, 2017년부터 ECMWF IFS),
      전 기간 ERA5, 히마와리 위성, NASA POWER, JMA 예보(최신 실행분, 24시간 전, 48시간 전)
단위는 모두 MJ/m2(하루 합계). 두 지점은 같은 곳이 아니다(광양 관측소 34.94N 127.69E, 격자 35.04N 127.79E).
"""
import numpy as np
import pandas as pd

import t3_common as c

pd.set_option("display.width", 250)

full = c.load_full()
arc = c.load_archive()
sat, sat_grid = c.load_himawari()
pw = c.load_power()
pr = c.load_prevruns_daily()

df = full.merge(arc, on="date", how="left").merge(sat, on="date", how="left").merge(pw, on="date", how="left").merge(pr, on="date", how="left")
df["year"] = df["date"].dt.year
df["month"] = df["date"].dt.month
obs = df["gy_gsr_obs"].where(df["gy_gsr_suspect"] != 1)      # 낮게 기록된 것으로 표시된 3일 제외
obs_all = df["gy_gsr_obs"]
print("광양 관측 일사량이 있는 날:", int(obs_all.notna().sum()), "| 의심 3일 제외:", int(obs.notna().sum()),
      "| 기간", df.loc[obs_all.notna(), "date"].min().date(), "~", df.loc[obs_all.notna(), "date"].max().date())
print("보관 자료 행:", int(df["om_gsr"].notna().sum()), "| 위성 값 있는 날:", int(df["sat_gsr"].notna().sum()),
      "| 위성 격자", sat_grid)

print("\n[1] 전체 기간, 같은 날 일치도 (기준 = 광양 관측)")
for name, col in [("보관 자료 기본값(ERA5→IFS)", "om_gsr"), ("전 기간 ERA5", "era5_gsr"), ("히마와리 위성", "sat_gsr"),
                  ("NASA POWER", "power_gsr"), ("JMA 최신 실행분", "fc0_gsr"), ("JMA 24시간 전 예보", "fc1_gsr"),
                  ("JMA 48시간 전 예보", "fc2_gsr")]:
    print(f"  {name:24s}", c.fmt(c.stats_pair(obs, df[col])))
print("  (의심 3일 포함) 보관 자료 기본값  ", c.fmt(c.stats_pair(obs_all, df["om_gsr"])))

print("\n[2] 보관 자료 기본값: 출처가 바뀌는 2017-01-01 앞뒤")
for lab, m in [("2013~2016 (ERA5 구간)", df["year"] <= 2016), ("2017~2025 (IFS 구간)", df["year"] >= 2017)]:
    print(f"  {lab:22s} 기본값", c.fmt(c.stats_pair(obs[m], df.loc[m, "om_gsr"])))
    print(f"  {lab:22s} ERA5  ", c.fmt(c.stats_pair(obs[m], df.loc[m, "era5_gsr"])))

print("\n[3] 연도별 (기준 = 광양 관측, 비교 = 보관 자료 기본값 / 위성)")
rows = []
for y, g in df.groupby("year"):
    if y > 2025:
        continue
    s = c.stats_pair(obs[g.index], g["om_gsr"])
    s2 = c.stats_pair(obs[g.index], g["sat_gsr"])
    rows.append(dict(year=y, n=s["n"], obs_mean=round(s["mean_x"], 2), om_ratio=round(s["ratio_sum"], 3),
                     om_rmse=round(s["rmse"], 2), om_r=round(s["r"], 3),
                     sat_n=s2.get("n", 0), sat_ratio=round(s2.get("ratio_sum", np.nan), 3),
                     sat_rmse=round(s2.get("rmse", np.nan), 2), sat_r=round(s2.get("r", np.nan), 3)))
yt = pd.DataFrame(rows)
print(yt.to_string(index=False))
yt.to_csv(c.HERE / "t3_01_by_year.csv", index=False)

print("\n[4] 달별 (전 기간, 보관 자료 기본값)")
rows = []
for mth, g in df.groupby("month"):
    s = c.stats_pair(obs[g.index], g["om_gsr"])
    rows.append(dict(month=mth, n=s["n"], obs_mean=round(s["mean_x"], 2), ratio=round(s["ratio_sum"], 3),
                     bias=round(s["bias"], 2), rmse=round(s["rmse"], 2), rrmse_pct=round(s["rrmse_pct"], 1), r=round(s["r"], 3)))
mt = pd.DataFrame(rows)
print(mt.to_string(index=False))
mt.to_csv(c.HERE / "t3_01_by_month.csv", index=False)

print("\n[5] 하늘 상태별 (광양 관측 맑음 지수 gy_kt 로 나눔)")
for lab, m in [("흐림 kt<0.3", df["gy_kt"] < 0.3), ("중간 0.3~0.6", (df["gy_kt"] >= 0.3) & (df["gy_kt"] <= 0.6)),
               ("맑음 kt>0.6", df["gy_kt"] > 0.6)]:
    print(f"  {lab:12s} 기본값", c.fmt(c.stats_pair(obs[m], df.loc[m, "om_gsr"])))
    print(f"  {lab:12s} 위성  ", c.fmt(c.stats_pair(obs[m], df.loc[m, "sat_gsr"])))

print("\n[6] 날짜 밀림 점검: 광양 관측[d] 와 보관 자료[d+k] 의 상관")
for k in [-2, -1, 0, 1, 2]:
    s = c.stats_pair(obs, df["om_gsr"].shift(-k))
    print(f"  k={k:+d}: 상관 {s['r']:.3f} (n={s['n']})")

print("\n[7] 같은 달 안에서의 일치(계절을 걷어낸 값): 달마다 상관을 구해 평균")
for name, col in [("보관 자료 기본값", "om_gsr"), ("전 기간 ERA5", "era5_gsr"), ("히마와리 위성", "sat_gsr"), ("JMA 24시간 전 예보", "fc1_gsr")]:
    rs = []
    for (y, mth), g in df.groupby(["year", "month"]):
        s = c.stats_pair(obs[g.index], g[col])
        if s.get("n", 0) >= 20:
            rs.append(s["r"])
    print(f"  {name:20s} 연·월 {len(rs)}개 평균 상관 {np.mean(rs):.3f} (최소 {np.min(rs):.3f}, 중앙 {np.median(rs):.3f})")

print("\n[8] 큰 어긋남: |보관 자료 - 광양 관측| 이 큰 날의 비율")
d = (df["om_gsr"] - obs).dropna()
for th in [2, 3, 5, 8]:
    print(f"  차이 {th} MJ/m2 초과: {int((d.abs() > th).sum())}일 ({(d.abs() > th).mean() * 100:.1f}%)")
print("  차이의 분위수(5, 25, 50, 75, 95%):", np.round(np.percentile(d, [5, 25, 50, 75, 95]), 2))

print("\n[9] 예보가 있는 공통 구간(2022-07-03 ~ 2025-12-31)에서 같은 날끼리 (기준 = 광양 관측)")
m = (df["date"] >= "2022-07-03") & (df["date"] <= "2025-12-31") & df["fc1_gsr"].notna() & df["sat_gsr"].notna() & obs.notna()
print("  공통 일수:", int(m.sum()))
for name, col in [("보관 자료 기본값(IFS)", "om_gsr"), ("전 기간 ERA5", "era5_gsr"), ("히마와리 위성", "sat_gsr"),
                  ("NASA POWER", "power_gsr"), ("JMA 최신 실행분", "fc0_gsr"), ("JMA 24시간 전 예보", "fc1_gsr"),
                  ("JMA 48시간 전 예보", "fc2_gsr")]:
    print(f"  {name:22s}", c.fmt(c.stats_pair(obs[m], df.loc[m, col])))

print("\n[10] 일조 시간: 광양 관측(gy_ss_obs, 시간) 대 보관 자료 sunshine_duration(계산값, 시간)")
ss = df["gy_ss_obs"]
print("  기본값", c.fmt(c.stats_pair(ss, df["om_ss"])))
print("  ERA5  ", c.fmt(c.stats_pair(ss, df["era5_ss"])))
