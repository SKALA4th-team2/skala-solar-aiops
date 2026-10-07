"""업로드 형식 파일 hadong_upload_forecast_jma.csv 를 만들고 점검한다. 텐서플로를 쓰지 않는다.

열: Date, Close, Volume, Stop
  Close  = d 일의 하루 발전량(kWh). 원본 data_15043409.csv 의 '총량(kw)'.
  Volume = d+1 일에 대한 '24시간 전 일사량 예보'의 하루 합계(MJ/m2). Open-Meteo Previous Runs API 의
           shortwave_radiation_previous_day1 (시간 평균 W/m2, 기본 모델 = JMA) 24칸을 더해 x3600/1e6 한 값(어제 받아 둔 d2r/wx_prevruns_daily.csv).
  Stop   = asos/hadong_upload.csv 의 Stop 을 날짜로 맞춰 옮긴 값.
배치는 asos/hadong_upload_forecast_proxy.csv 와 같다(d 행에 d 일의 발전량과 d+1 일의 값). 실습 build_sequences 의 창(20행)에 넣으면
발전량 칸은 T-20 ~ T-1, 날씨 칸은 T-19 ~ T 가 된다(T = 대상일).
기간: 24시간 전 예보의 첫 날이 2022-07-03 이므로 첫 행은 2022-07-02, 마지막 행은 2026-02-27(= 2026-02-28 예보).
"""
import numpy as np
import pandas as pd

from lstm_common import CSV, HERE, WXD
from practice_copy import SEQ_LEN, HAICScaler, build_sequences, load_rows, train_test_split

ASOS = HERE.parent.parent / "asos"
OUT = HERE / "hadong_upload_forecast_jma.csv"
pd.set_option("display.width", 220)

# ---------- 원본 ----------
raw = pd.read_csv(CSV, encoding="cp949")
raw["date"] = pd.to_datetime(raw["년월일"])
raw = raw.sort_values("date")
gen = raw.set_index("date")["총량(kw)"].astype(float)
assert gen.index.is_unique and (gen.index.to_series().diff().dropna().dt.days == 1).all()

pr = pd.read_csv(WXD / "wx_prevruns_daily.csv", parse_dates=["date"]).set_index("date")
fc1 = pr["shortwave_radiation_previous_day1"].dropna()

# 일별 값이 시간값에서 나온 것인지(단위 변환 포함) 따로 다시 계산해 대조한다
hh = pd.read_csv(WXD / "wx_prevruns_hourly.csv", parse_dates=["time"])
g = hh.groupby(hh["time"].dt.normalize())["shortwave_radiation_previous_day1"]
fc1_re = (g.sum() * 3600 / 1e6).where(g.count() == 24).dropna()
assert fc1_re.index.equals(fc1.index)
print(f"[예보] 24시간 전 일사량 예보: {len(fc1)}일 {fc1.index.min().date()} ~ {fc1.index.max().date()}, 시간값(W/m2) 24칸 합 x 3600/1e6 으로 다시 만든 값과 최대차 {np.abs(fc1_re - fc1).max():.2e} MJ/m2")
print(f"[예보] 시간값 범위 {hh['shortwave_radiation_previous_day1'].min():.0f} ~ {hh['shortwave_radiation_previous_day1'].max():.0f} W/m2, 하루 합계 범위 {fc1.min():.4f} ~ {fc1.max():.4f} MJ/m2, 평균 {fc1.mean():.2f}")

# ---------- 파일 만들기 ----------
first = fc1.index.min() - pd.Timedelta(days=1)          # 2022-07-02
last = min(gen.index.max(), fc1.index.max() - pd.Timedelta(days=1))   # 2026-02-27
idx = pd.date_range(first, last, freq="D")
vol = fc1.reindex(idx + pd.Timedelta(days=1)).to_numpy()     # d 행 <- d+1 일의 예보
up_asos = pd.read_csv(ASOS / "hadong_upload.csv", parse_dates=["Date"]).set_index("Date")
px_asos = pd.read_csv(ASOS / "hadong_upload_forecast_proxy.csv", parse_dates=["Date"]).set_index("Date")
stop = up_asos["Stop"].reindex(idx)
n_missing_stop = int(stop.isna().sum())
miss = idx[stop.isna().to_numpy()]
# hadong_upload.csv 에 없는 날짜: 옮길 값이 없다. ASOS 쪽 정지 규칙(hadong_build/hd_01_build.py: 발전량 0, 또는 1 미만, 또는 10 미만이면서 일사량 8 이상)을
# 발전량에 적용하면 발전량이 10kWh 이상인 날은 날씨와 무관하게 0 이다.
if n_missing_stop:
    gmin = gen.reindex(miss).min()
    print(f"[Stop] hadong_upload.csv 에 없는 날짜 {n_missing_stop}일 ({miss.min().date()} ~ {miss.max().date()}): 그 기간 최소 발전량 {gmin:.3f} kWh ({gen.reindex(miss).idxmin().date()})")
    assert gmin >= 10.0, "정지 규칙에 걸릴 수 있는 날이 있어 0 으로 채울 수 없다"
    stop = stop.fillna(0)
out = pd.DataFrame({"Date": idx.strftime("%Y-%m-%d"), "Close": gen.reindex(idx).to_numpy(), "Volume": np.round(vol, 4), "Stop": stop.astype(int).to_numpy()})
out.to_csv(OUT, index=False, encoding="utf-8", lineterminator="\n")
print(f"[저장] {OUT.name}: {len(out)}행, {out['Date'].iloc[0]} ~ {out['Date'].iloc[-1]}")

# ---------- 점검 (저장한 파일을 다시 읽어서) ----------
f = pd.read_csv(OUT)
D = pd.to_datetime(f["Date"])
chk = {}
chk["열 이름"] = list(f.columns) == ["Date", "Close", "Volume", "Stop"]
chk["빈 값 0개"] = int(f.isna().sum().sum()) == 0
chk["날짜 중복 0개"] = int(D.duplicated().sum()) == 0
chk["날짜가 하루 간격으로 이어짐"] = bool((D.diff().dropna().dt.days == 1).all())
chk["Close = 원본의 같은 날 발전량(전 행)"] = bool(np.allclose(f["Close"].to_numpy(), gen.reindex(D).to_numpy(), atol=0, rtol=0))
chk["Volume = 다음 날의 24시간 전 예보(전 행, 반올림 4자리)"] = bool(np.allclose(f["Volume"].to_numpy(), fc1.reindex(D + pd.Timedelta(days=1)).to_numpy(), atol=5e-5, rtol=0))
ov = D[D.isin(up_asos.index)]
m = f.set_index(D)
chk[f"겹치는 {len(ov)}일에서 Close 가 asos/hadong_upload.csv 와 같음"] = bool((m.loc[ov, "Close"].to_numpy() == up_asos.loc[ov, "Close"].to_numpy()).all())
chk[f"겹치는 {len(ov)}일에서 Close 가 asos/hadong_upload_forecast_proxy.csv 와 같음"] = bool((m.loc[ov, "Close"].to_numpy() == px_asos.loc[ov, "Close"].to_numpy()).all())
chk[f"겹치는 {len(ov)}일에서 Stop 이 asos/hadong_upload.csv 와 같음"] = bool((m.loc[ov, "Stop"].to_numpy() == up_asos.loc[ov, "Stop"].to_numpy()).all())
chk["Close 0 이상, Volume 0 이상"] = bool((f["Close"] >= 0).all() and (f["Volume"] >= 0).all())
for k, v in chk.items():
    print(f"[점검] {'통과' if v else '실패'}: {k}")
assert all(chk.values())
print(f"[점검] Stop=1 인 행 {int(f['Stop'].sum())}개 (hadong_upload.csv 의 같은 기간 Stop 합 {int(up_asos.loc[ov, 'Stop'].sum())}). Close 최소 {f['Close'].min():.3f} ({f.loc[f['Close'].idxmin(), 'Date']}), 최대 {f['Close'].max():.3f}; Volume 최소 {f['Volume'].min():.4f}, 최대 {f['Volume'].max():.4f}")

# 날짜 밀림: 시차 상관
c, v = f["Close"], f["Volume"]
print("[밀림] 상관 Close[d+k] 대 Volume[d]: " + ", ".join(f"k={k:+d} {c.shift(-k).corr(v):+.3f}" for k in (-1, 0, 1, 2, 3)) + "  (k=+1 이 가장 커야 한다: d 행의 Volume 은 d+1 일의 예보)")
pv = px_asos["Volume"].reindex(D).to_numpy()       # 같은 배치의 ASOS 실제 일사량(d+1 일)
okp = ~np.isnan(pv)
print("[밀림] 상관 이 파일 Volume[d+k] 대 hadong_upload_forecast_proxy.csv Volume[d] (같은 배치면 k=0 이 가장 커야 한다): "
      + ", ".join(f"k={k:+d} {pd.Series(pv).corr(v.shift(-k)):+.3f}" for k in (-1, 0, 1)) + f"  (겹치는 {int(okp.sum())}일)")

# ---------- 실습 코드(옮겨 적은 사본)로 읽기 ----------
rows = load_rows(str(OUT))
scaler = HAICScaler().fit(rows)
X, y = build_sequences(rows, scaler)
Xtr, ytr, Xte, yte = train_test_split(X, y)
Xa = np.array(X, dtype="float32")
dates = [r["Date"] for r in rows]
n_tr, n_te = len(Xtr), len(Xte)
print(f"[실습 코드로 읽기] 행 {len(rows)}, X {Xa.shape}, 학습 {n_tr}문제(정답일 {dates[SEQ_LEN]} ~ {dates[SEQ_LEN + n_tr - 1]}), 시험 {n_te}문제(정답일 {dates[SEQ_LEN + n_tr]} ~ {dates[-1]})")
print(f"[실습 코드로 읽기] 스케일러(전체 행): Close {scaler.close_min} ~ {scaler.close_max}, Volume {scaler.volume_min} ~ {scaler.volume_max}")
s2 = HAICScaler().fit(rows[:SEQ_LEN + n_tr])
print(f"[실습 코드로 읽기] 학습 구간 행만으로 맞춘 스케일러: Close {s2.close_min} ~ {s2.close_max}, Volume {s2.volume_min} ~ {s2.volume_max} -> 전체 행 기준과 같음: "
      f"{(s2.close_min, s2.close_max, s2.volume_min, s2.volume_max) == (scaler.close_min, scaler.close_max, scaler.volume_min, scaler.volume_max)}")
print(f"[실습 코드로 읽기] 업로드 최소 행 수(SEQ_LEN 20 + WINDOW_SIZE 21 = 41) 이상: {len(rows) >= 41}. 시험 구간의 Stop 합 {int(f['Stop'].iloc[SEQ_LEN + n_tr:].sum())}, 학습 구간의 Stop 합 {int(f['Stop'].iloc[:SEQ_LEN + n_tr].sum())}")

# 표본 창 직접 찍기: 원본에서 날짜로 찾은 값과 칸마다 대조
print("[표본 창] X 를 되돌린 값과 원본을 날짜로 대조한다")
for i in [0, n_tr - 1, n_tr, len(X) - 1]:
    T = pd.Timestamp(dates[i + SEQ_LEN])
    win = [pd.Timestamp(d) for d in dates[i:i + SEQ_LEN]]
    xc = Xa[i, :, 0] * (scaler.close_max - scaler.close_min) + scaler.close_min
    xv = Xa[i, :, 1] * (scaler.volume_max - scaler.volume_min) + scaler.volume_min
    ok_c = np.allclose(xc, gen.reindex(win).to_numpy(), atol=1e-3)
    ok_v = np.allclose(xv, fc1.reindex([w + pd.Timedelta(days=1) for w in win]).to_numpy(), atol=1e-3)
    ok_v_same = np.allclose(xv, fc1.reindex(win).to_numpy(), atol=1e-3) if all(w in fc1.index for w in win) else False
    print(f"   문제 {i}: 정답일 T = {T.date()} (y {y[i]:.3f} = 원본 {gen[T]:.3f}) | 발전량 칸 {win[0].date()} ~ {win[-1].date()} (= T-20 ~ T-1, 원본과 일치 {ok_c}, 정답일 포함 {T in win}) | "
          f"날씨 칸 = {(win[0] + pd.Timedelta(days=1)).date()} ~ {(win[-1] + pd.Timedelta(days=1)).date()} 의 24시간 전 예보 (= T-19 ~ T, 일치 {ok_v}; 같은 날 예보로 읽으면 일치 {ok_v_same}) | 마지막 칸 {xv[-1]:.4f} = {T.date()} 예보 {fc1[T]:.4f}")
# 전 칸 대조
allc = np.array([gen.reindex(pd.to_datetime(dates)).to_numpy()[i:i + SEQ_LEN] for i in range(len(X))])
allv = np.array([fc1.reindex(pd.to_datetime(dates) + pd.Timedelta(days=1)).to_numpy()[i:i + SEQ_LEN] for i in range(len(X))])
dc = np.abs(Xa[:, :, 0] * (scaler.close_max - scaler.close_min) + scaler.close_min - allc).max()
dv = np.abs(Xa[:, :, 1] * (scaler.volume_max - scaler.volume_min) + scaler.volume_min - allv).max()
print(f"[표본 창] 전체 {Xa.shape[0]}문제 x 20칸 x 2: 원본과의 최대차 발전량 {dc:.2e} kWh, 예보 {dv:.2e} MJ/m2 (float32 와 4자리 반올림 오차 범위)")

# ---------- 단위와 수준: ASOS 광양 일사량, 재분석과 비교 ----------
full = pd.read_csv(ASOS / "hadong_daily_full.csv", parse_dates=["date"]).set_index("date")
ar = pd.read_csv(WXD / "wx_archive_daily.csv", parse_dates=["date"]).set_index("date")["shortwave_radiation_sum"]
cmp = pd.DataFrame({"fc1": fc1, "asos": full["gy_gsr"], "era": ar, "fc0": pr["shortwave_radiation"]}).dropna(subset=["fc1"])
print("[단위] 예보(이 파일의 Volume)는 MJ/m2(하루 합계)이고 ASOS sumGsr 도 MJ/m2 다. 출처가 다르다: 예보 = JMA 모델 격자(35.05N, 127.75E)의 예보값, ASOS = 광양(266) 관측값.")
for name, col in [("ASOS 광양 실제 일사량(같은 날)", "asos"), ("Open-Meteo 재분석 실제 일사량(같은 날)", "era"), ("예보 모델 최신 실행분(같은 날)", "fc0")]:
    t = cmp.dropna(subset=[col])
    b1, b0 = np.polyfit(t["fc1"], t[col], 1)
    print(f"   24시간 전 예보 대 {name}: {len(t)}일 ({t.index.min().date()} ~ {t.index.max().date()}), 평균 {t['fc1'].mean():.2f} 대 {t[col].mean():.2f} (합의 비 {t['fc1'].sum() / t[col].sum():.3f}), "
          f"상관 {t['fc1'].corr(t[col]):.3f}, RMSE {np.sqrt(((t['fc1'] - t[col]) ** 2).mean()):.2f} MJ/m2 (평균의 {np.sqrt(((t['fc1'] - t[col]) ** 2).mean()) / t[col].mean() * 100:.1f}%), 직선 {name[:4]} = {b0:.2f} + {b1:.3f} x 예보, "
          f"범위 예보 {t['fc1'].min():.2f} ~ {t['fc1'].max():.2f} / {t[col].min():.2f} ~ {t[col].max():.2f}")
pa = pd.read_csv(ASOS / "hadong_upload_forecast_proxy.csv")
print(f"[단위] 스케일 범위 비교: 이 파일 Volume {f['Volume'].min():.4f} ~ {f['Volume'].max():.4f}, hadong_upload_forecast_proxy.csv Volume {pa['Volume'].min():.2f} ~ {pa['Volume'].max():.2f}, Close {f['Close'].min():.3f} ~ {f['Close'].max():.3f} 대 {pa['Close'].min():.3f} ~ {pa['Close'].max():.3f}")
