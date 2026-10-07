"""t3_10: 감시 지표의 분모로 쓸 날씨 자료를 고르기 위한 참고 계산.

지표: 최근 21일 (발전량 합 / 일사량 합). 수평면 일사량을 쓰면 계절에 따라 비가 달라지므로
연중 일수의 조화항 2개(sin, cos x 2)로 계절 곡선을 맞춰 걷어 낸 뒤, 남은 흔들림의 표준편차(%)를 본다.
구간: 2022-07-24 ~ 2025-12-30 (모든 자료가 있고 정지 표시가 없는 구간). 계절 곡선도 같은 구간으로 맞춘다(사후 계산, 참고용).
날씨는 모두 그날이 지난 뒤에 계산하는 사후 값이다. 예보 열만 그날 이전에 받을 수 있다.
"""
import numpy as np
import pandas as pd
import t3_common as c

full = c.load_full(); arc = c.load_archive(); sat, _ = c.load_himawari(); pr = c.load_prevruns_daily()
df = full.merge(arc, on="date", how="left").merge(sat, on="date", how="left").merge(pr, on="date", how="left").sort_values("date").reset_index(drop=True)
m = (df["date"] >= "2022-07-03") & (df["date"] <= "2025-12-30")
d = df[m].reset_index(drop=True)
doy = d["date"].dt.dayofyear.values
X = np.column_stack([np.ones(len(d))] + [f(2 * np.pi * k * doy / 365.25) for k in (1, 2) for f in (np.sin, np.cos)])
print("구간", d["date"].min().date(), "~", d["date"].max().date(), "| 정지 표시", int(d["stop_day"].sum()))
rows = []
for lab, col in [("광양 ASOS 수평면 일사량", "gy_gsr"), ("광양 ASOS 경사면 27도 환산", "gy_gsr_tilt27"), ("히마와리 위성", "sat_gsr"),
                 ("Open-Meteo 보관 자료 기본값", "om_gsr"), ("JMA 최신 실행분", "fc0_gsr"), ("JMA 24시간 전 예보", "fc1_gsr")]:
    for win in (21, 30):
        ok = d[col].notna()
        g = d["gen_kwh"].where(ok).rolling(win, min_periods=int(win * 0.9)).sum()
        w = d[col].rolling(win, min_periods=int(win * 0.9)).sum()
        r = np.log(g / w)
        mm = r.notna()
        beta = np.linalg.lstsq(X[mm], r[mm], rcond=None)[0]
        with np.errstate(all="ignore"):          # macOS numpy 의 matmul 경고(값에는 영향 없음)를 끈다
            res = r[mm] - X[mm] @ beta
        assert np.isfinite(res).all()
        rows.append(dict(자료=lab, 창=win, 남은_흔들림_표준편차_pct=round(float(res.std() * 100), 2),
                         p5_pct=round(float(np.percentile(res, 5) * 100), 1), p95_pct=round(float(np.percentile(res, 95) * 100), 1), n=int(mm.sum())))
t = pd.DataFrame(rows)
print(t.to_string(index=False))
t.to_csv(c.HERE / "t3_10_monitor_noise.csv", index=False)
