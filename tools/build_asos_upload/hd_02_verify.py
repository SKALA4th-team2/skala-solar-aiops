"""hd_02_verify.py — 만든 파일 3종(과 보조 2종)을 원자료·다른 분석 결과와 대조한다. 파일을 고치지 않는다.

실행: /Users/psm/workspace/skala-aiops/mlflow/.venv/bin/python hd_02_verify.py
원자료는 만들 때 쓴 코드와 따로, 문자열로 읽어 날짜를 맞춘다.
"""
import csv
import importlib.util
import json
import os
import sys
import warnings

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
pd.set_option("display.width", 250); pd.set_option("display.max_columns", 60); pd.set_option("display.max_rows", 200)
HERE = os.path.dirname(os.path.abspath(__file__))
ASOS = os.path.dirname(HERE)
SOLAR = os.path.join(ASOS, "..", "solar", "data_15043409.csv")
ASOS_DIR = "/Users/psm/Downloads/연도별 통합 DATA"
ok_all = True


def check(name, cond, detail=""):
    global ok_all
    ok_all &= bool(cond)
    print(("[OK]   " if cond else "[FAIL] ") + name + (" | " + detail if detail else ""))


full = pd.read_csv(os.path.join(ASOS, "hadong_daily_full.csv"), dtype=str, keep_default_na=False)
print("===== 1. hadong_daily_full.csv =====")
print("열:", list(full.columns))
dates = pd.to_datetime(full["date"])
check("행 수 4,807", len(full) == 4807, str(len(full)))
check("날짜 2013-01-01 ~ 2026-02-28, 하루씩 이어짐, 중복 없음",
      full["date"].iloc[0] == "2013-01-01" and full["date"].iloc[-1] == "2026-02-28"
      and (dates.diff().dropna().dt.days == 1).all() and dates.is_unique)
raw_bytes = open(os.path.join(ASOS, "hadong_daily_full.csv"), "rb").read()
check("UTF-8 로 읽히고 BOM 없음", not raw_bytes.startswith(b"\xef\xbb\xbf") and raw_bytes.decode("utf-8") is not None)
wx = full["wx_available"] == "1"
print("\n빈 값 개수(열별): 날씨가 있는 구간(2013~2025, %d일) / 2026-01~02(%d일)" % (wx.sum(), (~wx).sum()))
blank = pd.DataFrame({"2013~2025": (full[wx] == "").sum(), "2026-01~02": (full[~wx] == "").sum()})
print(blank[(blank.sum(axis=1) > 0)].to_string())
no_blank_cols = ["date", "gen_kwh", "peak_kw", "gen_hours", "zero_gen", "near_zero_stop", "stop_day", "wx_available",
                 "gy_gsr_fill", "gy_ss_fill", "gy_ssdur", "pi_valid"]
check("발전 실적·표시 열에는 전 기간 빈 값 없음", (full[no_blank_cols] == "").sum().sum() == 0, str((full[no_blank_cols] == "").sum()[lambda s: s > 0].to_dict()))
check("채운 날씨 열(gy_gsr, gy_ss, gy_sun_frac, gy_kt, gy_gsr_tilt27)은 2013~2025 에 빈 값 없음",
      (full.loc[wx, ["gy_gsr", "gy_ss", "gy_sun_frac", "gy_kt", "gy_gsr_tilt27"]] == "").sum().sum() == 0)
check("2026-01~02 에는 날씨에서 나온 열이 모두 비어 있음(gy_ssdur, gy_ss_web 제외)",
      (full.loc[~wx, ["gy_gsr_obs", "gy_gsr", "gy_ss_obs", "gy_ss", "gy_sun_frac", "gy_kt", "gy_gsr_tilt27", "gy_max_ta",
                      "pi_expected_kwh", "pi_daily", "pi_outage", "pi_partial_suspect", "pi_21d", "pi_30d"]] != "").sum().sum() == 0)
for c, why in (("gy_gsr_obs", "관측 빈 날"), ("gy_ss_obs", "관측 빈 날"), ("gy_max_ta", "관측 빈 날"), ("gy_ss_web", "웹 자료 빈 날·가조시간 넘는 값"),
               ("pi_expected_kwh", "일사량·일조·최고기온 중 하나가 빈 날"), ("pi_21d", "창 앞머리와 유효일 부족"), ("pi_30d", "창 앞머리와 유효일 부족")):
    b_ = full.loc[wx & (full[c] == ""), "date"].tolist()
    print(f"  {c} 빈 날 {len(b_)}일({why}):", b_ if len(b_) <= 13 else f"{b_[:3]} ... {b_[-3:]}")

f = full.replace("", np.nan)
num = [c for c in f.columns if c not in ("date", "gy_gsr_fill", "gy_ss_fill")]
f[num] = f[num].astype(float)
f.index = dates

# ---- 발전 실적 원본과 대조 (csv 모듈로 따로 읽음)
with open(SOLAR, encoding="cp949", newline="") as fh:
    rd = list(csv.reader(fh))
hdr, body = rd[0], rd[1:]
raw_gen = {r[0]: r for r in body}
check("원본 발전 실적 4,807행", len(body) == 4807)
gen_ok = peak_ok = hrs_ok = True
for d, row in zip(full["date"], f.itertuples()):
    r = raw_gen[d]
    hv = [float(x) for x in r[8:32]]
    gen_ok &= abs(float(r[2]) - row.gen_kwh) < 5e-4
    peak_ok &= abs(max(hv) - row.peak_kw) < 5e-4
    hrs_ok &= sum(1 for x in hv if x > 0) == int(row.gen_hours)
check("gen_kwh = 원본 총량(kw) (4,807일 모두)", gen_ok)
check("peak_kw = 원본 시간대별 값의 최댓값 (모두)", peak_ok)
check("gen_hours = 원본 시간대별 값이 0보다 큰 시간 수 (모두)", hrs_ok)
peak_col = max(abs(float(raw_gen[d][4]) - v) for d, v in zip(full["date"], f.peak_kw))
print("  참고: 원본 '최대(kw)' 열과 peak_kw 의 최대 차이 %.4f" % peak_col)
for d in ("2013-01-01", "2021-05-18", "2026-02-28"):
    r = raw_gen[d]
    print(f"  대조 {d}: 원본 총량 {r[2]}, 시간대 최대 {max(float(x) for x in r[8:32])}, 0초과 시간 수 {sum(float(x) > 0 for x in r[8:32])}"
          f" | 파일 gen_kwh {f.gen_kwh[d]}, peak_kw {f.peak_kw[d]}, gen_hours {int(f.gen_hours[d])}")

# ---- ASOS 원본과 대조 (문자열로 따로 읽음)
frames = []
for y in range(2013, 2026):
    a = pd.read_csv(os.path.join(ASOS_DIR, f"ASOS_{y}.csv"), encoding="utf-8-sig", dtype=str, keep_default_na=False,
                    usecols=["stnId", "stnNm", "tm", "sumGsr", "sumSsHr", "ssDur", "maxTa"])
    frames.append(a[a["stnId"].isin(["266", "192", "263"])])
a = pd.concat(frames, ignore_index=True)
st = {}
for sid in ("266", "192", "263"):
    d = a[a.stnId == sid].copy()
    d.index = pd.to_datetime(d["tm"])
    st[sid] = d.replace("", np.nan)[["sumGsr", "sumSsHr", "ssDur", "maxTa"]].astype(float).sort_index()
    print(f"  ASOS {sid} {a[a.stnId == sid].stnNm.iloc[0]}: {len(st[sid])}일 {st[sid].index.min().date()} ~ {st[sid].index.max().date()}")
gy, jj, ur = st["266"], st["192"], st["263"]
W = f.loc[:"2025-12-31"]


def same(x, y):
    x, y = np.asarray(x, float), np.asarray(y, float)
    return bool(((np.isnan(x) & np.isnan(y)) | (np.abs(x - y) < 1e-9)).all())


check("gy_gsr_obs = 광양(266) sumGsr 원본 (4,748일, 빈 값 위치 포함)", same(W.gy_gsr_obs, gy.sumGsr.reindex(W.index)))
check("gy_ss_obs = 광양 sumSsHr 원본 (4,748일)", same(W.gy_ss_obs, gy.sumSsHr.reindex(W.index)))
check("gy_max_ta = 광양 maxTa 원본", same(W.gy_max_ta, gy.maxTa.reindex(W.index)))
m = gy.ssDur.reindex(W.index).notna()
check("gy_ssdur = 광양 ssDur 원본 (값이 있는 날)", same(W.gy_ssdur[m], gy.ssDur.reindex(W.index)[m]),
      "원본이 빈 날 %d일: %s -> 식으로 계산한 값 %s" % ((~m).sum(), [str(x.date()) for x in W.index[~m]], W.gy_ssdur[~m].tolist()))

print("\n-- 빠진 날과 채운 값")
miss_g = W.index[W.gy_gsr_obs.isna()]
print("광양 일사량이 빈 날:", [str(x.date()) for x in miss_g])
check("일사량이 빈 날 5일이 분석 A1 의 목록과 같음",
      [str(x.date()) for x in miss_g] == ["2017-07-05", "2018-07-02", "2018-07-03", "2021-01-08", "2024-10-18"])
for d in miss_g:
    src = full.loc[full.date == str(d.date()), "gy_gsr_fill"].iloc[0]
    print(f"  {d.date()} 채운 값 {W.gy_gsr[d]} ({src}) | 진주 {jj.sumGsr.get(d)} 의령군 {ur.sumGsr.get(d)}")
    exp = ur.sumGsr[d] if (pd.Timestamp("2016-01-07") <= d <= pd.Timestamp("2018-04-05")) else jj.sumGsr[d]
    check(f"  {d.date()} 채움 규칙(진주, 고장 구간이면 의령군)", abs(W.gy_gsr[d] - exp) < 1e-9)
check("일사량이 있는 날은 gy_gsr = gy_gsr_obs", same(W.gy_gsr[W.gy_gsr_obs.notna()], W.gy_gsr_obs[W.gy_gsr_obs.notna()]))
diff_s = W.index[~((W.gy_ss_obs == W.gy_ss) & W.gy_ss_obs.notna())]
print("일조 시간을 고친 날:", [str(x.date()) for x in diff_s])
for d in diff_s:
    print(f"  {d.date()} 원본 {W.gy_ss_obs[d]} (가조시간 {W.gy_ssdur[d]}) -> {W.gy_ss[d]} | 진주 {jj.sumSsHr.get(d)}")
check("일조 시간을 고친 날은 10일(빈 날 9 + 2015-06-06 26.5시간)이고 모두 진주 값",
      len(diff_s) == 10 and int(W.gy_ss_obs.isna().sum()) == 9 and W.gy_ss_obs["2015-06-06"] == 26.5
      and same(W.gy_ss[diff_s], jj.sumSsHr.reindex(diff_s)))
check("gy_ss <= gy_ssdur (모든 날)", bool((W.gy_ss <= W.gy_ssdur + 0.05).all()), "최대 일조율 %.4f" % W.gy_sun_frac.max())
check("gy_sun_frac = gy_ss / gy_ssdur", np.abs(W.gy_sun_frac - W.gy_ss / W.gy_ssdur).max() < 6e-5)
check("gy_gsr_suspect 3일", [str(x.date()) for x in W.index[W.gy_gsr_suspect == 1]] == ["2013-07-10", "2017-07-18", "2022-12-23"],
      str(W.gy_gsr[W.gy_gsr_suspect == 1].tolist()))

print("\n-- 가조시간 식(위도 34.94)과 ASOS ssDur 의 차이")
sys.path.insert(0, HERE)
import hd_01_build as B
calc = np.round(B.daylen_refr(gy.index, B.LAT_GY), 1)
dd = (gy.ssDur.values - calc)[gy.ssDur.notna().values]
print("  2013~2025 %d일: 평균 차이 %+.3f, RMSE %.3f, 최대 |차이| %.2f 시간" % (len(dd), dd.mean(), np.sqrt((dd ** 2).mean()), np.abs(dd).max()))

print("\n-- 발전 정지 표시")
z = [str(x.date()) for x in f.index[f.zero_gen == 1]]
z_given = ["2016-12-22", "2016-12-23", "2016-12-24", "2016-12-25", "2016-12-26"] + [f"2018-07-{d:02d}" for d in range(13, 32)]
check("zero_gen 24일 = 2016-12-22~26, 2018-07-13~31", z == z_given)
nz = [str(x.date()) for x in f.index[f.near_zero_stop == 1]]
nz_a1 = ([str(x.date()) for x in pd.date_range("2015-04-23", "2015-05-05")]
         + ["2016-12-27", "2018-07-04", "2018-07-07", "2018-07-11", "2018-07-12", "2020-09-08"])
check("near_zero_stop 19일 = 분석 A1·A2 의 목록(2015-04-23~05-05, 2016-12-27, 2018-07-04·07·11·12, 2020-09-08)", nz == nz_a1, str(nz) if nz != nz_a1 else "")
print("  near_zero_stop 날의 발전량 범위 %.3f ~ %.3f kWh" % (f.gen_kwh[f.near_zero_stop == 1].min(), f.gen_kwh[f.near_zero_stop == 1].max()))
check("stop_day 43일, 연도별 2015:13 2016:6 2018:23 2020:1 (분석 A3)",
      int(f.stop_day.sum()) == 43 and f.stop_day.groupby(f.index.year).sum()[lambda s: s > 0].astype(int).to_dict() == {2015: 13, 2016: 6, 2018: 23, 2020: 1})
t = f.loc["2026-01-01":]
print("  2026-01~02: 발전량 최소 %.3f kWh (%s), 10kWh 미만인 날 %d일 -> 날씨 없이도 near_zero_stop=0 판정 가능 여부: %s"
      % (t.gen_kwh.min(), t.gen_kwh.idxmin().date(), int((t.gen_kwh < 10).sum()), (t.gen_kwh >= 10).all()))
print("  업로드 구간 뒤 20%(시험 구간, 2023-05-30 이후)의 stop_day:", int(f.loc["2023-05-30":"2025-12-30"].stop_day.sum()),
      "| pi_outage:", int(f.loc["2023-05-30":"2025-12-30"].pi_outage.sum()))

print("\n-- 다른 분석이 만든 파일과 대조")
a1 = pd.read_csv(os.path.join(ASOS, "a1", "a1_lstm_input.csv"), parse_dates=["date"]).set_index("date")
obs_g = W.gy_gsr_obs.notna()
check("A1 a1_lstm_input.csv: 일사량이 관측된 날의 gsr, kt, ht(27도 경사면) 일치",
      np.abs(a1.gsr[obs_g] - W.gy_gsr[obs_g]).max() < 1e-9 and np.abs(a1.kt[obs_g] - W.gy_kt[obs_g]).max() < 1.01e-4
      and np.abs(a1.ht[obs_g] - W.gy_gsr_tilt27[obs_g]).max() < 1.01e-4,
      "채운 5일의 차이(A1 은 회귀 보정, 여기는 그대로): %s" % np.round((a1.gsr[~obs_g] - W.gy_gsr[~obs_g]).values, 2).tolist())
obs_s = ~W.index.isin(diff_s)
check("A1: 일조 시간이 관측된 날의 ss, sf 일치", np.abs(a1.ss[obs_s] - W.gy_ss[obs_s]).max() < 1e-9 and np.abs(a1.sf[obs_s] - W.gy_sun_frac[obs_s]).max() < 1.01e-4,
      "고친 10일의 차이(A1 은 진주·순천·남해 평균, 여기는 진주): 최대 %.2f 시간" % np.abs(a1.ss[~obs_s] - W.gy_ss[~obs_s]).max())
a3 = pd.read_csv(os.path.join(ASOS, "a3", "a3_daily.csv"), parse_dates=["date"]).set_index("date")
check("A3 a3_daily.csv: gen, 최대 출력, 일조 시간(진주로 메운 값) 4,748일 모두 일치",
      np.abs(a3.gen - W.gen_kwh).max() < 1e-9 and np.abs(a3.pmax_h - W.peak_kw).max() < 1e-9 and np.abs(a3.sun - W.gy_ss).max() < 1e-9)
a2 = pd.read_csv(os.path.join(ASOS, "a2", "a2_daily.csv"), parse_dates=["date"]).set_index("date")
check("A2 a2_daily.csv: 발전 시간 수(nhours) 4,807일 모두 일치", (a2.nhours.reindex(f.index) == f.gen_hours).all())

# A4 의 성능 지표를 A4 자신의 코드로 다시 계산해 비교
spec = importlib.util.spec_from_file_location("a4common", os.path.join(ASOS, "a4", "common.py"))
a4c = importlib.util.module_from_spec(spec); spec.loader.exec_module(a4c)
d4 = a4c.load(); d4 = d4[d4.date <= "2025-12-31"].reset_index(drop=True)
p4 = a4c.build_pi(d4)
p4.index = d4.date
check("A4 build_pi: 기대 발전량 일치(값이 있는 날 %d일, 빈 날 위치 포함)" % p4.e.notna().sum(),
      (p4.e.isna().values == W.pi_expected_kwh.isna().values).all() and np.abs(p4.e - W.pi_expected_kwh).max() < 6e-4,
      "기대값이 빈 날: %s" % [str(x.date()) for x in W.index[W.pi_expected_kwh.isna()]])
check("A4 build_pi: 하루 지표(pi) 일치", np.abs(p4.pi - W.pi_daily).max() < 6e-5)
check("A4 build_pi: 정지 표시(outage) 49일 일치", (p4.outage.values == (W.pi_outage == 1).values).all() and int(W.pi_outage.sum()) == 49)
low = (((p4.e >= 80) & (d4.gen.values < 0.7 * p4.e)) | p4.outage).values
susp = pd.Series(low.astype(float)).rolling(7, min_periods=1).sum().values >= 3
check("A4 둘째 규칙(부분 정지 의심) 구간 일치", (susp == (W.pi_partial_suspect == 1).values).all(), "%d일" % susp.sum())
sp = W.index[W.pi_partial_suspect == 1]
runs = (pd.Series(sp).diff().dt.days != 1).cumsum().values
print("  부분 정지 의심 구간:", [(str(sp[runs == r][0].date()), str(sp[runs == r][-1].date()), int((runs == r).sum())) for r in np.unique(runs)])
p4["valid"] = p4.valid & ~susp
check("pi_valid 일치(A4 07_baseline_policy 와 같은 정의)", (p4.valid.values == (W.pi_valid == 1).values).all(), "유효 %d일" % int(W.pi_valid.sum()))
for n in (21, 30):
    w4 = a4c.pi_window(p4.reset_index(drop=True), n)
    mine = W[f"pi_{n}d"].values
    check(f"pi_{n}d 일치(A4 pi_window, 빈 값 위치 포함)", (np.isnan(w4) == np.isnan(mine)).all() and np.nanmax(np.abs(w4 - mine)) < 6e-5,
          "빈 값 %d일" % np.isnan(mine).sum())
cm = (W.index >= "2016-01-01") & (W.index <= "2018-06-30")
p4b = a4c.build_pi(d4)
print("  참고: 변화 없던 구간(2016-01-01~2018-06-30) 21일 창 표준편차 — A4 원 정의(정지만 제외) %.4f, 이 파일(부분 정지 의심도 제외) %.4f"
      % (np.nanstd(a4c.pi_window(p4b, 21)[cm]), np.nanstd(W.pi_21d[cm])))
seg = [("2013-01-01", "2014-12-31"), ("2015-01-03", "2015-05-15"), ("2016-01-01", "2018-06-30"), ("2018-09-01", "2021-05-17"),
       ("2021-05-18", "2024-03-27"), ("2024-03-28", "2025-12-31")]
print("  구간별 수준(유효일 합계 실제/합계 기대, 0.5~1.5배로 자른 값):")
for s0, s1 in seg:
    x = W.loc[s0:s1]; v = x.pi_valid == 1
    gc = np.clip(x.gen_kwh[v], 0.5 * x.pi_expected_kwh[v], 1.5 * x.pi_expected_kwh[v])
    print(f"    {s0} ~ {s1}: {gc.sum() / x.pi_expected_kwh[v].sum():.3f} (유효 {int(v.sum())}일)")

print("\n-- 참고 열 gy_ss_web(기상청 날씨누리 요소별자료)과 ASOS 일조 시간")
b = W[["gy_ss_web", "gy_ss_obs"]].dropna()
print("  2013~2025 둘 다 있는 %d일 중 같은 날 %d일, 다른 날: %s" % (len(b), int((b.gy_ss_web == b.gy_ss_obs).sum()),
      [(str(i.date()), r.gy_ss_web, r.gy_ss_obs) for i, r in b[b.gy_ss_web != b.gy_ss_obs].iterrows()]))
print("  2026-01~02 의 gy_ss_web: %d일, 범위 %.1f ~ %.1f 시간, 가조시간 넘는 날 %d일" % (t.gy_ss_web.notna().sum(), t.gy_ss_web.min(), t.gy_ss_web.max(), int((t.gy_ss_web > t.gy_ssdur).sum())))
g26 = t[t.gen_kwh > 0]
print("  2026-01~02 발전량과 gy_ss_web 의 같은 날 상관 %.3f (n=%d) | 2023~2025 1~2월 발전량과 ASOS 일조 %.3f"
      % (g26.gen_kwh.corr(g26.gy_ss_web), len(g26), W[(W.index.month <= 2) & (W.index.year >= 2023)].gen_kwh.corr(W[(W.index.month <= 2) & (W.index.year >= 2023)].gy_ss)))

print("\n===== 2. 업로드 파일 =====")
FILES = [("hadong_upload.csv", os.path.join(ASOS, "hadong_upload.csv"), "gy_gsr", -1),
         ("hadong_upload_forecast_proxy.csv", os.path.join(ASOS, "hadong_upload_forecast_proxy.csv"), "gy_gsr", +1),
         ("alt/hadong_upload_sunshine.csv", os.path.join(HERE, "alt", "hadong_upload_sunshine.csv"), "gy_ss", -1),
         ("alt/hadong_upload_forecast_proxy_sunshine.csv", os.path.join(HERE, "alt", "hadong_upload_forecast_proxy_sunshine.csv"), "gy_ss", +1)]
raw_col = {"gy_gsr": gy.sumGsr, "gy_ss": gy.sumSsHr}
up = {}
for name, path, col, k in FILES:
    if not os.path.exists(path):
        continue
    print(f"\n--- {name}  (Volume = {col} 의 {'하루 전(d-1)' if k < 0 else '하루 뒤(d+1)'} 값)")
    rb = open(path, "rb").read()
    u = pd.read_csv(path, dtype=str, keep_default_na=False)
    check("UTF-8, BOM 없음, 열 이름 Date,Close,Volume,Stop", not rb.startswith(b"\xef\xbb\xbf") and list(u.columns) == ["Date", "Close", "Volume", "Stop"])
    ud = pd.to_datetime(u["Date"])
    check("행 수 4,746 (>= 최소 41), 2013-01-02 ~ 2025-12-30", len(u) == 4746 and u.Date.iloc[0] == "2013-01-02" and u.Date.iloc[-1] == "2025-12-30")
    check("날짜가 하루씩 빠짐없이 이어지고 중복 없음", (ud.diff().dropna().dt.days == 1).all() and ud.is_unique)
    check("빈 값 없음, Close·Volume 모두 숫자로 읽힘", (u == "").sum().sum() == 0 and pd.to_numeric(u.Close, errors="coerce").notna().all()
          and pd.to_numeric(u.Volume, errors="coerce").notna().all())
    x = u.copy(); x.index = ud
    x[["Close", "Volume", "Stop"]] = x[["Close", "Volume", "Stop"]].astype(float)
    up[name] = x
    check("Close = full 의 gen_kwh (같은 날)", np.abs(x.Close - f.gen_kwh.reindex(x.index)).max() < 1e-9)
    check("Stop = full 의 stop_day (같은 날)", (x.Stop == f.stop_day.reindex(x.index)).all(), "Stop=1 인 행 %d" % int(x.Stop.sum()))
    tgt = f[col].shift(-k).reindex(x.index)            # k=-1: 하루 전 값, k=+1: 하루 뒤 값
    check(f"Volume[d] = full 의 {col}[d{k:+d}일] (4,746행 모두)", np.abs(x.Volume - tgt).max() < 1e-9)
    other = f[col].shift(k).reindex(x.index)
    print("  반대 방향으로 밀었을 때와 같은 행 수(우연히 같은 값): %d / 4746, 같은 날 값과 같은 행 수: %d"
          % (int((np.abs(x.Volume - other) < 1e-9).sum()), int((np.abs(x.Volume - f[col].reindex(x.index)) < 1e-9).sum())))
    rawc = raw_col[col]
    for d in ("2013-01-02", "2021-05-18", "2025-12-30"):
        d0 = pd.Timestamp(d)
        print(f"  원본 대조 {d}: 광양 원본 {('sumGsr' if col == 'gy_gsr' else 'sumSsHr')} 전날 {rawc.get(d0 - pd.Timedelta(days=1), 'ASOS_2012/없음')}, 당일 {rawc[d0]}, 다음날 {rawc.get(d0 + pd.Timedelta(days=1))}"
              f" | 파일 Volume {x.Volume[d0]} | 원본 총량 {raw_gen[d][2]} / 파일 Close {x.Close[d0]}")
    nzm = x.Close > 0
    c_same = x.Close[nzm].corr(x.Volume[nzm])
    c_prev = x.Close.shift(1)[nzm & (x.Close.shift(1) > 0)].corr(x.Volume[nzm & (x.Close.shift(1) > 0)])
    c_next = x.Close.shift(-1)[nzm & (x.Close.shift(-1) > 0)].corr(x.Volume[nzm & (x.Close.shift(-1) > 0)])
    print("  상관(발전량 0 제외): 같은 행 Close-Volume %.3f | 앞 행 Close-이 행 Volume %.3f | 다음 행 Close-이 행 Volume %.3f" % (c_same, c_prev, c_next))
    if k < 0:
        check("밀림 방향: 이 행의 Volume 은 앞 행(전날) 발전량과 가장 강하게 맞는다(같은 날 관측)", c_prev > 0.8 and c_prev > c_same and c_prev > c_next)
    else:
        check("밀림 방향: 이 행의 Volume 은 다음 행(다음날) 발전량과 가장 강하게 맞는다(대상일 관측 = 미래 정보)", c_next > 0.8 and c_next > c_same and c_next > c_prev)
    print("  값 범위: Close %.3f ~ %.3f, Volume %.2f ~ %.2f | Close==0 인 행 %d, Close<=0 %d, Volume 이 정수가 아닌 행 %d"
          % (x.Close.min(), x.Close.max(), x.Volume.min(), x.Volume.max(), int((x.Close == 0).sum()), int((x.Close <= 0).sum()), int((x.Volume % 1 != 0).sum())))

a_, b_ = up["hadong_upload.csv"], up["hadong_upload_forecast_proxy.csv"]
check("두 업로드 파일은 Date, Close, Stop 이 완전히 같고 Volume 만 다르다", (a_.index == b_.index).all() and (a_.Close == b_.Close).all() and (a_.Stop == b_.Stop).all())
check("proxy 의 Volume[d] = upload 의 Volume[d+2일] (같은 관측값을 이틀 어긋나게 놓은 것)", np.abs(b_.Volume.values[:-2] - a_.Volume.values[2:]).max() < 1e-9)

print("\n-- 실습 코드의 80/20 분할을 이 파일에 적용하면")
n = len(a_) - 20; cut = int(n * 0.8)
print(f"  문제 수 {n}, 학습 {cut}(정답일 {a_.index[20].date()} ~ {a_.index[20 + cut - 1].date()}), 시험 {n - cut}(정답일 {a_.index[20 + cut].date()} ~ {a_.index[-1].date()})")
trn = a_.iloc[:20 + cut]
print("  스케일 범위(전체 행으로 fit): Close %.3f ~ %.3f, Volume(upload) %.2f ~ %.2f, Volume(proxy) %.2f ~ %.2f"
      % (a_.Close.min(), a_.Close.max(), a_.Volume.min(), a_.Volume.max(), b_.Volume.min(), b_.Volume.max()))
print("  스케일 범위(학습 구간 행으로만 fit): Close %.3f ~ %.3f, Volume(upload) %.2f ~ %.2f, Volume(proxy) %.2f ~ %.2f"
      % (trn.Close.min(), trn.Close.max(), trn.Volume.min(), trn.Volume.max(), b_.iloc[:20 + cut].Volume.min(), b_.iloc[:20 + cut].Volume.max()))
samp_stop = sum(a_.Stop.values[i:i + 21].any() for i in range(n))
print("  창(20일)이나 정답일에 Stop=1 이 걸린 문제 수: 전체 %d, 학습 %d, 시험 %d"
      % (samp_stop, sum(a_.Stop.values[i:i + 21].any() for i in range(cut)), sum(a_.Stop.values[i:i + 21].any() for i in range(cut, n))))

print("\n===== 결과:", "모든 점검 통과" if ok_all else "실패한 점검이 있다", "=====")
