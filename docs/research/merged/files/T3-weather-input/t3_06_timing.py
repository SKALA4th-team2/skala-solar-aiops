"""t3_06: 예보를 대상일 전날 몇 시에 받을 수 있는가(저장된 응답으로 다시 계산).

(1) Open-Meteo 모델 메타 파일(meta.json)의 실행 시작 시각과 공개 시각 차이.
    어제·오늘 다른 과제가 받아 둔 5건과 이번에 받은 것(api/meta_*.json).
(2) 보완 조사 1 검토자가 받아 둔 JMA MSM 개별 실행분(merged/gap1_review/r06_runs)과 Previous Runs 응답으로
    '24시간 전 예보' 값이 어느 실행분의 값인지 다시 맞춰 본다(검토자 코드를 쓰지 않고 새로 씀).
(3) 같은 방법으로 JMA GSM 구름양.
"""
import glob
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

import t3_common as c

KST = timezone(timedelta(hours=9))
M = c.SCR / "merged"


def ts(x):
    return datetime.fromtimestamp(x, tz=timezone.utc)


print("[1] 메타 파일: 실행 시작(UTC) -> 공개까지 걸린 시간")
files = [c.SOLAR / "gap2" / "api" / "meta_jma_msm.json", M / "gap2" / "api" / "meta_jma_msm_1007.json",
         M / "gap2" / "api" / "meta_jma_msm_1007b.json", M / "gap2_review" / "meta_jma_msm_review.json",
         c.SOLAR / "gap2" / "api" / "meta_jma_gsm.json", M / "gap2" / "api" / "meta_jma_gsm_1007.json"]
files += [Path(p) for p in sorted(glob.glob(str(c.HERE / "api" / "meta_jma_*.json")))]
seen = set()
for f in files:
    j = json.load(open(f))
    init, av = j["last_run_initialisation_time"], j["last_run_availability_time"]
    model = "MSM" if "msm" in f.name else "GSM"
    key = (model, init)
    tag = "" if key not in seen else " (같은 실행분)"
    seen.add(key)
    print(f"  {model} {f.parent.parent.name}/{f.parent.name}/{f.name:28s} 시작 {ts(init):%m-%d %H:%M}Z = {ts(init).astimezone(KST):%m-%d %H:%M} KST"
          f" | 공개 {ts(av):%m-%d %H:%M}Z = {ts(av).astimezone(KST):%m-%d %H:%M} KST | 지연 {(av - init) / 3600:.2f}시간"
          f" | 갱신 간격 {j['update_interval_seconds'] / 3600:.0f}시간{tag}")
log = (c.HERE / "api" / "meta_fetch_log.txt")
if log.exists():
    print("  이번에 받은 시각:", log.read_text().strip().replace("\n", " / "))

print("\n[2] JMA MSM 일사량: 2026-10-06, 10-07 낮(07~18시 KST)의 '24시간 전 예보'가 어느 실행분 값과 같은가")
pv = pd.DataFrame(json.load(open(M / "gap1_review" / "r06_prevruns_now.json"))["hourly"])
pv["time"] = pd.to_datetime(pv["time"])
runs = {}
for f in sorted(glob.glob(str(M / "gap1_review" / "r06_runs" / "msm_*.json"))):
    j = json.load(open(f))
    if "hourly" not in j:
        print("  실행분 없음:", Path(f).name, j.get("reason", ""))
        continue
    init = pd.Timestamp(Path(f).stem.split("_")[1][:13].replace("T", " ") + ":00")   # UTC
    s = pd.Series(j["hourly"]["shortwave_radiation"], index=pd.to_datetime(j["hourly"]["time"])).dropna()
    runs[init] = s
for day in ["2026-10-06", "2026-10-07"]:
    d = pv[(pv["time"] >= f"{day} 07:00") & (pv["time"] <= f"{day} 18:00")]
    cnt, uniq = {}, {}
    for _, r in d.iterrows():
        hit = [k for k, s in runs.items() if r["time"] in s.index and abs(s[r["time"]] - r["shortwave_radiation_previous_day1"]) < 1e-9]
        for k in hit:
            cnt[k] = cnt.get(k, 0) + 1
        if len(hit) == 1:
            uniq[hit[0]] = uniq.get(hit[0], 0) + 1
    print(f"  대상일 {day}: 낮 12칸")
    for k in sorted(cnt):
        kst = k + pd.Timedelta(hours=9)
        print(f"    실행분 {k:%m-%d %H}Z (= {kst:%m-%d %H시} KST): 같은 칸 {cnt[k]:2d}, 그 실행분만 같은 칸 {uniq.get(k, 0):2d}")
    # 규칙: 09시 이후 = 전날 00Z, 07~08시 = 전전날 12Z
    d0 = pd.Timestamp(day)
    rA, rB = d0 - pd.Timedelta(days=1), d0 - pd.Timedelta(days=2) + pd.Timedelta(hours=12)
    ok = 0
    for _, r in d.iterrows():
        k = rA if r["time"].hour >= 9 else rB
        if k in runs and r["time"] in runs[k].index and abs(runs[k][r["time"]] - r["shortwave_radiation_previous_day1"]) < 1e-9:
            ok += 1
    print(f"    규칙 '09시 이후는 전날 00Z(09시 KST) 실행분, 07~08시는 그 전날 12Z(21시 KST) 실행분'이 맞는 칸: {ok} / {len(d)}")
    tot = d["shortwave_radiation_previous_day1"].sum() * 3600 / 1e6
    early = d.loc[d["time"].dt.hour < 9, "shortwave_radiation_previous_day1"].sum() * 3600 / 1e6
    print(f"    낮 합계 {tot:.2f} MJ/m2 가운데 07~08시 몫 {early:.2f} ({early / tot * 100:.1f}%)")

print("\n[3] JMA GSM 구름양: 2026-10-07 낮의 '하루 전 예보'가 어느 실행분 값과 같은가")
pg = pd.DataFrame(json.load(open(M / "gap1_review" / "r06_prevruns_gsm_cloud.json"))["hourly"])
pg["time"] = pd.to_datetime(pg["time"])
gr = {}
for f in sorted(glob.glob(str(M / "gap1_review" / "r06_runs" / "gsm_*.json"))):
    j = json.load(open(f))
    if "hourly" not in j:
        print("  실행분 없음:", Path(f).name, j.get("reason", ""))
        continue
    init = pd.Timestamp(Path(f).stem.split("_")[1][:13].replace("T", " ") + ":00")
    gr[init] = pd.Series(j["hourly"]["cloud_cover"], index=pd.to_datetime(j["hourly"]["time"])).dropna()
d = pg[(pg["time"] >= "2026-10-07 07:00") & (pg["time"] <= "2026-10-07 18:00")]
for _, r in d.iterrows():
    hit = [f"{k:%d일%H}Z" for k, s in gr.items() if r["time"] in s.index and abs(s[r["time"]] - r["cloud_cover_previous_day1"]) < 1e-9]
    lead24 = r["time"] - pd.Timedelta(hours=9) - pd.Timedelta(hours=24)       # 정확히 24시간 전(UTC)
    v24 = gr[lead24][r["time"]] if lead24 in gr and r["time"] in gr[lead24].index else np.nan
    print(f"    {r['time']:%H시} KST 하루 전 예보 {r['cloud_cover_previous_day1']:5.1f} | 같은 실행분: {','.join(hit) or '-':40s} | 정확히 24시간 전에 시작한 실행분의 값: {v24}")
