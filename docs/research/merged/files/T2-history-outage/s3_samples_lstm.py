"""s3: (1) 정지일 목록마다 실습 코드의 표본(최근 20행 + 다음 날 정답)이 몇 개 걸리는가.
       (2) ASOS 묶음이 남긴 실습 LSTM 예측 파일(시험 구간 946일, 씨앗 42·43·44)로, 설비 이벤트일을 넣고 뺄 때 시험 RMSE 가 얼마나 달라지는가.
표본 정의는 project/data/features.py 를 읽어 옮겨 적었다(SEQ_LEN=20, 정답은 그다음 행, 앞 80% 학습 / 뒤 20% 시험). 실습 모듈은 import 하지 않는다.
예측 파일은 읽기만 한다. proxy(상한) 파일은 정답일과 그 전날의 실제 관측 일사량을 입력에 쓴 값이라 예측 시점에는 받을 수 없는 값을 쓴 수치다.
"""
import numpy as np, pandas as pd
from t2_common import *
pd.set_option("display.width", 250)
SEQ = 20
up = pd.read_csv(ASOS / "hadong_upload.csv", parse_dates=["Date"])
n = len(up) - SEQ; split = int(n * 0.8)
tgt = up.Date.values[SEQ:]
print(f"업로드 파일 {len(up)}행 {up.Date.min().date()}~{up.Date.max().date()} | 표본 {n} | 학습 {split} (정답일 {pd.Timestamp(tgt[0]).date()}~{pd.Timestamp(tgt[split-1]).date()}) | 시험 {n-split} ({pd.Timestamp(tgt[split]).date()}~{pd.Timestamp(tgt[-1]).date()})")
cal = pd.read_csv(SOLAR / "ev" / "day_table_all.csv", encoding="utf-8-sig", parse_dates=["날짜"]).set_index("날짜")
cat = cal["범주"].fillna("").str.split("_").str[0]
a = load_asos()
L = {
    "정확히 0 (24일)": cal.index[cal["일합계"] == 0],
    "1 미만 (39일)": cal.index[cal["일합계"] < 1],
    "D1 정지 = 보완3 A (40일)": cal.index[cat == "A"],
    "ASOS stop_day (43일)": a.index[a.stop_day == 1],
    "D2 정지 (45일)": cal.index[cal["정의_D2"] == 1],
    "ASOS pi_outage (49일)": a.index[a.pi_outage.fillna(0) == 1],
    "D3 정지 (50일)": cal.index[cal["정의_D3"] == 1],
    "보완3 A+B (50일)": cal.index[cat.isin(["A", "B"])],
    "D1 따로 다룰 날 (63일)": cal.index[cal["정의_D1"] == 1],
    "보완3 A+B+C+C2 (65일)": cal.index[cat.isin(["A", "B", "C", "C2"])],
    "보완3 C+C2 만 (15일)": cal.index[cat.isin(["C", "C2"])],
}
assert (up.Stop == 1).sum() == 43 and set(up.Date[up.Stop == 1]) == set(L["ASOS stop_day (43일)"])
rows = []
for k, ds in L.items():
    flag = up.Date.isin(ds).to_numpy()
    win = np.lib.stride_tricks.sliding_window_view(flag, SEQ)[:n].any(axis=1)
    t = flag[SEQ:]
    either = win | t
    rows.append(dict(목록=k, 파일안_일수=int(flag.sum()), 정답일이_걸림=int(t.sum()), 창에_걸림=int(win.sum()), 어느쪽이든=int(either.sum()), 학습구간=int(either[:split].sum()), 시험구간=int(either[split:].sum()),
                     학습표본대비=f"{100*either[:split].sum()/split:.1f}%", 시험표본대비=f"{100*either[split:].sum()/(n-split):.1f}%"))
print("\n== 1. 목록별로 걸리는 표본 수(업로드 파일 기준)")
t1 = pd.DataFrame(rows); print(t1.to_string(index=False)); t1.to_csv(HERE / "s3_sample_counts.csv", index=False, encoding="utf-8-sig")

# 재학습 41행에 이벤트일이 몇 개 들어가는가
flagC = up.Date.isin(L["보완3 A+B+C+C2 (65일)"]).to_numpy()
r41 = pd.Series(flagC).rolling(41).sum()
print("\n== 2. 최근 41행(재학습에 쓰는 행) 안에 설비 이벤트일(A+B+C+C2)이 든 날: ", int((r41 > 0).sum()), "일 | 최대", int(r41.max()), "행 (", up.Date[r41.idxmax()].date(), "끝 창 )")
t = up.Date[(r41 > 0) & (up.Date >= "2023-05-30")]
print("   시험 구간에서 41행에 이벤트일이 든 기간:", fmt(t), "| 그 가운데 5행 이상:", fmt(up.Date[(r41 >= 5) & (up.Date >= '2023-05-30')]))

print("\n== 3. 실습 LSTM 예측 파일(ASOS 묶음, 씨앗 42·43·44)로 본 시험 구간 RMSE")
ev16 = L["보완3 A+B+C+C2 (65일)"]; ev16 = ev16[ev16 >= "2023-05-30"]
print("   시험 구간의 설비 이벤트일:", len(ev16), "일:", fmt(ev16))
res = []
for tag, nm in [("lag_gsr", "현실 조건(전날까지의 광양 일사량)"), ("proxy_gsr", "상한(정답일 실제 일사량 사용. 예측 시점에는 받을 수 없음)")]:
    p = pd.read_csv(ASOS / "hadong_build" / "train_check" / f"{tag}_pred.csv", parse_dates=["date"]).set_index("date")
    isev = p.index.isin(ev16)
    flag = up.set_index("Date").index.isin(ev16)
    fs = pd.Series(flag, index=up.Date)
    winev = fs.rolling(SEQ).sum().shift(1).reindex(p.index).fillna(0) > 0      # 직전 20행에 이벤트일이 든 표본
    aft7 = (fs.rolling(7).sum().shift(1).reindex(p.index).fillna(0) > 0) & ~isev
    for s in (42, 43, 44):
        err = p[f"pred_s{s}"] - p.actual
        rm = lambda m: float(np.sqrt((err[m] ** 2).mean()))
        allm = np.ones(len(p), bool)
        e2 = err ** 2
        r21 = np.sqrt(e2.rolling(21).mean())
        e2x = e2.where(~isev); r21x = np.sqrt(e2x.rolling(21, min_periods=15).mean())
        res.append(dict(파일=nm, 씨앗=s, 전체=rm(allm), 이벤트16일_정답_제외=rm(~isev), 창이나_정답에_닿는_표본_제외=rm(~isev & ~winev.values),
                        이벤트일_평균오차=float(err[isev].mean()), 이벤트뒤7일_평균오차=float(err[aft7.values].mean()), 이벤트뒤7일_RMSE=rm(aft7.values),
                        제곱오차_몫=float(e2[isev].sum() / e2.sum() * 100), 창21_최대=float(r21.max()), 창21_최대_끝날짜=str(r21.idxmax().date()),
                        창21_최대_16일제외=float(r21x.max()), 창21_최대_끝날짜_16일제외=str(r21x.idxmax().date()),
                        n전체=len(p), n제외후=int((~isev & ~winev.values).sum())))
t3 = pd.DataFrame(res); pd.set_option("display.float_format", lambda v: f"{v:.2f}")
print(t3.to_string(index=False)); t3.to_csv(HERE / "s3_lstm_event_effect.csv", index=False, encoding="utf-8-sig")
g = t3.groupby("파일")[["전체", "이벤트16일_정답_제외", "창이나_정답에_닿는_표본_제외", "이벤트일_평균오차", "이벤트뒤7일_평균오차", "제곱오차_몫", "창21_최대", "창21_최대_16일제외"]].mean()
print("\n   씨앗 3개 평균:"); print(g.to_string())
print("   전체 대비 변화(%): 16일 제외", ((g["이벤트16일_정답_제외"] / g["전체"] - 1) * 100).round(2).to_dict(), "| 닿는 표본 제외", ((g["창이나_정답에_닿는_표본_제외"] / g["전체"] - 1) * 100).round(2).to_dict())

# 2024-07 사건 주변: 날짜별 실제와 예측(씨앗 평균)
print("\n== 4. 2024-07-08~07-27 날짜별 실제와 실습 LSTM 예측(씨앗 3개 평균)")
o = pd.DataFrame(index=pd.date_range("2024-07-08", "2024-07-27"))
for tag in ("lag_gsr", "proxy_gsr"):
    p = pd.read_csv(ASOS / "hadong_build" / "train_check" / f"{tag}_pred.csv", parse_dates=["date"]).set_index("date")
    o["실제"] = p.actual.reindex(o.index); o[tag] = p[["pred_s42", "pred_s43", "pred_s44"]].mean(axis=1).reindex(o.index).round(1)
o["범주"] = cat.reindex(o.index).replace("", "-")
print(o.to_string())
print("\n== 5. 2025-03-31(하루짜리 절반 출력, 맑은 날) 앞뒤")
o = pd.DataFrame(index=pd.date_range("2025-03-28", "2025-04-04"))
for tag in ("lag_gsr", "proxy_gsr"):
    p = pd.read_csv(ASOS / "hadong_build" / "train_check" / f"{tag}_pred.csv", parse_dates=["date"]).set_index("date")
    o["실제"] = p.actual.reindex(o.index); o[tag] = p[["pred_s42", "pred_s43", "pred_s44"]].mean(axis=1).reindex(o.index).round(1)
o["기대(광양)"] = a.pi_expected_kwh.reindex(o.index).round(0); o["범주"] = cat.reindex(o.index).replace("", "-")
print(o.to_string())
