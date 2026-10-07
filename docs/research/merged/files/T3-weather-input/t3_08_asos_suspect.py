"""t3_08: 광양 ASOS 일사량이 격자 자료(위성, 보관 자료) 둘 다보다 크게 낮거나 높은 날을 찾는다.

ASOS 분석은 '낮게 기록된 것으로 보이는 날' 3일(2013-07-10, 2017-07-18, 2022-12-23)을 표시했다.
사전 조사의 격자 자료를 독립 기준으로 삼으면 같은 날이 걸리는지, 더 있는지 본다.
기준(분석자가 정함): |광양 - 보관 자료| > 8 MJ/m2 이고, 위성이 있으면 |광양 x 1.10 - 위성| > 8 MJ/m2 도 같은 방향.
"""
import numpy as np
import pandas as pd
import t3_common as c

pd.set_option("display.width", 250)
full = c.load_full(); arc = c.load_archive(); sat, _ = c.load_himawari(); pw = c.load_power()
df = full.merge(arc, on="date", how="left").merge(sat, on="date", how="left").merge(pw, on="date", how="left")
o = df["gy_gsr_obs"]
d_om = o - df["om_gsr"]
d_sat = o * 1.10 - df["sat_gsr"]
low = (d_om < -8) & ((d_sat < -8) | df["sat_gsr"].isna())
high = (d_om > 8) & ((d_sat > 8) | df["sat_gsr"].isna())
cols = ["date", "gen_kwh", "gy_gsr_obs", "gy_gsr_suspect", "gy_ss", "gy_ss_fill", "gy_ssdur", "om_gsr", "era5_gsr", "sat_gsr", "power_gsr", "stop_day"]
print("광양이 격자 자료보다 8 MJ/m2 넘게 낮은 날:", int(low.sum()))
print(df.loc[low, cols].round(2).to_string(index=False))
print("\n광양이 격자 자료보다 8 MJ/m2 넘게 높은 날:", int(high.sum()))
print(df.loc[high, cols].round(2).to_string(index=False))
print("\nASOS 분석이 표시한 3일:")
print(df.loc[df["gy_gsr_suspect"] == 1, cols].round(2).to_string(index=False))
# 낮게 걸린 날 가운데 발전량이 높았던 날(관측이 낮게 기록됐을 가능성이 큰 날)
df["eff"] = df["gen_kwh"] / df["gy_gsr_obs"]
m = (df["stop_day"] == 0) & o.notna()
q99 = df.loc[m, "eff"].quantile(0.99)
print(f"\n발전량 / 광양 일사량 비가 상위 1%({q99:.1f} kWh per MJ/m2)를 넘는 날 가운데 위에서 '낮은 날'로 걸린 날:")
print(df.loc[low & (df["eff"] > q99), ["date", "gen_kwh", "gy_gsr_obs", "om_gsr", "sat_gsr", "eff"]].round(2).to_string(index=False))
df.loc[low | high, cols].to_csv(c.HERE / "t3_08_asos_suspect_days.csv", index=False)
