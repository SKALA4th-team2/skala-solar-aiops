"""T5 대조 1: 2021-05 변화의 날짜와 크기, 판정 규칙(성능 지표·천장 규칙)을 같은 자료·같은 세는 법으로 다시 계산한다.

자료(읽기만):
  solar/data_15043409.csv            발전 실적 원본(CP949)
  asos/hadong_daily_full.csv         ASOS 묶음의 결합 자료(광양 관측, 기대 발전량 pi_expected_kwh)
  solar/d2/wx_archive_daily.csv      Open-Meteo 과거 날씨(사전 조사 D3 가 맑은 날을 고를 때 쓴 것)
모든 계산은 그날이 지난 뒤의 사후 계산이다(예측 입력이 아니다). 기준(포락선, 기준선)은 판정일 이전 자료로만 만든다.
"""
from pathlib import Path
import numpy as np
import pandas as pd

S = Path(__file__).resolve().parents[2]
pd.set_option("display.width", 250); pd.set_option("display.max_columns", 60); pd.set_option("display.max_rows", 400)

raw = pd.read_csv(S / "solar" / "data_15043409.csv", encoding="cp949")
HOURS = [str(h) for h in range(1, 25)]
g = pd.DataFrame({"date": pd.to_datetime(raw["년월일"]), "gen": raw["총량(kw)"].astype(float).values})
g["peak"] = raw[HOURS].astype(float).values.max(axis=1)
g = g.sort_values("date").set_index("date")
a = pd.read_csv(S / "asos" / "hadong_daily_full.csv", parse_dates=["date"]).set_index("date")
print("[0] 원본 %d일 %s ~ %s | ASOS 결합 자료 gen_kwh 와 원본 총량의 최대 차이 %.6f, peak_kw 와 시간대 최대값의 최대 차이 %.6f" % (
    len(g), g.index.min().date(), g.index.max().date(), float((a.gen_kwh - g.gen).abs().max()), float((a.peak_kw - g.peak).abs().max())))
wx = pd.read_csv(S / "solar" / "d2" / "wx_archive_daily.csv", parse_dates=["date"]).set_index("date")
g["om_sunfrac"] = (wx["sunshine_duration"] / wx["daylight_duration"]).reindex(g.index)
g["e"] = a.pi_expected_kwh.reindex(g.index)
g["gy_sunfrac"] = a.gy_sun_frac.reindex(g.index)
g["gy_gsr"] = a.gy_gsr_obs.reindex(g.index)
g["doy"] = g.index.dayofyear

# ---- 정지 표시 두 가지
D3_OUT = [("2015-04-23", "2015-05-06"), ("2016-12-22", "2016-12-27"), ("2018-07-04", "2018-08-01"), ("2020-09-08", "2020-09-08")]
g["d3_out"] = False
for x, y in D3_OUT:
    g.loc[x:y, "d3_out"] = True


def gate(gen, e):
    """ASOS 2.5절의 정지 관문을 글대로 다시 만든다."""
    outage = (gen <= 0) | ((e >= 30) & (gen < 0.3 * e))
    low = ((e >= 80) & (gen < 0.7 * e)) | outage
    susp = pd.Series(low.astype(float)).rolling(7, min_periods=1).sum().values >= 3
    valid = ~np.isnan(e) & (e > 0) & ~outage & ~susp
    return outage, susp, valid


gen = g.gen.values.copy(); e = g.e.values.copy()
outage, susp, valid = gate(gen, e)
fv = a.pi_valid.reindex(g.index).fillna(0).values.astype(int)
print("[0] 정지 관문 다시 계산: 정지 %d일(파일 %d), 보류 %d일(파일 %d), 판정에 쓰는 날 %d일(파일 %d), 표시가 다른 날 %d일" % (
    outage.sum(), a.pi_outage.sum(), susp.sum(), a.pi_partial_suspect.sum(), valid.sum(), fv.sum(), int((valid.astype(int) != fv).sum())))
print("[0] 사전 조사 D3 정지 %d일, ASOS stop_day %d일, 둘 다 %d일, D3 만 %s" % (
    g.d3_out.sum(), a.stop_day.sum(), int((g.d3_out & (a.stop_day.reindex(g.index) == 1)).sum()),
    [str(d.date()) for d in g.index[g.d3_out & (a.stop_day.reindex(g.index) != 1)]]))


def envelope(df, col, a_, b_, half=10, q=0.90):
    bb = df[(df.index >= a_) & (df.index <= b_) & (~df.d3_out)]
    doy = bb.doy.values; v = bb[col].values; env = np.zeros(367)
    for d in range(1, 367):
        dist = np.abs(doy - d); dist = np.minimum(dist, 366 - dist); k = dist <= half
        if k.sum() < 5:
            k = dist <= 3 * half
        env[d] = np.quantile(v[k], q)
    return env


def r_peak(df, a_, b_, peak=None):
    env = envelope(df, "peak", a_, b_)
    p = df.peak.values if peak is None else peak
    return pd.Series(np.where(df.d3_out.values, np.nan, p / env[df.doy.values]), index=df.index)


def pi_n(gen_, e_, valid_, n):
    gc = np.clip(gen_, 0.5 * e_, 1.5 * e_)
    num = pd.Series(np.where(valid_, gc, 0.0)).rolling(n, min_periods=1).sum().values
    den = pd.Series(np.where(valid_, e_, 0.0)).rolling(n, min_periods=1).sum().values
    k = pd.Series(valid_.astype(float)).rolling(n, min_periods=1).sum().values
    out = np.where(k >= np.ceil(0.7 * n), num / np.where(den > 0, den, np.nan), np.nan)
    return out


def episodes(flag):
    f = flag.values.astype(bool); st = f & ~np.r_[False, f[:-1]]
    return int(st.sum()), int(f.sum())


def runs(flag):
    f = flag.values.astype(bool); idx = flag.index; out = []; i = 0
    while i < len(f):
        if f[i]:
            j = i
            while j + 1 < len(f) and f[j + 1]:
                j += 1
            out.append("%s~%s(%d일)" % (idx[i].date(), idx[j].date(), j - i + 1)); i = j + 1
        else:
            i += 1
    return out


def first(flag, ref, hz=120):
    ref = pd.Timestamp(ref); x = flag.loc[ref: ref + pd.Timedelta(days=hz)]; x = x[x]
    pre = bool(flag.get(ref - pd.Timedelta(days=1), False))
    if not len(x):
        return "%d일 안에 없음%s" % (hz, " (전날 켜짐)" if pre else "")
    return "%s, %d일 뒤%s" % (x.index[0].date(), (x.index[0] - ref).days, " (전날 이미 켜짐)" if pre else "")


# =====================================================================
print("\n[1] 2021-05 변화 앞뒤의 날짜별 값 (r_peak = 시간대 최대값 / 2013~2017 같은 날짜 ±10일 P90, PI = 실제 / 기대)")
g["r13"] = r_peak(g, pd.Timestamp("2013-01-01"), pd.Timestamp("2017-12-31"))
g["pi_d"] = np.where(valid, g.gen / g.e, np.nan)
t = g.loc["2021-05-05":"2021-05-27", ["gen", "peak", "r13", "e", "pi_d", "gy_sunfrac", "om_sunfrac", "gy_gsr"]].round(3)
print(t.to_string())

print("\n[1b] 계단 날짜 훑기: 창 2021-03-01 ~ 2021-07-31, 후보일 c = 이 날부터 새 수준. 두 수준 모형의 잔차제곱합이 가장 작은 날과 그 근처")
win = g.loc["2021-03-01":"2021-07-31"]
series = {
    "날짜별 PI(판정에 쓰는 날 전부)": win.pi_d.dropna(),
    "날짜별 PI(광양 일조율 0.6 이상)": win.pi_d[win.gy_sunfrac >= 0.6].dropna(),
    "r_peak(광양 일조율 0.8 이상)": win.r13[win.gy_sunfrac >= 0.8].dropna(),
    "r_peak(Open-Meteo 일조율 0.85 이상, D3 의 맑은 날)": win.r13[win.om_sunfrac >= 0.85].dropna(),
}
# 주의: '일합계 / 수평면 일사량'은 계절(태양 고도)에 따라 3월에서 7월로 가며 스스로 내려가므로 계절을 빼지 않고는 계단 날짜를 찾는 데 쓰지 않는다.
cands = pd.date_range("2021-04-15", "2021-06-20")
for nm, s in series.items():
    res = []
    for c in cands:
        lo, hi = s[s.index < c], s[s.index >= c]
        if len(lo) < 5 or len(hi) < 5:
            continue
        sse = ((lo - lo.mean()) ** 2).sum() + ((hi - hi.mean()) ** 2).sum()
        res.append((c, sse, lo.mean(), hi.mean()))
    R = pd.DataFrame(res, columns=["c", "sse", "lo", "hi"]).set_index("c")
    best = R.sse.idxmin(); n = len(s)
    thr = R.sse.min() * (1 + 3.84 / (n - 2))        # 근사 95% 범위(F 1, n-2)
    rng = R.index[R.sse <= thr]
    sse0 = ((s - s.mean()) ** 2).sum()
    print("  %-46s n=%3d | 최소 %s (앞 %.3f, 뒤 %.3f, %+.1f%%, 설명률 %.1f%%) | 근사 95%% 범위 %s ~ %s | 05-13 과 05-18 의 잔차제곱합 비(최소 대비) %.3f, %.3f" % (
        nm, n, best.date(), R.lo[best], R.hi[best], (R.hi[best] / R.lo[best] - 1) * 100, (1 - R.sse.min() / sse0) * 100,
        rng.min().date(), rng.max().date(), R.sse["2021-05-13"] / R.sse.min(), R.sse["2021-05-18"] / R.sse.min()))
print("  2021-05-13 ~ 05-19 의 광양 일조율:", {str(d.date())[5:]: round(float(v), 2) for d, v in g.gy_sunfrac.loc["2021-05-13":"2021-05-19"].items()})

print("\n[1c] 낙폭을 두 정의와 두 기준일로 나란히 (앞 구간 대비 뒤 구간)")


def pi_sum(a_, b_):
    m = (g.index >= a_) & (g.index <= b_) & valid
    gc = np.clip(gen[m], 0.5 * e[m], 1.5 * e[m])
    return gc.sum() / e[m].sum(), int(m.sum())


for ref in ("2021-05-13", "2021-05-18"):
    r = pd.Timestamp(ref); rows = []
    for nm, (b0, b1, a0, a1) in {
        "앞 42일 / 뒤 42일": (r - pd.Timedelta(days=42), r - pd.Timedelta(days=1), r, r + pd.Timedelta(days=41)),
        "앞 42일 / 뒤 49일(D3 의 창)": (r - pd.Timedelta(days=42), r - pd.Timedelta(days=1), r, r + pd.Timedelta(days=48)),
        "앞 365일 / 뒤 365일": (r - pd.Timedelta(days=365), r - pd.Timedelta(days=1), r, r + pd.Timedelta(days=364)),
        "한 해 전 같은 날짜 42일 / 뒤 42일": (r - pd.Timedelta(days=365), r - pd.Timedelta(days=365 - 41), r, r + pd.Timedelta(days=41)),
        "한 해 전 같은 날짜 141일 / 뒤 141일(~09-30)": (r - pd.Timedelta(days=365), r - pd.Timedelta(days=365 - 140), r, r + pd.Timedelta(days=140)),
    }.items():
        p0, n0 = pi_sum(b0, b1); p1, n1 = pi_sum(a0, a1)
        q0 = g.r13.loc[b0:b1].quantile(0.9); q1 = g.r13.loc[a0:a1].quantile(0.9)
        t0 = (g.gen.loc[b0:b1][~g.d3_out.loc[b0:b1]]).mean(); t1 = (g.gen.loc[a0:a1][~g.d3_out.loc[a0:a1]]).mean()
        rows.append(dict(구간=nm, PI앞=round(p0, 3), PI뒤=round(p1, 3), PI변화pct=round((p1 / p0 - 1) * 100, 1), r_peak_P90앞=round(q0, 3), r_peak_P90뒤=round(q1, 3),
                         r_peak변화pct=round((q1 / q0 - 1) * 100, 1), 일합계평균앞=round(t0, 1), 일합계평균뒤=round(t1, 1)))
    print("  기준일", ref); print(pd.DataFrame(rows).to_string(index=False))

# =====================================================================
print("\n[2] 천장 규칙(최근 14일 r_peak 최대값 < 한도, 유효일 10일 이상). 포락선 기준 기간별")
EV_DOWN = [("2015-01 하락", "2015-01-03"), ("2021-05 하락(05-13 기준)", "2021-05-13"), ("2021-05 하락(05-18 기준)", "2021-05-18")]
for nm, (ea, eb) in {"2013~2017(D3 의 지수 정의)": ("2013-01-01", "2017-12-31"), "2016~2020": ("2016-01-01", "2020-12-31"), "2018-08-02~2020-12-31": ("2018-08-02", "2020-12-31")}.items():
    r = r_peak(g, pd.Timestamp(ea), pd.Timestamp(eb))
    cnt = r.rolling(14, min_periods=10).count(); mx = r.rolling(14, min_periods=10).max()
    for lim in (0.90, 0.88):
        fl = ((mx < lim) & (cnt >= 10)).fillna(False)
        print("  포락선 %s, 한도 %.2f: 2021-05-13 뒤 첫 경보 %s | 05-18 기준 %s" % (nm, lim, first(fl, "2021-05-13"), first(fl, "2021-05-18")))
        if lim == 0.90:
            for seg, (x, y) in {"N1 2016-01-01~2018-06-30": ("2016-01-01", "2018-06-30"), "2018-08-02~2021-05-12": ("2018-08-02", "2021-05-12"), "2021-05-13~2021-12-31": ("2021-05-13", "2021-12-31")}.items():
                ne, nd = episodes(fl.loc[x:y]); rr = runs(fl.loc[x:y])
                print("      %s: %d회 %d일 %s" % (seg, ne, nd, rr if len(rr) <= 12 else rr[:12] + ["..."]))

# =====================================================================
print("\n[3] 성능 지표(PI) 규칙: 기준선 세 가지 x 창 21·30일 x 연속 1·3일, 한도 7.5%")
BASES = ("고정 1.0", "직전 365일", "1년 전 같은 창")
SEG = {"N1 2016-01-01~2018-06-30": ("2016-01-01", "2018-06-30"), "2018-08-02~2021-05-12": ("2018-08-02", "2021-05-12"),
       "2021-09-01~2023-10-31": ("2021-09-01", "2023-10-31"), "N2 2025-03-01~2025-12-31": ("2025-03-01", "2025-12-31")}
EV = [("2015-01 하락", "2015-01-03", "down"), ("2015-05 회복", "2015-05-16", "up"), ("2021-05 하락(05-13)", "2021-05-13", "down"),
      ("2021-05 하락(05-18)", "2021-05-18", "down"), ("2024 봄 회복", "2024-03-28", "up"), ("2024-07 절반 출력", "2024-07-10", "down")]


def pi_dev(gen_, e_, valid_, n, base):
    p = pi_n(gen_, e_, valid_, n)
    if base == "고정 1.0":
        b = np.ones(len(p))
    elif base == "직전 365일":
        gc = np.clip(gen_, 0.5 * e_, 1.5 * e_)
        num = pd.Series(np.where(valid_, gc, 0.0)).rolling(365, min_periods=200).sum().shift(n).values
        den = pd.Series(np.where(valid_, e_, 0.0)).rolling(365, min_periods=200).sum().shift(n).values
        b = num / den
    else:
        b = pd.Series(p).shift(365).values
    return p, b, p / b - 1


rows = []
for base in BASES:
    for n in (21, 30):
        p, b, dev = pi_dev(gen, e, valid, n, base)
        dv = pd.Series(dev, index=g.index).loc["2015-01-01":"2025-12-31"]
        for K in (1, 3):
            dn = ((dv < -0.075).astype(int).rolling(K).sum() >= K); up = ((dv > 0.075).astype(int).rolling(K).sum() >= K)
            r = dict(기준선=base, N=n, 연속=K)
            for nm, ref, direc in EV:
                r[nm] = first(dn if direc == "down" else up, ref, 120 if "절반" not in nm else 30)
            for nm, (x, y) in SEG.items():
                ne, nd = episodes((dn | up).loc[x:y]); nd_, _ = episodes(dn.loc[x:y]); nu_, _ = episodes(up.loc[x:y])
                r[nm] = "%d회(%d일; 하락 %d, 상승 %d)" % (ne, nd, nd_, nu_)
            rows.append(r)
R3 = pd.DataFrame(rows)
print(R3.T.to_string())
R3.to_csv(Path(__file__).with_name("t5_01_pi_rules.csv"), index=False)
for n in (21, 30):
    p, b, dev = pi_dev(gen, e, valid, n, "직전 365일")
    P = pd.Series(p, index=g.index); B = pd.Series(b, index=g.index); Dv = pd.Series(dev, index=g.index)
    for nm, (x, y) in SEG.items():
        print("  직전 365일 기준선, N=%d, %s: 편차 표준편차 %.3f, 최소 %+.3f, 최대 %+.3f, PI 평균 %.3f" % (n, nm, Dv.loc[x:y].std(), Dv.loc[x:y].min(), Dv.loc[x:y].max(), P.loc[x:y].mean()))

# =====================================================================
print("\n[4] 실습 코드 구조(41행 배치 = 입력 20일 + 대상 21일)로 본 두 묶음의 시연 배치: 대상 21일의 PI, 직전 365일 기준선, 편차, 14일 r_peak 최대")
p21, b21, d21 = pi_dev(gen, e, valid, 21, "직전 365일")
P21 = pd.Series(p21, index=g.index); B21 = pd.Series(b21, index=g.index); D21 = pd.Series(d21, index=g.index)
mx14 = g.r13.rolling(14, min_periods=10).max()
r1620 = r_peak(g, pd.Timestamp("2016-01-01"), pd.Timestamp("2020-12-31")); mx14b = r1620.rolling(14, min_periods=10).max()
BATCH = [("사전 조사 정상 배치", "2021-04-02", "2021-05-12"), ("사전 조사 전환 배치", "2021-04-23", "2021-06-02"), ("사전 조사 드리프트 배치", "2021-05-13", "2021-06-22"),
         ("ASOS 정상 배치", "2021-04-07", "2021-05-17"), ("ASOS 드리프트 배치", "2021-05-18", "2021-06-27"),
         ("절충: 정상 배치(05-12 끝)", "2021-04-02", "2021-05-12"), ("절충: 드리프트 배치(05-19 시작)", "2021-05-19", "2021-06-28")]
rows = []
for nm, x, y in BATCH:
    x_, y_ = pd.Timestamp(x), pd.Timestamp(y)
    assert (y_ - x_).days == 40
    t0 = x_ + pd.Timedelta(days=20)
    rows.append(dict(배치=nm, 행=f"{x}~{y}", 대상21일=f"{t0.date()}~{y}", PI21=round(P21[y_], 4), 파일pi_21d=a.pi_21d.get(y_, np.nan), 기준선365=round(B21[y_], 4), 편차pct=round(D21[y_] * 100, 1),
                     고정기준편차pct=round((P21[y_] - 1) * 100, 1), 대상21일_판정일수=int(valid[(g.index >= t0) & (g.index <= y_)].sum()),
                     r_peak14최대_1317=round(mx14[y_], 3), r_peak14최대_1620=round(mx14b[y_], 3), 대상21일_평균발전=round(g.gen.loc[t0:y_].mean(), 1)))
print(pd.DataFrame(rows).to_string(index=False))
print("  ASOS 보고서가 적은 기준선(0.959, 0.958)과 견줌: 직전 365일 기준선 2021-05-17 %.4f, 2021-06-27 %.4f" % (B21["2021-05-17"], B21["2021-06-27"]))

print("\n[4b] 변화 없던 구간에서 41행 배치 하나(대상 21일)의 PI 편차가 7.5% 를 넘는 비율 (직전 365일 기준선 / 고정 기준선). 배치 끝 날짜를 하루씩 민 모든 배치")
for nm, (x, y) in SEG.items():
    dd = D21.loc[x:y].dropna(); ff = (P21.loc[x:y] - 1).dropna()
    print("  %s: 배치 %d개 | 직전 365일 기준선 |편차|>7.5%% %.1f%% (하락 쪽 %.1f%%), >10%% %.1f%% | 고정 기준선 >7.5%% %.1f%%" % (
        nm, len(dd), (dd.abs() > 0.075).mean() * 100, (dd < -0.075).mean() * 100, (dd.abs() > 0.10).mean() * 100, (ff.abs() > 0.075).mean() * 100))

# =====================================================================
print("\n[5] 일사량 예보가 있는 2025년 구간에 수준을 주입: 성능 지표(관측 날씨)와 천장 규칙의 30일 안 켜짐. 시작일은 2025-03-08 부터 7일 간격, 30일 뒤가 2025-12-31 이내")
starts = [d for d in pd.date_range("2025-03-08", "2026-01-17", freq="7D") if d + pd.Timedelta(days=29) <= pd.Timestamp("2025-12-31")]
print("  시작일 %d개 (%s ~ %s). 광양 관측이 2025-12-31 까지라 사전 조사의 46개보다 적다" % (len(starts), starts[0].date(), starts[-1].date()))
envB = envelope(g, "peak", pd.Timestamp("2023-11-07"), pd.Timestamp("2025-02-28"))
rows = []
for f in (1.0, 0.915, 0.86, 0.80, 0.70):
    acc = {}
    for st in starts:
        i0 = g.index.get_loc(st)
        gg = gen.copy(); gg[i0:] *= f
        pk = g.peak.values.copy(); pk[i0:] *= f
        o2, s2, v2 = gate(gg, e)
        hz = slice(st, st + pd.Timedelta(days=29))
        held = int((~v2[i0:i0 + 30] & ~np.isnan(e[i0:i0 + 30])).sum())
        acc.setdefault("보류·정지로 빠진 날(30일 중) 중앙", []).append(held)
        for n in (21, 30):
            for base in ("직전 365일", "고정(주입 전날의 직전 365일 PI)"):
                if base == "직전 365일":
                    p, b, dev = pi_dev(gg, e, v2, n, "직전 365일")
                else:
                    p = pi_n(gg, e, v2, n)
                    m = v2.copy(); m[i0:] = False; m[:i0 - 365] = False
                    gc0 = np.clip(gg, 0.5 * e, 1.5 * e)
                    dev = p / (gc0[m].sum() / e[m].sum()) - 1
                dv = pd.Series(dev, index=g.index)
                for K in (1, 3):
                    dn = ((dv < -0.075).astype(int).rolling(K).sum() >= K)
                    pre = bool(dn.get(st - pd.Timedelta(days=1), False))
                    x = dn.loc[hz]; x = x[x]
                    key = "PI N=%d %s 연속%d" % (n, base, K)
                    acc.setdefault(key, []).append((np.nan if not len(x) else (x.index[0] - st).days + 1, pre))
        r = pd.Series(np.where(g.d3_out.values, np.nan, pk / envB[g.doy.values]), index=g.index)
        fl = ((r.rolling(14, min_periods=10).max() < 0.90) & (r.rolling(14, min_periods=10).count() >= 10)).fillna(False)
        x = fl.loc[hz]; x = x[x]
        acc.setdefault("천장 14일 0.90", []).append((np.nan if not len(x) else (x.index[0] - st).days + 1, bool(fl.get(st - pd.Timedelta(days=1), False))))
    row = dict(배율=f)
    for k, v in acc.items():
        if k.startswith("보류"):
            row[k] = float(np.median(v)); continue
        dl = np.array([q[0] for q in v], dtype=float); pre = np.array([q[1] for q in v])
        row[k] = "%.0f%% (지연 중앙 %s일, 전날 이미 켜짐 %d개)" % (np.mean(~np.isnan(dl)) * 100, "-" if np.all(np.isnan(dl)) else "%.1f" % np.nanmedian(dl), int(pre.sum()))
    rows.append(row)
R5 = pd.DataFrame(rows)
print(R5.T.to_string())
R5.to_csv(Path(__file__).with_name("t5_01_injection_2025.csv"), index=False)

print("\n[5b] 같은 주입을 변화 없던 구간 N1(2016-02-01 ~ 2018-05-01, 30일 간격 28개, ASOS 08 실험과 같은 시작일)에 적용: PI 직전 365일 기준선")
starts1 = pd.date_range("2016-02-01", "2018-05-01", freq="30D")
rows = []
for f in (1.0, 0.915, 0.86, 0.70):
    acc = {}
    for st in starts1:
        i0 = g.index.get_loc(st); gg = gen.copy(); gg[i0:] *= f
        o2, s2, v2 = gate(gg, e)
        for n in (21, 30):
            p, b, dev = pi_dev(gg, e, v2, n, "직전 365일"); dv = pd.Series(dev, index=g.index)
            for K in (1, 3):
                dn = ((dv < -0.075).astype(int).rolling(K).sum() >= K)
                x = dn.loc[st: st + pd.Timedelta(days=29)]; x = x[x]
                acc.setdefault("PI N=%d 직전 365일 연속%d" % (n, K), []).append(np.nan if not len(x) else (x.index[0] - st).days + 1)
    row = dict(배율=f)
    for k, v in acc.items():
        dl = np.array(v, dtype=float)
        row[k] = "%.0f%% (지연 중앙 %s일)" % (np.mean(~np.isnan(dl)) * 100, "-" if np.all(np.isnan(dl)) else "%.1f" % np.nanmedian(dl))
    rows.append(row)
print(pd.DataFrame(rows).T.to_string())

print("\n[6] 실습 코드의 재학습 표본 수: 41행 -> 창 %d개 -> 학습 %d개, 시험 %d개 (train_test_split 의 int(len * 0.8))" % (41 - 20, int((41 - 20) * 0.8), (41 - 20) - int((41 - 20) * 0.8)))
