"""hd_03_loadrows_check.py — 만든 업로드 파일이 실습 코드에서 그대로 읽히는지 확인한다(실습 코드 파일은 고치지 않는다).

실행(현재 폴더를 임시 폴더로 두고 실행한다. 실습 코드의 upload() 가 '현재 폴더/data/uploads/' 에 쓰기 때문이다):
  mkdir -p upload_sim && cd upload_sim && /Users/psm/workspace/skala-aiops/project/.venv/bin/python -B ../hd_03_loadrows_check.py

확인하는 것
 1) data.features.load_rows 로 읽히는가, build_sequences 가 (N, 20, 2) 를 만드는가
 2) build_sequences 가 만든 창의 칸마다 어느 날의 날씨가 들어가는가(전 표본)
 3) serving_app/routers/data.py 의 upload(), status() 를 그대로 불러 통과하는가
 4) serving_app/schemas.py 의 값 범위 조건에 이 자료가 걸리는가
"""
import asyncio
import csv
import datetime as dt
import os
import sys
import time

sys.dont_write_bytecode = True
PROJECT = "/Users/psm/workspace/skala-aiops/project"
sys.path.insert(0, PROJECT)
HERE = os.path.dirname(os.path.abspath(__file__))
ASOS = os.path.dirname(HERE)
assert os.path.realpath(os.getcwd()) != os.path.realpath(PROJECT), "프로젝트 폴더에서 실행하지 않는다"

import numpy as np
from data.features import SEQ_LEN, HAICScaler, build_sequences, load_rows, train_test_split

ok_all = True


def check(name, cond, detail=""):
    global ok_all
    ok_all &= bool(cond)
    print(("[OK]   " if cond else "[FAIL] ") + name + (" | " + detail if detail else ""))


with open(os.path.join(ASOS, "hadong_daily_full.csv"), encoding="utf-8", newline="") as f:
    full = {r["date"]: r for r in csv.DictReader(f)}


def day(s, k):
    return (dt.date.fromisoformat(s) + dt.timedelta(days=k)).isoformat()


FILES = [("hadong_upload.csv", os.path.join(ASOS, "hadong_upload.csv"), "gy_gsr", -1),
         ("hadong_upload_forecast_proxy.csv", os.path.join(ASOS, "hadong_upload_forecast_proxy.csv"), "gy_gsr", +1),
         ("alt/hadong_upload_sunshine.csv", os.path.join(HERE, "alt", "hadong_upload_sunshine.csv"), "gy_ss", -1),
         ("alt/hadong_upload_forecast_proxy_sunshine.csv", os.path.join(HERE, "alt", "hadong_upload_forecast_proxy_sunshine.csv"), "gy_ss", +1)]

print("===== 1·2. load_rows / build_sequences =====")
loaded = {}
for name, path, col, k in FILES:
    if not os.path.exists(path):
        continue
    print(f"\n--- {name}")
    rows = load_rows(path)
    loaded[name] = rows
    check("load_rows 로 읽힘", len(rows) == 4746 and set(rows[0]) == {"Date", "Close", "Volume"},
          f"{len(rows)}행, 첫 행 {rows[0]}, 끝 행 {rows[-1]}")
    check("Close·Volume 이 모두 유한한 float", all(isinstance(r["Close"], float) and isinstance(r["Volume"], float)
                                              and np.isfinite(r["Close"]) and np.isfinite(r["Volume"]) for r in rows))
    scaler = HAICScaler().fit(rows)
    X, y = build_sequences(rows, scaler)
    Xa = np.array(X, dtype="float64")
    check("build_sequences: X (4726, 20, 2), y 4726개, 값은 0~1", Xa.shape == (len(rows) - SEQ_LEN, SEQ_LEN, 2) and len(y) == len(rows) - SEQ_LEN
          and Xa.min() >= 0 and Xa.max() <= 1 and not np.isnan(Xa).any(), f"X {Xa.shape}, 범위 {Xa.min():.3f}~{Xa.max():.3f}")
    Xtr, ytr, Xte, yte = train_test_split(X, y)
    print(f"  train_test_split: 학습 {len(Xtr)} / 시험 {len(Xte)} | 스케일러 close {scaler.close_min}~{scaler.close_max}, volume {scaler.volume_min}~{scaler.volume_max}")
    # 창의 칸마다 실제로 어느 날의 값이 들어 있는지: 스케일을 되돌려 full 파일의 날짜별 값과 맞춘다(전 표본, 전 칸)
    dates = [r["Date"] for r in rows]
    bad_w = bad_g = bad_y = 0
    for i in range(len(X)):
        T = dates[i + SEQ_LEN]                                   # 정답일
        if abs(y[i] - float(full[T]["gen_kwh"])) > 1e-9:
            bad_y += 1
        for j in range(SEQ_LEN):
            d = dates[i + j]                                     # 창의 j 번째 칸의 날짜 = T-20+j
            g = Xa[i, j, 0] * (scaler.close_max - scaler.close_min) + scaler.close_min
            v = Xa[i, j, 1] * (scaler.volume_max - scaler.volume_min) + scaler.volume_min
            if abs(g - float(full[d]["gen_kwh"])) > 1e-6:
                bad_g += 1
            if abs(v - float(full[day(d, k)][col])) > 1e-6:
                bad_w += 1
    last = "T-2" if k < 0 else "T (정답일)"
    check(f"전 표본 {len(X)}개 x 20칸: 발전량 칸은 T-20..T-1, 날씨 칸은 그 날짜의 {k:+d}일 값 -> 창의 마지막 날씨는 {last}",
          bad_w == 0 and bad_g == 0 and bad_y == 0, f"어긋난 칸: 발전량 {bad_g}, 날씨 {bad_w}, 정답 {bad_y}")
    i = dates.index("2021-05-18") - SEQ_LEN
    T = dates[i + SEQ_LEN]
    v_last = Xa[i, -1, 1] * (scaler.volume_max - scaler.volume_min) + scaler.volume_min
    g_last = Xa[i, -1, 0] * (scaler.close_max - scaler.close_min) + scaler.close_min
    print(f"  예: 정답일 T={T} (정답 {y[i]}), 창 {dates[i]} ~ {dates[i + SEQ_LEN - 1]}, 창 마지막 칸 발전량 {g_last:.3f} (= {dates[i + SEQ_LEN - 1]} 발전량 {full[dates[i + SEQ_LEN - 1]]['gen_kwh']}),"
          f" 마지막 칸 날씨 {v_last:.2f} | full 의 {col}: T-2={full[day(T, -2)][col]}, T-1={full[day(T, -1)][col]}, T={full[T][col]}")

print("\n===== 3. serving_app/routers/data.py 의 upload(), status() =====")
from fastapi import HTTPException
from serving_app.routers import data as data_router

print("REQUIRED_COLUMNS", sorted(data_router.REQUIRED_COLUMNS), "| MIN_ROWS", data_router.MIN_ROWS, "| 업로드 위치(현재 폴더 기준)", os.path.abspath(data_router.UPLOAD_DIR))


class FakeUpload:
    def __init__(self, raw):
        self._raw = raw

    async def read(self):
        return self._raw


for name, path, col, k in FILES[:2]:
    raw = open(path, "rb").read()
    res = asyncio.run(data_router.upload(file=FakeUpload(raw)))
    stat = data_router.status()
    check(f"{name}: upload() 통과, status() 가 읽음", res["rows"] == 4746 and stat["exists"] and stat["rows"] == 4746
          and stat["start_date"] == "2013-01-02" and stat["end_date"] == "2025-12-30", f"upload -> {res} | status -> {stat}")
    saved = open(os.path.join(data_router.UPLOAD_DIR, res["filename"]), "rb").read()
    check("  저장된 사본이 원본과 바이트 단위로 같음", saved == raw)
    time.sleep(1.1)                                             # 저장 이름이 초 단위 시각이라 겹치지 않게 한다
try:
    asyncio.run(data_router.upload(file=FakeUpload(open(os.path.join(ASOS, "hadong_daily_full.csv"), "rb").read())))
    check("hadong_daily_full.csv 는 업로드 형식이 아니므로 거절돼야 함", False)
except HTTPException as e:
    check("hadong_daily_full.csv 는 업로드 형식이 아니라서 거절됨(그대로 올리면 안 됨)", e.status_code == 400, f"{e.status_code} {e.detail}")

print("\n===== 4. serving_app/schemas.py 의 값 범위 조건 =====")
from pydantic import ValidationError
from serving_app.schemas import BatchTestRequest, DailyPoint, PredictRequest

rows = loaded["hadong_upload.csv"]
for kw in ({"close": 234.084, "volume": 9.04}, {"close": 234.084, "volume": 9}, {"close": 0.0, "volume": 9}):
    try:
        DailyPoint(**kw)
        print(f"  DailyPoint({kw}) -> 통과")
    except ValidationError as e:
        print(f"  DailyPoint({kw}) -> 거절: {e.errors()[0]['loc']} {e.errors()[0]['msg']}")
n_win = len(rows) - SEQ_LEN + 1
rej_int = rej_zero = passed = 0
for i in range(n_win):
    w = rows[i:i + SEQ_LEN]
    try:
        PredictRequest(sequence=[{"close": r["Close"], "volume": r["Volume"]} for r in w])
        passed += 1
    except ValidationError as e:
        locs = {(x["loc"][-1], x["type"]) for x in e.errors()}
        rej_int += any(t.startswith("int") for _, t in locs)
        rej_zero += any(l == "close" for l, _ in locs)
print(f"  hadong_upload.csv 의 연속 20행 창 {n_win}개를 지금의 PredictRequest 에 넣으면: 통과 {passed}, volume 이 정수가 아니라 거절 {rej_int}, close 가 0 이라 거절 {rej_zero}")
check("지금 스키마로는 한 건도 통과하지 못함(스키마를 고쳐야 한다는 근거)", passed == 0)
zero_win = sum(any(r["Close"] <= 0 for r in rows[i:i + SEQ_LEN]) for i in range(n_win))
print(f"  volume 을 float 로만 바꾸면: close gt=0 조건에 걸리는 창 {zero_win}개(발전량 0 인 날이 든 창)")
BatchTestRequest(prices=[r["Close"] for r in rows[-41:]])
print("  BatchTestRequest(prices=마지막 41행의 Close) -> 통과 (다만 날씨 값을 받는 칸이 없다)")
scaler = HAICScaler().fit(rows)
print("  routers/predict.py 의 SIMULATED_VOLUME=1,200,000 을 이 자료의 스케일러에 넣으면 volume 칸이",
      round(scaler.transform_point(165.0, 1_200_000)[1], 1), "(학습 때 범위는 0~1)")
v = sorted(r["Volume"] for r in rows)
print(f"  Volume 중앙값 {v[len(v) // 2]}, Close 중앙값 {sorted(r['Close'] for r in rows)[len(rows) // 2]}")

print("\n===== 결과:", "모든 점검 통과" if ok_all else "실패한 점검이 있다", "=====")
