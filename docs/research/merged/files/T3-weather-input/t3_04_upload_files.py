"""t3_04: 업로드 파일 세 개를 같은 기준으로 대조한다.

 (1) asos/hadong_upload.csv                      Volume = 하루 전(d-1) 광양 ASOS 일사량  (지난 관측)
 (2) asos/hadong_upload_forecast_proxy.csv       Volume = 하루 뒤(d+1) 광양 ASOS 일사량  (대상일 실제 값, 상한)
 (3) merged/gap1/hadong_upload_forecast_jma.csv  Volume = 하루 뒤(d+1)에 대한 24시간 전 예보 (JMA MSM)
실습 코드의 창(입력 행 i ~ i+19, 정답 행 i+20, 앞 80% 학습)을 옮겨 적어 정답일 기준으로 날씨 칸이 어느 날 값인지 센다.
project 모듈은 import 하지 않는다.
"""
import json

import numpy as np
import pandas as pd

import t3_common as c

pd.set_option("display.width", 250)
SEQ = 20
FILES = {
    "upload(지난 관측)": c.ASOS / "hadong_upload.csv",
    "proxy(상한)": c.ASOS / "hadong_upload_forecast_proxy.csv",
    "jma(24시간 전 예보)": c.GAP1 / "hadong_upload_forecast_jma.csv",
}
full = c.load_full().set_index("date")
pr = c.load_prevruns_daily().set_index("date")
raw = pd.read_csv(c.SOLAR / "data_15043409.csv", encoding="cp949")
gen = pd.Series(raw["총량(kw)"].astype(float).values, index=pd.to_datetime(raw["년월일"]))

info = {}
for name, path in FILES.items():
    u = pd.read_csv(path, parse_dates=["Date"])
    d = u["Date"]
    print(f"\n== {name}: {path.name}")
    print(f"  행 {len(u)}, {d.min().date()} ~ {d.max().date()}, 열 {list(u.columns)}, 하루 간격 어긋남 {int((d.diff().dropna() != pd.Timedelta(days=1)).sum())}, 빈 칸 {int(u.isna().sum().sum())}")
    print(f"  Close 범위 {u['Close'].min():.3f} ~ {u['Close'].max():.3f} | Volume 범위 {u['Volume'].min():.4f} ~ {u['Volume'].max():.4f} | Volume 이 정수인 행 {int((u['Volume'] % 1 == 0).sum())}")
    print(f"  Close 가 원본 같은 날 합계와 다른 행: {int((np.abs(u['Close'].values - gen.reindex(d).values) > 1e-9).sum())}")
    print(f"  Close <= 0 인 행 {int((u['Close'] <= 0).sum())} (스키마 gt=0 이면 이 날이 창에 든 /predict 요청은 422), Stop=1 인 행 {int((u['Stop'] == 1).sum())}")
    # Volume 이 어느 날의 어떤 값인지
    for k in [-1, 0, 1]:
        src = full["gy_gsr"].reindex(d + pd.Timedelta(days=k)).values
        same = int(np.sum(np.abs(u["Volume"].values - src) < 1e-9))
        src2 = pr["fc1_gsr"].reindex(d + pd.Timedelta(days=k)).round(4).values
        same2 = int(np.sum(np.abs(u["Volume"].values - src2) < 1e-9))
        print(f"  Volume[d] == 광양 ASOS 일사량[d{k:+d}] 인 행 {same:5d} | == 24시간 전 예보[d{k:+d}] 인 행 {same2:5d}")
    # 창
    n = len(u) - SEQ
    n_tr = int(n * 0.8)
    tgt = d.iloc[SEQ:].reset_index(drop=True)
    print(f"  창 표본 {n}개, 학습 {n_tr}개(정답일 {tgt.iloc[0].date()} ~ {tgt.iloc[n_tr - 1].date()}), 시험 {n - n_tr}개(정답일 {tgt.iloc[n_tr].date()} ~ {tgt.iloc[-1].date()})")
    # 스케일러: 전체 행 대 학습 구간 행(학습 표본이 쓰는 앞 n_tr+SEQ-1 행)
    head = u.iloc[: n_tr + SEQ - 1]
    print(f"  스케일 범위(전체 행) Close {u['Close'].min():.3f}~{u['Close'].max():.3f}, Volume {u['Volume'].min():.4f}~{u['Volume'].max():.4f}"
          f" | (학습 구간 행) Close {head['Close'].min():.3f}~{head['Close'].max():.3f}, Volume {head['Volume'].min():.4f}~{head['Volume'].max():.4f}")
    # 시차 상관
    out = []
    for k in [0, 1, 2]:
        y = u["Close"].shift(-k)
        m = y.notna() & (y > 0)
        out.append(f"Close[d{k:+d}]~Volume[d] {np.corrcoef(u.loc[m, 'Volume'], y[m])[0, 1]:+.3f}")
    print("  " + ", ".join(out))
    # 시험 구간 계절
    te = tgt.iloc[n_tr:]
    print("  시험 구간의 달별 일수:", te.dt.month.value_counts().sort_index().to_dict())
    info[name] = u.set_index("Date")

print("\n== 파일 사이 대조")
a, p, j = info["upload(지난 관측)"], info["proxy(상한)"], info["jma(24시간 전 예보)"]
ix = a.index.intersection(j.index)
print(f"  upload·proxy 와 jma 가 겹치는 날 {len(ix)}일 ({ix.min().date()} ~ {ix.max().date()}), Close 가 다른 날 {int((np.abs(a.loc[ix, 'Close'] - j.loc[ix, 'Close']) > 1e-9).sum())}")
s = c.stats_pair(p.loc[ix, "Volume"], j.loc[ix, "Volume"])
print("  같은 행의 Volume: 기준 proxy(대상일 ASOS 실제 값), 비교 jma(24시간 전 예보) ->", c.fmt(s))
print(f"  jma 에만 있는 날: {len(j.index.difference(a.index))}일 ({j.index.difference(a.index).min().date()} ~ {j.index.difference(a.index).max().date()})")
print(f"  upload·proxy 에만 있는 날: {len(a.index.difference(j.index))}일 ({a.index.difference(j.index).min().date()} ~ {a.index.difference(j.index).max().date()})")
print(f"  스케일 범위가 다르다: proxy Volume {p['Volume'].min():.2f}~{p['Volume'].max():.2f}, jma Volume {j['Volume'].min():.4f}~{j['Volume'].max():.4f}"
      f" | Close 최솟값 proxy {p['Close'].min():.3f}, jma {j['Close'].min():.3f}, 최댓값 proxy {p['Close'].max():.3f}, jma {j['Close'].max():.3f}")
# proxy 로 맞춘 스케일러에 jma 값을 넣으면 0~1 을 벗어나는가
vmin, vmax = p["Volume"].min(), p["Volume"].max()
z = (j["Volume"] - vmin) / (vmax - vmin)
print(f"  proxy 스케일러로 jma Volume 을 바꾸면 범위 {z.min():.3f} ~ {z.max():.3f} (0~1 밖 {int(((z < 0) | (z > 1)).sum())}행)")
vmin, vmax = j["Volume"].min(), j["Volume"].max()
z = (p.loc[ix, "Volume"] - vmin) / (vmax - vmin)
print(f"  jma 스케일러로 proxy Volume(겹치는 날) 을 바꾸면 범위 {z.min():.3f} ~ {z.max():.3f} (0~1 밖 {int(((z < 0) | (z > 1)).sum())}행)")

print("\n== 예보 파일의 2024-01-24 ~ 02-15: 모델을 jma_seamless 로 지정한 호출(q3)은 비어 있고 기본 모델 호출(d2r)은 값이 있다")
h = c.load_prevruns_hourly()
q = pd.DataFrame(json.load(open(c.SOLAR / "q3" / "pr_jma_seamless.json"))["hourly"])
q["time"] = pd.to_datetime(q["time"])
m = h.merge(q, on="time", suffixes=("_def", "_jma"))
col_d, col_j = "shortwave_radiation_previous_day1_def", "shortwave_radiation_previous_day1_jma"
both = m[col_d].notna() & m[col_j].notna()
print(f"  두 호출 모두 값이 있는 시간 {int(both.sum())}칸, 값이 다른 칸 {int((np.abs(m.loc[both, col_d] - m.loc[both, col_j]) > 1e-9).sum())}")
only = m[col_d].notna() & m[col_j].isna()
print(f"  기본 모델 호출에만 값이 있는 시간 {int(only.sum())}칸: {m.loc[only, 'time'].min()} ~ {m.loc[only, 'time'].max()}")
gapdays = pd.date_range("2024-01-24", "2024-02-15")
x = full.join(pr, how="left")
for lab, days in [("빈 구간 23일(2024-01-24~02-15)", gapdays), ("앞 23일(2024-01-01~01-23)", pd.date_range("2024-01-01", "2024-01-23")),
                  ("뒤 23일(2024-02-16~03-09)", pd.date_range("2024-02-16", "2024-03-09")),
                  ("다른 해 같은 날짜(2023, 2025)", pd.date_range("2023-01-24", "2023-02-15").append(pd.date_range("2025-01-24", "2025-02-15")))]:
    xs = x.loc[x.index.isin(days)]
    s1 = c.stats_pair(xs["gy_gsr"], xs["fc1_gsr"])
    s0 = c.stats_pair(xs["gy_gsr"], xs["fc0_gsr"])
    print(f"  {lab:30s} 24시간 전 예보 대 광양 관측: n={s1['n']} RMSE {s1['rmse']:.2f} 상관 {s1['r']:.3f} 합의 비 {s1['ratio_sum']:.3f} | 최신 실행분: RMSE {s0['rmse']:.2f} 상관 {s0['r']:.3f}")
hh = h[(h["time"] >= "2024-01-24") & (h["time"] < "2024-02-16")]
v = hh["shortwave_radiation_previous_day1"].dropna()
print(f"  빈 구간의 기본 모델 호출 시간값: {len(v)}칸, 정수가 아닌 값 {int((v % 1 != 0).sum())}칸, 낮 최대 {v.max():.0f} W/m2")
hh2 = h[(h["time"] >= "2024-02-16") & (h["time"] < "2024-03-10")]["shortwave_radiation_previous_day1"].dropna()
print(f"  뒤 23일의 시간값: {len(hh2)}칸, 정수가 아닌 값 {int((hh2 % 1 != 0).sum())}칸")
