"""실행 중인 서버에 요청을 보내고, 요청과 응답을 그대로 파일로 남긴다.

기획서 ⑤(API 명세)와 ⑥(동작 증빙)의 근거를 만드는 도구다. 서버 코드는 건드리지 않는다.
요청 본문에 쓰는 값은 저장소의 데이터 파일에서 읽는다.

실행 (저장소 루트에서):
    python tools/proposal/http_checks.py --base http://127.0.0.1:8077 --out docs/proposal/evidence/http --phase pre
    python tools/proposal/http_checks.py ... --phase upload-haic
    python tools/proposal/http_checks.py ... --phase upload-errors
    python tools/proposal/http_checks.py ... --phase upload-hadong
    python tools/proposal/http_checks.py ... --phase post
    python tools/proposal/http_checks.py ... --phase latency
    python tools/proposal/http_checks.py ... --phase upload-gaps
    python tools/proposal/http_checks.py --base http://127.0.0.1:8077 --out docs/proposal/evidence/http_mlflow_lazy --phase mlflow-lazy

phase
    pre            업로드 전: 화면, 문서, 헬스체크, 예측과 배치의 정상·오류 입력, 로그
    upload-haic    project/data/sample_haic_prices.csv 업로드와 상태 조회
    upload-errors  거절되는 업로드 4종
    upload-hadong  datasets/hadong_upload_forecast_jma.csv 업로드와 상태 조회
    post           학습을 돌린 뒤: 헬스체크, 예측, 배치, 로그
    latency        /health 와 422 응답의 소요 시간
    upload-gaps    형식은 맞지만 내용이 잘못된 업로드 5종(날짜 역순, 빠진 날과 중복, 음수, 숫자가 아닌 값, 빈 값)과 그 뒤의 상태 조회
    mlflow-lazy    서버를 MODEL_SOURCE=mlflow (LOADING_MODE 는 기본값 lazy)로 띄운 뒤의 헬스체크와 예측. --out 을 다른 폴더로 준다
"""
import argparse
import csv
import datetime as dt
import io
import json
import statistics
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
FORECAST_CSV = ROOT / "datasets" / "hadong_upload_forecast_jma.csv"
DAILY_FULL_CSV = ROOT / "datasets" / "hadong_daily_full.csv"
RAW_CP949_CSV = ROOT / "datasets" / "raw" / "data_15043409.csv"
HAIC_CSV = ROOT / "project" / "data" / "sample_haic_prices.csv"

p = argparse.ArgumentParser()
p.add_argument("--base", default="http://127.0.0.1:8077")
p.add_argument("--out", type=Path, required=True)
p.add_argument("--phase", required=True)
a = p.parse_args()
a.out.mkdir(parents=True, exist_ok=True)


def forecast_rows():
    with open(FORECAST_CSV, encoding="utf-8") as f:
        return list(csv.DictReader(f))


ROWS = forecast_rows()
LAST20 = ROWS[-20:]          # 2026-02-08 ~ 2026-02-27
LAST41 = ROWS[-41:]          # 2026-01-18 ~ 2026-02-27


def seq(rows, volume=lambda r: int(round(float(r["Volume"]))), close=lambda r: float(r["Close"])):
    return [{"close": close(r), "volume": volume(r)} for r in rows]


def save(name, note, method, path, *, json_body=None, files=None, resp, elapsed_ms, body_note=None):
    ctype = resp.headers.get("content-type", "")
    if "application/json" in ctype:
        try:
            body = resp.json()
        except ValueError:
            body = resp.text
    else:
        text = resp.text
        body = {"length": len(text), "head": text[:300]}
    rec = {
        "case": name,
        "note": note,
        "requested_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "request": {"method": method, "path": path, "json": json_body, "files": files, "body_note": body_note},
        "response": {"status": resp.status_code, "content_type": ctype, "elapsed_ms": round(elapsed_ms, 1), "body": body},
    }
    (a.out / f"{name}.json").write_text(json.dumps(rec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    short = json.dumps(body, ensure_ascii=False)
    print(f"{name:34s} {method:4s} {path:22s} -> {resp.status_code}  {short[:150]}")
    return rec


def call(name, note, method, path, *, json_body=None, data=None, headers=None, files=None, files_note=None, body_note=None):
    t0 = time.perf_counter()
    resp = requests.request(method, a.base + path, json=json_body, data=data, headers=headers, files=files, timeout=120)
    return save(name, note, method, path, json_body=json_body, files=files_note, resp=resp,
                elapsed_ms=(time.perf_counter() - t0) * 1000, body_note=body_note)


def upload(name, note, filename, content: bytes, files_note):
    return call(name, note, "POST", "/data/upload", files={"file": (filename, content, "text/csv")}, files_note=files_note)


def phase_pre():
    call("root_dashboard", "대시보드 화면(정적 파일)", "GET", "/")
    call("docs_swagger", "자동 문서 화면", "GET", "/docs")
    spec = requests.get(a.base + "/openapi.json", timeout=30)
    (a.out.parent / "openapi.json").write_text(json.dumps(spec.json(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("openapi.json 저장:", sorted(spec.json()["paths"].keys()))
    call("health_before", "모델을 불러오기 전의 헬스체크", "GET", "/health")
    call("data_status_empty", "업로드가 없을 때의 상태 조회", "GET", "/data/status")
    call("logs_list_before", "로그 목록", "GET", "/logs")
    call("logs_read_aiops", "aiops.log 내용", "GET", "/logs/aiops.log")
    call("logs_read_missing", "없는 로그 파일", "GET", "/logs/no-such-file.log")
    call("not_found", "없는 경로", "GET", "/no-such-path")
    call("predict_get_not_allowed", "POST 전용 경로를 GET 으로 호출", "GET", "/predict")

    valid = {"sequence": seq(LAST20)}
    call("predict_valid_current_schema", "현행 스키마에 맞는 20개 시퀀스(거래량 자리를 정수로 반올림)", "POST", "/predict", json_body=valid)
    call("predict_19_items", "시퀀스가 19개", "POST", "/predict", json_body={"sequence": seq(LAST20[1:])})
    call("predict_21_items", "시퀀스가 21개", "POST", "/predict", json_body={"sequence": seq(ROWS[-21:])})
    zero = seq(LAST20)
    zero[-1] = {"close": 0.0, "volume": zero[-1]["volume"]}
    call("predict_close_zero", "발전량 0 (태양광에서는 실제로 있는 값)", "POST", "/predict", json_body={"sequence": zero})
    call("predict_volume_float", "두 번째 값이 소수(실제 일사량 예보 값 그대로)", "POST", "/predict",
         json_body={"sequence": seq(LAST20, volume=lambda r: float(r["Volume"]))})
    neg = seq(LAST20)
    neg[0] = {"close": neg[0]["close"], "volume": -1}
    call("predict_volume_negative", "두 번째 값이 음수", "POST", "/predict", json_body={"sequence": neg})
    miss = seq(LAST20)
    miss[0] = {"close": miss[0]["close"]}
    call("predict_field_missing", "volume 필드 누락", "POST", "/predict", json_body={"sequence": miss})
    call("predict_body_not_json", "JSON 이 아닌 본문", "POST", "/predict", data="not json",
         headers={"Content-Type": "application/json"}, body_note="본문 문자열: not json")
    call("predict_empty_object", "sequence 필드 자체가 없음", "POST", "/predict", json_body={})

    prices41 = [float(r["Close"]) for r in LAST41]
    call("batch_41_values", "연속된 발전량 41개", "POST", "/predict/batch-test", json_body={"prices": prices41})
    call("batch_20_values", "값이 20개(최소 21개 미만)", "POST", "/predict/batch-test", json_body={"prices": prices41[:20]})
    call("batch_wrong_type", "숫자가 아닌 값", "POST", "/predict/batch-test", json_body={"prices": ["a"] * 41})


def phase_upload_haic():
    raw = HAIC_CSV.read_bytes()
    upload("upload_haic_sample", "HAIC 예시 파일(스켈레톤에 들어 있던 것)", HAIC_CSV.name, raw, {"file": str(HAIC_CSV.relative_to(ROOT))})
    call("data_status_haic", "HAIC 업로드 뒤 상태", "GET", "/data/status")


def phase_upload_errors():
    upload("upload_cp949", "CP949 로 저장된 원본 발전 실적", RAW_CP949_CSV.name, RAW_CP949_CSV.read_bytes(),
           {"file": str(RAW_CP949_CSV.relative_to(ROOT))})
    upload("upload_missing_columns", "Date·Close·Volume 열이 없는 분석용 파일", DAILY_FULL_CSV.name, DAILY_FULL_CSV.read_bytes(),
           {"file": str(DAILY_FULL_CSV.relative_to(ROOT))})
    text = FORECAST_CSV.read_text(encoding="utf-8").splitlines()
    short = ("\n".join(text[:41]) + "\n").encode("utf-8")          # 머리 1줄 + 40행
    upload("upload_40_rows", "40행(최소 41행 미만)", "hadong_40rows.csv", short,
           {"file": "datasets/hadong_upload_forecast_jma.csv 의 앞 40행"})
    call("upload_no_file", "file 필드 없이 호출", "POST", "/data/upload")


def phase_upload_hadong():
    upload("upload_hadong_forecast", "하루 전 일사량 예보를 넣은 태양광 업로드 파일", FORECAST_CSV.name, FORECAST_CSV.read_bytes(),
           {"file": str(FORECAST_CSV.relative_to(ROOT))})
    call("data_status_hadong", "태양광 업로드 뒤 상태", "GET", "/data/status")


def phase_post():
    call("health_after_training", "학습을 돌린 뒤의 헬스체크", "GET", "/health")
    call("predict_valid_after_training", "학습을 돌린 뒤의 예측 요청", "POST", "/predict", json_body={"sequence": seq(LAST20)})
    call("batch_41_after_training", "학습을 돌린 뒤의 배치 요청", "POST", "/predict/batch-test",
         json_body={"prices": [float(r["Close"]) for r in LAST41]})
    call("logs_list_after", "로그 목록", "GET", "/logs")
    call("logs_read_aiops_after", "aiops.log 내용", "GET", "/logs/aiops.log")


def phase_latency():
    out = {"measured_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"), "base": a.base, "n": 50, "cases": {}}
    body19 = {"sequence": seq(LAST20[1:])}
    for name, fn in (("GET /health", lambda: requests.get(a.base + "/health", timeout=30)),
                     ("POST /predict (19개, 422)", lambda: requests.post(a.base + "/predict", json=body19, timeout=30)),
                     ("GET /data/status", lambda: requests.get(a.base + "/data/status", timeout=30))):
        fn()
        ms = []
        for _ in range(50):
            t0 = time.perf_counter()
            r = fn()
            ms.append((time.perf_counter() - t0) * 1000)
        ms.sort()
        out["cases"][name] = {"status": r.status_code, "median_ms": round(statistics.median(ms), 2), "p95_ms": round(ms[int(0.95 * len(ms)) - 1], 2),
                              "max_ms": round(ms[-1], 2)}
        print(name, out["cases"][name])
    (a.out.parent / "latency_http.json").write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def phase_upload_gaps():
    """업로드 검증이 보지 않는 것: 날짜 순서와 연속성, 값의 범위, 숫자인지, 빈 값인지.

    업로드 파일의 마지막 60행(2025-12-30 ~ 2026-02-27)을 메모리에서만 고쳐 보낸다. datasets/ 의 파일은 바꾸지 않는다.
    """
    head = "Date,Close,Volume"
    base = [[r["Date"], r["Close"], r["Volume"]] for r in ROWS[-60:]]

    def to_csv(rows):
        return (head + "\n" + "\n".join(",".join(r) for r in rows) + "\n").encode("utf-8")

    def variant(name, note, rows):
        upload(f"upload_{name}", note, f"hadong_{name}.csv", to_csv(rows), {"file": f"업로드 파일의 마지막 60행을 고친 것: {note}"})
        call(f"data_status_after_{name}", f"{note} 업로드 뒤의 상태 조회", "GET", "/data/status")
        time.sleep(1.1)        # 저장 이름이 초 단위 시각이라, 같은 초에 올리면 앞 파일을 덮어쓴다

    variant("dates_reversed", "날짜가 최근에서 과거 순서", list(reversed(base)))
    gap = [list(r) for r in base]
    del gap[20:25]                     # 5일을 뺀다
    gap[10][0] = gap[9][0]             # 한 날짜를 두 번 넣는다
    variant("dates_gap_duplicate", "5일이 빠지고 한 날짜가 두 번", gap)
    neg = [list(r) for r in base]
    neg[30][1] = "-10.0"
    neg[31][2] = "-1.0"
    variant("negative_values", "발전량 -10, 일사량 예보 -1 이 한 행씩", neg)
    text = [list(r) for r in base]
    text[30][1] = "abc"
    variant("non_numeric", "발전량 칸 하나가 숫자가 아님(abc)", text)
    empty = [list(r) for r in base]
    empty[30][1] = ""
    variant("empty_value", "발전량 칸 하나가 비어 있음", empty)
    upload("upload_gaps_restore", "점검을 마친 뒤 원래의 태양광 업로드 파일을 다시 올려 최신 파일을 되돌린다", FORECAST_CSV.name,
           FORECAST_CSV.read_bytes(), {"file": str(FORECAST_CSV.relative_to(ROOT))})
    call("data_status_after_restore", "되돌린 뒤의 상태 조회", "GET", "/data/status")


def phase_mlflow_lazy():
    """서버를 MODEL_SOURCE=mlflow 로 띄운 뒤에 부른다. 서버의 환경 변수는 이 스크립트가 알 수 없으므로 note 에 적어 둔다."""
    env = "서버를 MODEL_SOURCE=mlflow, LOADING_MODE 기본값(lazy)으로 띄운 상태"
    call("health", f"{env}의 헬스체크", "GET", "/health")
    call("predict_valid", f"{env}에서 현행 스키마에 맞는 20개 시퀀스", "POST", "/predict", json_body={"sequence": seq(LAST20)})
    call("predict_with_date_and_float", f"{env}에서 ⑤ 9절의 제안 본문(날짜와 소수 예보)을 그대로 보냄", "POST", "/predict",
         json_body={"sequence": [{"date": r["Date"], "close": float(r["Close"]), "volume": float(r["Volume"])} for r in LAST20]})


{"pre": phase_pre, "upload-haic": phase_upload_haic, "upload-errors": phase_upload_errors, "upload-hadong": phase_upload_hadong,
 "post": phase_post, "latency": phase_latency, "upload-gaps": phase_upload_gaps, "mlflow-lazy": phase_mlflow_lazy}[a.phase]()
