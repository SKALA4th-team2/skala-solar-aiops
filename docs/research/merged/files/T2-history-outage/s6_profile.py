"""s6: 맑은 날 최대 출력은 2024~2025년 여름에 돌아왔는데 하루 발전량 기준 지표(성능 지표, 발전량÷일사량)는 여름이 여전히 낮게 나오는 이유를 본다.
맑은 날(Open-Meteo 일조율 0.85 이상, 이벤트일 제외)의 하루 모양: 일합계÷시간 최대(등가 시간), 오전(열 8~12) 합, 오후(열 14~18) 합, 오후÷오전.
이웃(변전소)의 같은 값도 함께 본다(날씨나 계절 탓인지 가리기 위해). 사후 진단값이다."""
import numpy as np, pandas as pd
from t2_common import *
pd.set_option("display.width", 250)
df, H = load_raw(); nb, nbH = load_neighbors(df.index); w = load_weather(df.index)
cal = pd.read_csv(SOLAR / "ev" / "day_table_all.csv", encoding="utf-8-sig", parse_dates=["날짜"]).set_index("날짜")
ev = cal["범주"].fillna("").str.split("_").str[0].reindex(df.index).isin(["A", "B", "C", "C2"])
d = pd.DataFrame({"y": df.y, "peak": df.peak, "am": H[:, 7:12].sum(1), "pm": H[:, 13:18].sum(1), "mid": H[:, 11:14].sum(1)}, index=df.index)
S = nbH["subst"]; d["s_y"] = nb["subst"]; d["s_peak"] = np.nanmax(S, axis=1); d["s_am"] = np.nansum(S[:, 7:12], 1); d["s_pm"] = np.nansum(S[:, 13:18], 1)
d["clear"] = (w.sunfrac >= 0.85) & ~ev; d["sw"] = w.sw
rows = []
for yv in range(2013, 2026):
    for nm, a0, a1 in [("여름(6~9월)", f"{yv}-06-01", f"{yv}-09-30"), ("겨울(11~2월)", f"{yv}-11-01", f"{yv+1}-02-28")]:
        x = d.loc[a0:a1]; x = x[x.clear & (x.s_y > 50)]
        rows.append(dict(해=yv, 철=nm, n=len(x), 등가시간=(x.y / x.peak).median(), 오후오전비=(x.pm / x.am).median(), 변전소_등가시간=(x.s_y / x.s_peak).median(), 변전소_오후오전비=(x.s_pm / x.s_am).median(),
                         오전_변전소대비=(x.am.sum() / x.s_am.sum()), 한낮_일사대비=(x.mid.sum() / x.sw.sum()), 오후_변전소대비=(x.pm.sum() / x.s_pm.sum()), 일합계_변전소대비=x.y.sum() / x.s_y.sum()))
T = pd.DataFrame(rows)
for nm in ("여름(6~9월)", "겨울(11~2월)"):
    print("\n==", nm); print(T[T.철 == nm].drop(columns="철").set_index("해").round(3).to_string())
T.to_csv(HERE / "s6_profile.csv", index=False, encoding="utf-8-sig")
