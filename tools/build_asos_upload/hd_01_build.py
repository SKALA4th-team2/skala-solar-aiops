"""hd_01_build.py — 하동하수처리장 태양광 결합 데이터를 원자료에서 직접 만든다.

실행
  /Users/psm/workspace/skala-aiops/mlflow/.venv/bin/python hd_01_build.py            # 기본(Volume = 광양 일사량)
  /Users/psm/workspace/skala-aiops/mlflow/.venv/bin/python hd_01_build.py --alt      # 보조(Volume = 광양 일조 시간)도 alt/ 에 만든다

만드는 파일(모두 UTF-8, BOM 없음)
  ../hadong_daily_full.csv                 날짜별 한 줄(2013-01-01 ~ 2026-02-28)
  ../hadong_upload.csv                     실습 업로드 형식. Volume = 하루 전(d-1) 광양 일사량  -> 현실에서 쓸 수 있는 조건
  ../hadong_upload_forecast_proxy.csv      실습 업로드 형식. Volume = 하루 뒤(d+1) 광양 일사량  -> 예보가 완벽하다고 가정한 상한
  alt/hadong_upload_sunshine.csv, alt/hadong_upload_forecast_proxy_sunshine.csv   (--alt) 같은 배치, Volume = 일조 시간

원자료(읽기만 한다)
  발전 실적  ../../solar/data_15043409.csv (CP949)
  ASOS 일자료 /Users/psm/Downloads/연도별 통합 DATA/ASOS_2013.csv ~ ASOS_2025.csv (UTF-8 BOM)
  보조       ../../solar/kma3_266_35.json  (이전 단계가 기상청 날씨누리 '요소별자료'에서 받아 둔 광양 일조 시간. 참고 열 한 개에만 쓴다)

분석 결과에서 가져온 정의(값을 새로 정하지 않았다)
  A1: 관측소 광양시(266). 일사량이 빠진 날은 진주(192) 값, 진주가 고장 구간(2016-01-07 ~ 2018-04-05)이면 의령군(263) 값.
      일조 시간이 가조시간을 넘는 값은 지운다. 위도 34.94도(가조시간에 맞춘 추정), 정남 27도 경사면 환산.
      일부 시간만 합산된 것으로 보이는 광양 일사량 3일은 값을 바꾸지 않고 표시만 한다.
  A2: 사실상 멈춘 날 = 0 은 아닌데 (합계 < 1kWh) 또는 (합계 < 10kWh 이고 광양·진주 평균 일사량 >= 8MJ/m2).
  A3: 일조 시간이 빠진 날은 진주 값.
  A4: 성능 지표 = 실제 / 기대. 기대식은 광양 같은 날 일사량 + 일조 시간 + 계절 조화항 + 최고기온 선형식(2013~2014 적합, 고정).
      정지 규칙(기대 >= 30kWh 인데 실제 < 기대의 30%), 부분 정지 의심(기대 >= 80kWh 인 날 중 70% 미만이 7일에 3일 이상).
"""
import argparse
import json
import os

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.dirname(HERE)                       # .../scratchpad/asos
SOLAR = os.path.join(OUT_DIR, "..", "solar", "data_15043409.csv")
WEB_SS = os.path.join(OUT_DIR, "..", "solar", "kma3_266_35.json")
ASOS_DIR = "/Users/psm/Downloads/연도별 통합 DATA"

GY, JJ, UR = 266, 192, 263                            # 광양시, 진주, 의령군
LAT_GY, TILT = 34.94, 27                              # A1: a1_lat.json, a1_beta.json
WX_START, WX_END = "2013-01-01", "2025-12-31"         # 광양 ASOS 가 있는 구간
JJ_BAD = ("2016-01-07", "2018-04-05")                 # A1: 진주 일사량이 낮게 기록된 구간
GSR_SUSPECT = ["2013-07-10", "2017-07-18", "2022-12-23"]   # A1 검토: 광양 일사량이 낮게 기록된 것으로 보이는 날
PI_FIT = ("2013-01-01", "2014-12-31")                 # A4: 기대식 적합 구간
ZERO_24 = (["2016-12-22", "2016-12-23", "2016-12-24", "2016-12-25", "2016-12-26"]
           + [f"2018-07-{d:02d}" for d in range(13, 32)])
UP_START, UP_END = "2013-01-02", "2025-12-30"         # 업로드 파일 구간(하루 전·하루 뒤 값이 모두 실제 관측인 날)


# ---------- 태양 기하 (a1_common.py 와 같은 식) ----------
def solar_geom(dates, lat_deg):
    doy = pd.DatetimeIndex(dates).dayofyear.values.astype(float)
    phi = np.radians(lat_deg)
    dr = 1 + 0.033 * np.cos(2 * np.pi * doy / 365.0)
    delta = 0.409 * np.sin(2 * np.pi * doy / 365.0 - 1.39)
    ws = np.arccos(np.clip(-np.tan(phi) * np.tan(delta), -1, 1))
    H0 = (24 * 60 / np.pi) * 0.0820 * dr * (ws * np.sin(phi) * np.sin(delta) + np.cos(phi) * np.cos(delta) * np.sin(ws))
    return H0, delta, ws


def daylen_refr(dates, lat_deg, h0_deg=-0.8333):
    doy = pd.DatetimeIndex(dates).dayofyear.values.astype(float)
    g = 2 * np.pi * (doy - 1) / 365.0
    dec = (0.006918 - 0.399912 * np.cos(g) + 0.070257 * np.sin(g) - 0.006758 * np.cos(2 * g)
           + 0.000907 * np.sin(2 * g) - 0.002697 * np.cos(3 * g) + 0.00148 * np.sin(3 * g))
    phi = np.radians(lat_deg)
    c = (np.sin(np.radians(h0_deg)) - np.sin(phi) * np.sin(dec)) / (np.cos(phi) * np.cos(dec))
    return 24 / np.pi * np.arccos(np.clip(c, -1, 1))


def tilted(H, dates, lat_deg, beta_deg, rho=0.2):
    """수평면 하루 일사량 -> 정남향 경사면 하루 일사량(Erbs 확산 비율, Liu-Jordan 등방성 모형)."""
    H = np.asarray(H, dtype=float)
    H0, delta, ws = solar_geom(dates, lat_deg)
    phi = np.radians(lat_deg)
    KT = np.clip(H / H0, 0.01, 0.85)
    f1 = np.where(KT < 0.715, 1 - 0.2727 * KT + 2.4495 * KT**2 - 11.9514 * KT**3 + 9.3879 * KT**4, 0.143)
    f2 = np.where(KT < 0.722, 1 + 0.2832 * KT - 2.5557 * KT**2 + 0.8448 * KT**3, 0.175)
    fd = np.where(ws <= np.radians(81.4), f1, f2)
    Hd = fd * H
    b = np.radians(beta_deg)
    wsp = np.minimum(ws, np.arccos(np.clip(-np.tan(phi - b) * np.tan(delta), -1, 1)))
    Rb = ((np.cos(phi - b) * np.cos(delta) * np.sin(wsp) + wsp * np.sin(phi - b) * np.sin(delta))
          / (np.cos(phi) * np.cos(delta) * np.sin(ws) + ws * np.sin(phi) * np.sin(delta)))
    return (H - Hd) * Rb + Hd * (1 + np.cos(b)) / 2 + H * rho * (1 - np.cos(b)) / 2


# ---------- 1) 발전 실적 ----------
def load_generation():
    s = pd.read_csv(SOLAR, encoding="cp949")
    hours = [str(h) for h in range(1, 25)]
    g = pd.DataFrame({
        "date": pd.to_datetime(s["년월일"]),
        "gen_kwh": s["총량(kw)"].astype(float),
        "peak_kw": s[hours].max(axis=1),
        "gen_hours": (s[hours] > 0).sum(axis=1).astype(int),
        "_hsum": s[hours].sum(axis=1),
    }).sort_values("date").reset_index(drop=True)
    full = pd.date_range(g["date"].min(), g["date"].max(), freq="D")
    assert len(g) == len(full) and (g["date"].values == full.values).all(), "발전 실적에 빠지거나 겹친 날이 있다"
    assert (g["gen_kwh"] - g["_hsum"]).abs().max() < 1e-6, "총량과 시간대별 합이 다르다"
    assert (s["호기"] == 1).all()
    return g.drop(columns="_hsum").set_index("date")


# ---------- 2) ASOS ----------
def load_asos():
    cols = ["stnId", "tm", "sumGsr", "sumSsHr", "ssDur", "maxTa"]
    frames = []
    for y in range(2013, 2026):
        a = pd.read_csv(os.path.join(ASOS_DIR, f"ASOS_{y}.csv"), encoding="utf-8-sig", usecols=cols, low_memory=False)
        frames.append(a[a["stnId"].isin([GY, JJ, UR])])
    a = pd.concat(frames, ignore_index=True)
    a["tm"] = pd.to_datetime(a["tm"])
    assert not a.duplicated(["stnId", "tm"]).any()
    idx = pd.date_range(WX_START, WX_END)
    out = {}
    for sid in (GY, JJ, UR):
        d = a[a["stnId"] == sid].set_index("tm").sort_index()
        assert len(d) == len(idx), f"{sid}: 날짜 행이 빠져 있다 ({len(d)})"
        out[sid] = d.reindex(idx)
    return out


def build_full():
    g = load_generation()
    wx = load_asos()
    gy, jj, ur = wx[GY], wx[JJ], wx[UR]
    idx = gy.index

    # --- 가조시간: 빠진 날은 낮 길이 식(위도 34.94)으로 계산 ---
    ssdur_calc = pd.Series(np.round(daylen_refr(idx, LAT_GY), 1), index=idx)
    ssdur = gy["ssDur"].fillna(ssdur_calc)

    # --- 일조 시간: 가조시간을 넘는 값은 지우고, 빠진 날은 진주 값 ---
    ss_obs = gy["sumSsHr"]
    ss_bad = ss_obs > ssdur + 0.05
    ss_qc = ss_obs.mask(ss_bad)
    jj_ss = jj["sumSsHr"].mask(jj["sumSsHr"] > jj["ssDur"] + 0.05)
    ss = ss_qc.fillna(jj_ss)
    ss_fill = pd.Series(np.where(ss_qc.notna(), "obs", np.where(jj_ss.notna(), "jinju192", "none")), index=idx)
    assert ss.notna().all()

    # --- 일사량: 빠진 날은 진주 값, 진주가 고장 구간이면 의령군 값 ---
    gsr_obs = gy["sumGsr"]
    jj_ok = jj["sumGsr"].where(~((idx >= JJ_BAD[0]) & (idx <= JJ_BAD[1])))
    gsr = gsr_obs.fillna(jj_ok)
    gsr_fill = pd.Series(np.where(gsr_obs.notna(), "obs", np.where(jj_ok.notna(), "jinju192", "uiryeong263")), index=idx)
    gsr = gsr.fillna(ur["sumGsr"])
    assert gsr.notna().all()

    H0, _, _ = solar_geom(idx, LAT_GY)
    w = pd.DataFrame({
        "gy_gsr_obs": gsr_obs, "gy_gsr": gsr, "gy_gsr_fill": gsr_fill,
        "gy_gsr_suspect": idx.isin(pd.to_datetime(GSR_SUSPECT)).astype(int),
        "gy_ss_obs": ss_obs, "gy_ss": ss, "gy_ss_fill": ss_fill,
        "gy_ssdur": ssdur,
        "gy_sun_frac": ss / ssdur,
        "gy_kt": gsr / H0,
        "gy_gsr_tilt27": tilted(gsr.values, idx, LAT_GY, TILT),
        "gy_max_ta": gy["maxTa"],
    }, index=idx)

    d = g.join(w, how="left")
    d["wx_available"] = d.index.isin(idx).astype(int)
    all_idx = d.index
    # 2026-01 ~ 02 의 가조시간은 날짜와 위도만으로 정해지므로 식으로 채운다(날씨 관측값이 아니다)
    d["gy_ssdur"] = d["gy_ssdur"].fillna(pd.Series(np.round(daylen_refr(all_idx, LAT_GY), 1), index=all_idx))
    d["gy_gsr_fill"] = d["gy_gsr_fill"].fillna("none")
    d["gy_ss_fill"] = d["gy_ss_fill"].fillna("none")

    # --- 참고 열: 기상청 날씨누리 요소별자료(일조 시간). 분석 A1~A4 에는 쓰이지 않았다 ---
    web = pd.Series(json.load(open(WEB_SS)), dtype=float)
    web.index = pd.to_datetime(web.index, errors="coerce")
    web = web[web.index.notna()].sort_index().reindex(all_idx)
    d["gy_ss_web"] = web.mask(web > d["gy_ssdur"] + 0.05)

    # --- 발전 정지 표시 ---
    gen = d["gen_kwh"]
    d["zero_gen"] = (gen == 0).astype(int)
    m2 = (gy["sumGsr"] + jj["sumGsr"]) / 2                                   # A2 와 같은 식(한쪽이 빠지면 NaN)
    near = (gen > 0) & ((gen < 1.0) | ((gen < 10.0) & (m2.reindex(all_idx) >= 8.0)))
    d["near_zero_stop"] = near.astype(int)
    d["stop_day"] = ((d["zero_gen"] == 1) | near).astype(int)

    # --- 성능 지표 (A4 common.py 의 build_pi 와 같은 계산. 관측 그대로의 광양 값만 쓰고 채운 값은 쓰지 않는다) ---
    doy = all_idx.dayofyear.values
    ang = 2 * np.pi * doy / 365.25
    s1, c1, s2, c2 = np.sin(ang), np.cos(ang), np.sin(2 * ang), np.cos(2 * ang)
    gq = d["gy_gsr_obs"].values
    sq = ss_qc.reindex(all_idx).values
    ta = d["gy_max_ta"].values
    X = np.column_stack([gq, gq * s1, gq * c1, gq * s2, gq * c2, sq, sq * s1, sq * c1, sq * s2, sq * c2,
                         s1, c1, s2, c2, ta, gq * ta])
    ok = ~np.isnan(X).any(axis=1)
    fit = ((all_idx >= PI_FIT[0]) & (all_idx <= PI_FIT[1]) & (gen.values > 0)
           & ~all_idx.isin(pd.to_datetime(ZERO_24)))
    model = LinearRegression().fit(X[fit & ok], gen.values[fit & ok])
    e = np.full(len(d), np.nan)
    e[ok] = model.predict(X[ok])
    e = pd.Series(e, index=all_idx)
    outage = (gen <= 0) | ((e >= 30.0) & (gen < 0.3 * e))
    low = (((e >= 80.0) & (gen < 0.7 * e)) | outage)
    in_wx = all_idx <= WX_END
    susp = pd.Series(low[in_wx].astype(float)).rolling(7, min_periods=1).sum().values >= 3   # A4 07_baseline_policy.py
    susp = pd.Series(np.r_[susp, np.zeros((~in_wx).sum(), bool)], index=all_idx)
    valid = e.notna() & (e > 0) & ~outage & ~susp
    gen_c = np.clip(gen, 0.5 * e, 1.5 * e)

    def window(n, min_frac=0.7):
        gg = pd.Series(np.where(valid, gen_c, 0.0)).rolling(n).sum()
        ee = pd.Series(np.where(valid, e, 0.0)).rolling(n).sum()
        cc = pd.Series(valid.values.astype(float)).rolling(n).sum()
        r = gg / ee
        r[cc < np.ceil(min_frac * n)] = np.nan
        return r.values

    d["pi_expected_kwh"] = e
    d["pi_daily"] = gen / e
    d["pi_outage"] = outage.astype("Int64")
    d["pi_partial_suspect"] = susp.astype("Int64")
    d["pi_valid"] = valid.astype(int)
    d["pi_21d"] = window(21)
    d["pi_30d"] = window(30)
    no_wx = d["wx_available"] == 0                    # 2026-01 ~ 02: 날씨가 없어 판정할 수 없는 값은 비운다
    for c in ("pi_outage", "pi_partial_suspect"):
        d.loc[no_wx, c] = pd.NA
    for c in ("pi_21d", "pi_30d"):
        d.loc[no_wx, c] = np.nan
    d.loc[no_wx, "gy_gsr_suspect"] = np.nan
    d["gy_gsr_suspect"] = d["gy_gsr_suspect"].astype("Int64")

    cols = ["gen_kwh", "peak_kw", "gen_hours", "zero_gen", "near_zero_stop", "stop_day", "wx_available",
            "gy_gsr_obs", "gy_gsr", "gy_gsr_fill", "gy_gsr_suspect", "gy_ss_obs", "gy_ss", "gy_ss_fill", "gy_ss_web",
            "gy_ssdur", "gy_sun_frac", "gy_kt", "gy_gsr_tilt27", "gy_max_ta",
            "pi_expected_kwh", "pi_daily", "pi_outage", "pi_partial_suspect", "pi_valid", "pi_21d", "pi_30d"]
    d = d[cols].copy()
    for c, nd in {"gen_kwh": 3, "peak_kw": 3, "gy_sun_frac": 4, "gy_kt": 4, "gy_gsr_tilt27": 4,
                  "pi_expected_kwh": 3, "pi_daily": 4, "pi_21d": 4, "pi_30d": 4}.items():
        d[c] = d[c].round(nd)
    d.index.name = "date"
    return d, model


def write_upload(full, col, shift, path, decimals):
    """Date, Close, Volume, Stop.  Volume[d] = full[col][d + shift일].  shift=-1: 하루 전 값, shift=+1: 하루 뒤 값."""
    v = full[col].shift(-shift)                       # shift(-1) 은 하루 뒤 값을 현재 행으로 당긴다
    out = pd.DataFrame({"Date": full.index.strftime("%Y-%m-%d"), "Close": full["gen_kwh"].values,
                        "Volume": v.round(decimals).values, "Stop": full["stop_day"].values}, index=full.index)
    out = out.loc[UP_START:UP_END]
    assert out.notna().all().all(), "빈 값이 있다"
    assert (pd.to_datetime(out["Date"]).diff().dropna().dt.days == 1).all()
    out.to_csv(path, index=False, encoding="utf-8", lineterminator="\n")
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--alt", action="store_true", help="일조 시간을 Volume 에 넣은 보조 파일도 alt/ 에 만든다")
    args = ap.parse_args()

    full, model = build_full()
    p_full = os.path.join(OUT_DIR, "hadong_daily_full.csv")
    out = full.reset_index()
    out["date"] = out["date"].dt.strftime("%Y-%m-%d")
    out.to_csv(p_full, index=False, encoding="utf-8", lineterminator="\n")
    print("saved", p_full, out.shape)

    a = write_upload(full, "gy_gsr", -1, os.path.join(OUT_DIR, "hadong_upload.csv"), 2)
    b = write_upload(full, "gy_gsr", +1, os.path.join(OUT_DIR, "hadong_upload_forecast_proxy.csv"), 2)
    print("saved hadong_upload.csv", a.shape, a["Date"].iloc[0], a["Date"].iloc[-1])
    print("saved hadong_upload_forecast_proxy.csv", b.shape, b["Date"].iloc[0], b["Date"].iloc[-1])
    if args.alt:
        os.makedirs(os.path.join(HERE, "alt"), exist_ok=True)
        a2 = write_upload(full, "gy_ss", -1, os.path.join(HERE, "alt", "hadong_upload_sunshine.csv"), 1)
        b2 = write_upload(full, "gy_ss", +1, os.path.join(HERE, "alt", "hadong_upload_forecast_proxy_sunshine.csv"), 1)
        print("saved alt/*_sunshine.csv", a2.shape, b2.shape)

    # 기대 발전량 식을 서빙 코드에서 다시 계산할 수 있게 계수를 남긴다(A4 식 그대로, 2013~2014 적합)
    feats = ["gsr", "gsr*s1", "gsr*c1", "gsr*s2", "gsr*c2", "ss", "ss*s1", "ss*c1", "ss*s2", "ss*c2",
             "s1", "c1", "s2", "c2", "max_ta", "gsr*max_ta"]
    with open(os.path.join(HERE, "pi_expected_model.json"), "w", encoding="utf-8") as fh:
        json.dump({"target": "expected daily generation (kWh)",
                   "inputs": {"gsr": "Gwangyang(266) sumGsr MJ/m2, same day", "ss": "Gwangyang sumSsHr hr, same day",
                              "max_ta": "Gwangyang maxTa degC, same day",
                              "s1,c1,s2,c2": "sin(w), cos(w), sin(2w), cos(2w), w = 2*pi*dayofyear/365.25"},
                   "fit_period": list(PI_FIT), "features": feats, "intercept": float(model.intercept_),
                   "coef": [float(c) for c in model.coef_]}, fh, ensure_ascii=False, indent=1)
    print("기대식 절편", round(float(model.intercept_), 4), "계수", np.round(model.coef_, 5).tolist())
    print("정지 표시: zero", int(full.zero_gen.sum()), "near", int(full.near_zero_stop.sum()), "stop", int(full.stop_day.sum()),
          "| pi_outage", int(full.pi_outage.sum()), "pi_partial_suspect", int(full.pi_partial_suspect.sum()))
    print("채운 날: 일사량", full.gy_gsr_fill.value_counts().to_dict(), "일조", full.gy_ss_fill.value_counts().to_dict())
