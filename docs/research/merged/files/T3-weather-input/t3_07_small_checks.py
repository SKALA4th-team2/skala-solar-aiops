"""t3_07: 작은 확인들.
(1) ASOS 보고서 2.1절의 상관(0.846, 0.941, 0.903)을 '광양 실제 관측값만'(메운 5일 제외)으로 다시 계산
(2) 사전 조사 3a 의 일조 시간 상관 0.899(발전량 0 초과 4,774일, 날씨누리 값) 과 ASOS 0.903 의 차이: 날 집합
(3) 광양 ASOS 대비 위성·보관 자료의 연도별 비(수준 변화가 관측소 쪽인지 보는 참고)
(4) 이번에 받은 최신 응답(위성, 보관 자료, 예보)의 마지막 값
"""
import json
import numpy as np
import pandas as pd
import t3_common as c

full = c.load_full(); arc = c.load_archive(); sat, _ = c.load_himawari()
df = full.merge(arc, on="date", how="left").merge(sat, on="date", how="left")
z = df["zero_gen"] == 0
print("[1] 광양 실제 관측값만(발전량 0 인 24일 제외)")
for lab, col, obs in [("수평면 일사량", "gy_gsr", "gy_gsr_obs"), ("경사면 27도 환산", "gy_gsr_tilt27", "gy_gsr_obs"), ("일조 시간", "gy_ss", "gy_ss_obs")]:
    m = z & df[obs].notna()
    print(f"  {lab}: 상관 {np.corrcoef(df.loc[m, 'gen_kwh'], df.loc[m, col])[0, 1]:.3f} (n={int(m.sum())})")

print("\n[2] 일조 시간 상관: 날씨누리 참고 열(gy_ss_web) 대 ASOS 파일 값(gy_ss)")
for lab, col in [("날씨누리 값(gy_ss_web)", "gy_ss_web"), ("ASOS 파일 값(gy_ss)", "gy_ss")]:
    for lab2, m in [("발전량 0 초과", df["gen_kwh"] > 0), ("발전량 0 인 24일 제외", z)]:
        mm = m & df[col].notna()
        print(f"  {lab} / {lab2}: 상관 {np.corrcoef(df.loc[mm, 'gen_kwh'], df.loc[mm, col])[0, 1]:.3f} (n={int(mm.sum())})")
d = (df["gy_ss_web"] - df["gy_ss_obs"]).dropna()
print(f"  두 일조 시간 값이 다른 날: {int((d.abs() > 1e-9).sum())} / {len(d)} (최대 차이 {d.abs().max():.1f}시간)")
ksj = c.SOLAR / "kma3_266_35.json"
print("  날씨누리 사본:", ksj.exists())

print("\n[3] 연도별 합의 비(광양 관측을 1 로 둠). 맑은 날(gy_kt>0.6)만 따로")
df["year"] = df["date"].dt.year
rows = []
for y, g in df[df["date"] <= "2025-12-31"].groupby("year"):
    o = g["gy_gsr_obs"].where(g["gy_gsr_suspect"] != 1)
    r = {"year": y}
    for lab, col in [("era5", "era5_gsr"), ("om", "om_gsr"), ("sat", "sat_gsr")]:
        m = o.notna() & g[col].notna()
        r[lab + "_all"] = round(g.loc[m, col].sum() / o[m].sum(), 3) if m.sum() > 100 else np.nan
        mc = m & (g["gy_kt"] > 0.6)
        r[lab + "_clear"] = round(g.loc[mc, col].sum() / o[mc].sum(), 3) if mc.sum() > 50 else np.nan
    rows.append(r)
t = pd.DataFrame(rows); print(t.to_string(index=False)); t.to_csv(c.HERE / "t3_07_ratio_by_year.csv", index=False)
for lab in ["era5_all", "era5_clear", "sat_all", "sat_clear"]:
    a = t.loc[t.year.between(2016, 2018), lab].mean(); b = t.loc[t.year.between(2023, 2025), lab].mean()
    print(f"  {lab}: 2016~2018 평균 {a:.3f} -> 2023~2025 평균 {b:.3f} ({(b / a - 1) * 100:+.1f}%)")
a = t.loc[t.year.between(2013, 2015), "era5_all"].mean(); b = t.loc[t.year.between(2023, 2025), "era5_all"].mean()
print(f"  era5_all: 2013~2015 평균 {a:.3f} -> 2023~2025 평균 {b:.3f} ({(b / a - 1) * 100:+.1f}%)")
a = t.loc[t.year.between(2013, 2015), "era5_clear"].mean(); b = t.loc[t.year.between(2023, 2025), "era5_clear"].mean()
print(f"  era5_clear: 2013~2015 평균 {a:.3f} -> 2023~2025 평균 {b:.3f} ({(b / a - 1) * 100:+.1f}%)")

print("\n[4] 이번에 받은 최신 응답(받은 시각은 api/meta_fetch_log.txt)")
s = json.load(open(c.HERE / "api" / "sat_recent_hourly.json"))["hourly"]
nn = [(a, b) for a, b in zip(s["time"], s["shortwave_radiation"]) if b is not None]
print("  위성 시간값: 값이 있는 마지막 시각", nn[-1], "| 2026-10-06 하루 합계", round(sum(b for a, b in nn if a.startswith('2026-10-06')) * 3600 / 1e6, 2), "MJ/m2")
a = json.load(open(c.HERE / "api" / "archive_recent_daily.json"))["daily"]
print("  보관 자료 기본값:", dict(zip(a["time"], a["shortwave_radiation_sum_archive_best_match"])))
print("  ERA5 단독      :", dict(zip(a["time"], a["shortwave_radiation_sum_era5"])))
f = json.load(open(c.HERE / "api" / "forecast_now_daily.json"))["daily"]
print("  Forecast API(jma_seamless):", dict(zip(f["time"], f["shortwave_radiation_sum"])))

print("\n[5] 사전 조사 3a 의 일조 시간 상관 0.899 다시 계산(날씨누리 사본 원값, 발전량 0 초과, 2013-01-01 ~ 2026-02-28)")
ss = pd.Series(json.load(open(c.SOLAR / "kma3_266_35.json")))
ss.index = pd.to_datetime(ss.index)
ca = pd.Series(json.load(open(c.SOLAR / "kma3_168_59.json")))
ca.index = pd.to_datetime(ca.index)
g = full.set_index("date")["gen_kwh"]
x = pd.DataFrame({"gen": g, "ss": ss, "ca": ca}).dropna()
x = x[x["gen"] != 0]
print(f"  광양 일조와 여수 운량이 모두 있는 날: 상관 {np.corrcoef(x['gen'], x['ss'])[0, 1]:.3f} (n={len(x)}), 여수 운량 {np.corrcoef(x['gen'], x['ca'])[0, 1]:.3f}")
print(f"  일조 시간이 14.5시간을 넘는 날: {x.index[x['ss'] > 14.5].strftime('%Y-%m-%d').tolist()} 값 {x.loc[x['ss'] > 14.5, 'ss'].tolist()}")
x2 = x[x["ss"] <= 14.5]
print(f"  그 날을 빼면: 상관 {np.corrcoef(x2['gen'], x2['ss'])[0, 1]:.3f} (n={len(x2)})")
x3 = x2[x2.index <= "2025-12-31"]
print(f"  2025-12-31 까지만: 상관 {np.corrcoef(x3['gen'], x3['ss'])[0, 1]:.3f} (n={len(x3)})")
x4 = x3[~x3.index.isin(full.loc[full['stop_day'] == 1, 'date'])]
print(f"  정지 표시 43일까지 빼면: 상관 {np.corrcoef(x4['gen'], x4['ss'])[0, 1]:.3f} (n={len(x4)})")
