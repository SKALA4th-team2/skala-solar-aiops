# 검증 기록

기획서 ①~⑥ 이 "실행해 확인했다"고 적은 내용의 기록이다. 기획서의 `[실행]` 표기와 `V` 번호가 여기를 가리킨다.

## 읽는 법

- **판정**은 세 가지다. **통과**는 기대와 실제가 같다는 뜻이다. **실패**는 다 만든 서비스라면 나와야 할 결과가 나오지 않았다는 뜻이고, 고칠 곳을 함께 적었다. **미실행**은 돌리지 못했다는 뜻이다.
- 실패는 대부분 스켈레톤의 빈칸(`___`)에서 나왔다. 빈칸을 채우지 않고 지금의 코드 그대로 돌렸기 때문이다. 문서를 쓰려고 코드를 고치거나 기준값을 바꾸지 않았다.
- "기대"는 통합가이드가 요구하는 동작이나, 이 기획서가 제안하는 동작이다.

## 공통 환경

| 항목 | 내용 |
| --- | --- |
| 날짜 | 2026-10-07 (한국 시각). 요청과 응답, 레지스트리의 상태, 측정 기록, 로그에는 건마다의 시각이 들어 있다. 자료에서 계산한 결과 파일(`data_checks`, `threshold_sweep`, `static_scan` 등)과 화면에는 시각이 없다. 같은 입력이면 같은 값이 나오는 계산이라 여러 번 다시 돌렸다 |
| 코드 | 커밋 `58d6ff8`. `project/` 에 커밋되지 않은 변경이 없다 |
| 실행한 곳 | 그 커밋의 `project/` 를 임시 폴더에 그대로 복사한 **검증용 사본**. 사본의 `project/` 를 작업 디렉터리로 두고 돌렸다. 저장소 안에 모델 파일, MLflow 기록, 업로드 파일을 남기지 않으려는 것이다 |
| 파이썬 | 저장소에 `project/.venv` 가 아직 없다. 서빙과 학습에는 개인 실습 폴더의 가상환경을 썼다. Python 3.11.15 이고, `project/requirements.txt` 의 여덟 패키지가 모두 같은 버전이다. 자료 점검과 그림에는 pandas 2.3.3, numpy 2.1.3, matplotlib 3.11.2 가 든 다른 가상환경을 썼다 |
| 기계 | macOS 26.5.2, arm64. Docker 29.6.2 |
| 서버 | `uvicorn serving_app.main:app --host 127.0.0.1 --port 8077`. 따로 적지 않으면 `MODEL_SOURCE` 와 `LOADING_MODE` 는 기본값(`local`, `lazy`)이다 |
| 도구 | [`tools/proposal/`](../../../tools/proposal/). 쓰는 법은 [`README.md`](../../../tools/proposal/README.md)에 있다 |
| 증빙의 정리 | 로그에서 개인 PC 의 경로를 짧은 표기로 바꾸고 프레임워크 내부 호출을 접었다. 결과와 오류 문장은 그대로다. 규칙은 [`sanitize_logs.py`](../../../tools/proposal/sanitize_logs.py)에 있다 |

기록: [`environment.txt`](environment.txt)

## 한눈에

| 번호 | 무엇을 확인했는가 | 판정 |
| --- | --- | --- |
| [V01](#v01) | 저장소의 상태와 실행 환경 | 통과 |
| [V02](#v02) | 코드에 남은 빈칸, 정책 상수, 주가 표현, 모델을 바꾸는 코드 | 통과 |
| [V03](#v03) | 서버가 뜨고 엔드포인트 목록이 코드와 같다 | 통과 |
| [V04](#v04) | 정상 입력의 예측 | **실패** |
| [V05](#v05) | 틀린 예측 요청을 422 로 거절한다 | 통과 |
| [V06](#v06) | 배치 예측 | 422 는 통과, 정상 입력은 **실패** |
| [V07](#v07) | 업로드와 상태 조회, 틀린 파일의 거절 | 통과 |
| [V08](#v08) | 내용이 틀린 파일을 업로드가 거르는가 | **실패** |
| [V09](#v09) | 로그 조회와 없는 주소 | 통과 |
| [V10](#v10) | baseline 학습 스크립트 | **실패** |
| [V11](#v11) | 학습 기록과 게이트 통과의 경로 | 통과 (주가 예시 파일) |
| [V12](#v12) | 게이트에서 막히면 기존 버전을 유지한다. 지금의 게이트 값이 태양광에 맞는가 | 유지는 통과, 값은 **실패** |
| [V13](#v13) | 학습 뒤의 예측, 배치, 드리프트 시뮬레이션, 로그 | **실패** |
| [V14](#v14) | MLflow 의 운영 버전으로 서빙한다 | **실패** |
| [V15](#v15) | 컨테이너 | 설정은 통과, 빌드는 **실패**, 실행은 미실행 |
| [V16](#v16) | 레지스트리에서의 승격과 되돌리기 | 통과 (앱의 재학습이 아니라 MLflow 의 동작) |
| [V17](#v17) | 응답 시간 | 모델을 거치지 않는 응답은 측정, 예측은 미실행 |
| [V18](#v18) | 업로드 파일의 모양, 날짜의 정렬, 분할, 미래 값의 섞임, 값의 범위 | 통과 |
| [V19](#v19) | 기준 예측의 오차와 상대 게이트의 합격선 | 통과 |
| [V20](#v20) | 성능 지표의 정의, 2021년 사건, 정지와 보류의 수 | 통과 |
| [V21](#v21) | 2025년 인위 주입 장면과 재학습 자료의 날짜 | 통과 |
| [V22](#v22) | 임계값에 따른 오경보와 감지, 알림까지 걸리는 날, 재학습의 조건 | 통과 (표본 안의 계산) |
| [V23](#v23) | 설비 이상 후보의 하루 | 통과 |
| [V24](#v24) | 하루 발전이 끝나는 시각 | 통과 |
| [V25](#v25) | 조사 수치의 재현 스크립트가 지금도 같은 값을 낸다 | 통과 |
| [V26](#v26) | 화면 캡처 | 통과 (지금 상태의 화면 일곱 장) |
| [V27](#v27) | 그림의 색 구분 | 통과 |
| [V28](#v28) | Mermaid 그림의 문법 | 통과 |
| [V29](#v29) | 문서의 링크, 표, JSON 예시, 보관 문서의 보존 | 통과 |
| [V30](#v30) | 직접 학습한 모델의 오프라인 평가 | 통과 (서버의 결과가 아님) |

## 돌리지 못한 것

아래는 코드를 고치지 않고는 돌릴 수 없었다. 기획서에는 미실행으로 적었다.

| 무엇 | 막힌 곳 (정확한 오류) | 고칠 곳 | 기획서 |
| --- | --- | --- | --- |
| 정상 입력의 예측 응답(200) | `model_loader.py`, line 167, `if ___:` → `NameError: name '___' is not defined` | 빈칸 4(`model_loader.py` 167, 169행). 그 뒤 빈칸 2, 3(74, 88행). 읽을 모델도 있어야 한다. 기본 설정은 빈칸 1 뒤에서 저장되는 `haic_v1.keras` 를, MLflow 설정은 빈칸 5 를 거친다 | [⑥ 장면 2](../6-demo.md) |
| 예측의 응답 시간 | 위와 같다 | 위와 같다 | [② 6절](../2-solution-and-goals.md) |
| 배치 예측과 드리프트 판정 | 위와 같다(빈칸 4 에서 멈췄다). 그 뒤 `model_loader.py` 74, 88행과 `routers/predict.py` 85, 88행 | 빈칸 2 ~ 4, 6 ~ 8. 드리프트로 판정되는 배치는 9 ~ 11 도 | [⑥ 장면 7](../6-demo.md) |
| 경고 → 재학습 → 게이트의 로그 | 판정에 닿지 못한다 | 빈칸 7 ~ 11(`drift_detector.py` 58, 59, 73행, `retrain_trigger.py` 65, 75, 84행) | [⑥ 장면 8](../6-demo.md) |
| 승격 전후의 서빙 버전, 재학습 뒤의 서빙 모델 | `model_loader.py`, line 125, `scaler = ___` → `NameError`. 응답의 버전이 고정된 글자다. 승격 뒤 메모리의 모델을 바꾸는 코드가 없다 | 빈칸 5. 그리고 [0008](../../decisions/0008-retraining-and-version-switch.md)의 제안 | [⑥ 장면 5](../6-demo.md), [장면 9](../6-demo.md) |
| 컨테이너의 실행과 호출 | `train_baseline_v1.py`, line 99, `model.fit(___, ___, ...)` → `NameError`. 이미지 빌드의 마지막 단계다 | 빈칸 1 ~ 5 | [⑥ 장면 6](../6-demo.md) |
| 태양광용 상대 게이트, 성능 지표의 판정, 정지와 보류의 갈래 | 코드에 없다 | [0005](../../decisions/0005-deployment-gate.md) ~ [0007](../../decisions/0007-facility-vs-model-branch-and-alerts.md)의 제안 | [③](../3-operations-design.md) |
| 가용성 | 한 달을 띄워 둔 적이 없다 | 재는 도구가 필요하다 | [② 6절](../2-solution-and-goals.md) |

## 건별 기록

### V01

**저장소의 상태와 실행 환경**

| 항목 | 내용 |
| --- | --- |
| 주장 | 검증한 코드가 커밋 `58d6ff8` 그대로이고, 쓴 패키지가 `requirements.txt` 와 같다 |
| 방법 | `python tools/proposal/record_environment.py --compose-dir <검증용 사본의 project 폴더>`. 저장소의 커밋과 변경, 패키지 버전을 `requirements.txt` 와 한 줄씩 대조, 컨테이너 도구의 버전, 빌드 뒤 이미지가 남았는지를 적는다 |
| 일시와 환경 | 2026-10-07 15:46 에 손으로 모아 적었고, 16:59 에 스크립트로 다시 만들었다. 내용은 같다 |
| 입력 | 저장소, `project/requirements.txt` |
| 기대 | `project/` 에 변경이 없다. 여덟 패키지가 같은 버전이다 |
| 실제 | 변경 0개. fastapi 0.141.1, uvicorn 0.46.0, pydantic 2.13.3, numpy 2.4.4, tensorflow 2.21.0, mlflow 3.16.0, requests 2.33.1, python-multipart 0.0.20 이 모두 같다. `project/.venv` 는 없다 |
| 판정 | 통과 |
| 증빙 | [`environment.txt`](environment.txt) |
| 문서에 반영 | ⑥ 의 "어디서 돌렸는가". `project/.venv` 를 만드는 일은 팀의 과제로 남는다 |

### V02

**코드에 남은 빈칸, 정책 상수, 주가 표현, 모델을 바꾸는 코드**

| 항목 | 내용 |
| --- | --- |
| 주장 | 스켈레톤의 빈칸이 그대로 남아 있다. 게이트와 드리프트의 기준이 4.00 이다. 승격 뒤 메모리의 모델을 바꾸는 코드가 없다. 응답의 버전이 고정된 글자다 |
| 방법 | `python tools/proposal/static_scan.py`. 주석과 문서 문자열을 뺀 줄에서 `___` 를 세고, 상수를 뽑고, `_model_cache` 를 건드리는 줄을 찾는다. 코드를 읽기만 한다 |
| 일시와 환경 | 2026-10-07 15:38 |
| 입력 | `project/` 의 `.py`, `.html`, `.yml`, `Dockerfile`. 주가 표현을 셀 때는 `project/README.md` 도 넣었다 |
| 기대 | README 가 말하는 "빈칸 11곳"과 같다 |
| 실제 | 빈칸 11곳이 코드 14줄에 `___` 16개로 남아 있다. `RMSE_GATE = 4.00`, `RMSE_THRESHOLD = 4.00`, `WINDOW_SIZE = 21`, `SEQ_LEN = 20`, `SIMULATED_VOLUME = 1_200_000`. `_model_cache` 를 바꾸는 줄은 `model_loader.py` 안에만 있고 그 밖에는 0줄이다. 버전이 되는 값은 `"v1-local"`(99행)과 `"production"`(126행)이다. 주가 표현은 README 를 넣어 `HAIC` 43회, `종가` 25회, `달러` 23회(README 를 빼면 38회, 22회, 23회) |
| 판정 | 통과 (주장이 코드와 같다) |
| 증빙 | [`static_scan.txt`](static_scan.txt), [`static_scan.json`](static_scan.json) |
| 문서에 반영 | ③ 의 1, 11, 12절, ④ 의 5, 6절, ⑥ 의 장면 5. "승격해도 서빙 모델이 그대로다"는 코드를 읽어 얻은 결론이고 서버에서 재현한 것이 아니라고 적었다 |

### V03

**서버가 뜨고 엔드포인트 목록이 코드와 같다**

| 항목 | 내용 |
| --- | --- |
| 주장 | 빈칸이 남아 있어도 서버는 뜬다. 엔드포인트가 코드의 라우터와 같다 |
| 방법 | 서버를 띄우고 `python tools/proposal/http_checks.py --phase pre`. `/health`, `/`, `/docs`, `/openapi.json` 을 부른다 |
| 일시와 환경 | 2026-10-07 15:19 |
| 입력 | 없다 |
| 기대 | 200. OpenAPI 의 경로가 `/predict`, `/predict/batch-test`, `/health`, `/data/upload`, `/data/status`, `/logs`, `/logs/{filename}` |
| 실제 | 모두 200. 경로 7개가 같다. `/health` 는 `{"status": "ok", "model_loaded": false, "loading_mode": "lazy"}`. 제목은 "HAIC Serving & AIOps", 버전 0.1.0, OpenAPI 3.1.0 |
| 판정 | 통과 |
| 증빙 | [`health_before.json`](http/health_before.json), [`root_dashboard.json`](http/root_dashboard.json), [`docs_swagger.json`](http/docs_swagger.json), [`openapi.json`](openapi.json), [`01_server_local_lazy.log`](logs/01_server_local_lazy.log) |
| 문서에 반영 | ⑤ 의 1, 4, 8, 10절, ④ 의 7절 |

### V04

**정상 입력의 예측**

| 항목 | 내용 |
| --- | --- |
| 주장 | 최근 20일을 보내면 다음 날의 값과 모델 버전이 돌아온다 |
| 방법 | `http_checks.py --phase pre` 의 `predict_valid_current_schema`. 학습을 돌린 뒤 `--phase post` 로 한 번 더 |
| 일시와 환경 | 2026-10-07 15:19, 15:21 |
| 입력 | `datasets/hadong_upload_forecast_jma.csv` 의 마지막 20행(2026-02-08 ~ 02-27). 지금의 스키마에 맞추려고 `Volume` 을 정수로 반올림했다 |
| 기대 | 200, `predicted_close` 와 `model_version` |
| 실제 | **500 `Internal Server Error`** (`text/plain`). 서버 로그: `model_loader.py`, line 167, `if ___:`, `NameError: name '___' is not defined`. 학습 뒤에도 같다 |
| 판정 | **실패** |
| 증빙 | [`predict_valid_current_schema.json`](http/predict_valid_current_schema.json), [`predict_valid_after_training.json`](http/predict_valid_after_training.json), [`01_server_local_lazy.log`](logs/01_server_local_lazy.log) |
| 문서에 반영 | ⑤ 의 2절에 200 응답의 예시를 지어 넣지 않았다. ⑥ 의 장면 2 를 "일부만"으로 적었다. ① 의 7절 |

### V05

**틀린 예측 요청을 422 로 거절한다**

| 항목 | 내용 |
| --- | --- |
| 주장 | 길이와 값이 틀린 요청은 예측 전에 422 로 거절되고, 어느 칸이 왜 틀렸는지 알려 준다 |
| 방법 | `http_checks.py --phase pre`. 정상 입력에서 한 가지씩만 바꾼 여덟 가지 |
| 일시와 환경 | 2026-10-07 15:19 |
| 입력 | 19개, 21개, 마지막 `close` 0, `volume` 을 소수 그대로, 첫 `volume` −1, 첫 점에 `volume` 없음, `{}`, JSON 이 아닌 글자 |
| 기대 | 모두 422 |
| 실제 | 모두 422. `type` 은 차례로 `too_short`, `too_long`, `greater_than`, `int_from_float`, `greater_than_equal`, `missing`, `missing`, `json_invalid`. `loc` 과 `msg` 는 ⑤ 의 2절에 옮겼다 |
| 판정 | 통과. 다만 `close` 0 과 소수 `volume` 의 거절은 태양광에서는 고쳐야 할 동작이다 |
| 증빙 | [`predict_19_items.json`](http/predict_19_items.json), [`predict_21_items.json`](http/predict_21_items.json), [`predict_close_zero.json`](http/predict_close_zero.json), [`predict_volume_float.json`](http/predict_volume_float.json), [`predict_volume_negative.json`](http/predict_volume_negative.json), [`predict_field_missing.json`](http/predict_field_missing.json), [`predict_empty_object.json`](http/predict_empty_object.json), [`predict_body_not_json.json`](http/predict_body_not_json.json), [`predict_get_not_allowed.json`](http/predict_get_not_allowed.json) |
| 문서에 반영 | ⑤ 의 2절, ③ 의 2절, ⑥ 의 장면 2, 결정 기록 0002 |

### V06

**배치 예측**

| 항목 | 내용 |
| --- | --- |
| 주장 | 이어진 41개를 보내면 21건을 예측하고 드리프트를 판정한다. 21개보다 적거나 숫자가 아니면 422 다 |
| 방법 | `http_checks.py --phase pre`, `--phase post` |
| 일시와 환경 | 2026-10-07 15:19, 15:21 |
| 입력 | 업로드 파일의 마지막 41행(2026-01-18 ~ 02-27)의 발전량. 틀린 입력: 20개, 글자 |
| 기대 | 41개에 200 과 예측 21개, `drift_check`. 틀린 입력에 422 |
| 실제 | 41개에 **500**(V04 와 같은 빈칸). 20개에 422 `too_short`, `loc` `["body", "prices"]`. 글자에 422 `float_parsing` |
| 판정 | 422 는 통과, 정상 입력은 **실패** |
| 증빙 | [`batch_41_values.json`](http/batch_41_values.json), [`batch_41_after_training.json`](http/batch_41_after_training.json), [`batch_20_values.json`](http/batch_20_values.json), [`batch_wrong_type.json`](http/batch_wrong_type.json) |
| 문서에 반영 | ⑤ 의 3절. `drift_check` 의 내용은 코드를 읽어 적었다고 표시했다 |

### V07

**업로드와 상태 조회, 틀린 파일의 거절**

| 항목 | 내용 |
| --- | --- |
| 주장 | CSV 를 올리면 행 수가 돌아오고 상태 조회가 그 파일의 기간을 알려 준다. 형식이 틀린 파일은 거절된다 |
| 방법 | `http_checks.py --phase upload-haic`, `upload-errors`, `upload-hadong` |
| 일시와 환경 | 2026-10-07 15:19 ~ 15:20 |
| 입력 | `project/data/sample_haic_prices.csv`(756행), `datasets/hadong_upload_forecast_jma.csv`(1,337행). 틀린 파일: CP949 원본, 세 열이 없는 분석용 파일, 앞 40행만 자른 것, 파일 없이 호출 |
| 기대 | 올린 파일의 행 수와 기간이 그대로 나온다. 틀린 파일은 400, 파일이 없으면 422 |
| 실제 | 주가 예시 200(756행, 2026-01-02 ~ 2028-11-24). 태양광 200(1,337행, 2022-07-02 ~ 2026-02-27, 발전량 5.886 ~ 338.832). 올리기 전의 상태 조회는 `{"exists": false}`. 틀린 파일 셋은 400, 파일 없음은 422 |
| 판정 | 통과 |
| 증빙 | [`upload_haic_sample.json`](http/upload_haic_sample.json), [`data_status_haic.json`](http/data_status_haic.json), [`upload_hadong_forecast.json`](http/upload_hadong_forecast.json), [`data_status_hadong.json`](http/data_status_hadong.json), [`data_status_empty.json`](http/data_status_empty.json), [`upload_cp949.json`](http/upload_cp949.json), [`upload_missing_columns.json`](http/upload_missing_columns.json), [`upload_40_rows.json`](http/upload_40_rows.json), [`upload_no_file.json`](http/upload_no_file.json) |
| 문서에 반영 | ⑤ 의 5, 6절, ⑥ 의 장면 1 |

### V08

**내용이 틀린 파일을 업로드가 거르는가**

| 항목 | 내용 |
| --- | --- |
| 주장 | 날짜가 뒤바뀌거나 빠진 파일, 숫자가 아닌 값이나 음수가 든 파일은 학습 자료가 되기 전에 거절돼야 한다 |
| 방법 | `http_checks.py --phase upload-gaps`. 업로드 파일의 마지막 60행을 메모리에서만 고쳐 보내고, 그때마다 상태 조회를 부른다. 끝나면 원래 파일을 다시 올린다. `datasets/` 는 바꾸지 않는다 |
| 일시와 환경 | 2026-10-07 15:43 |
| 입력 | 날짜를 거꾸로, 5행을 빼고 한 행의 날짜를 앞 행과 같게(날짜 여섯이 빠지고 하나가 겹친다. 55행), 발전량 −10 과 예보 −1, 발전량 칸에 `abc`, 발전량 칸을 비움 |
| 기대 | 다섯 가지 모두 거절 |
| 실제 | **다섯 가지 모두 200 으로 올라갔다.** 거꾸로 된 파일은 상태 조회의 시작일이 2026-02-27, 끝일이 2025-12-30 으로 나온다. 음수 파일은 `min_close` 가 −10.0 이다. `abc` 와 빈 칸이 든 파일은 올라간 뒤 **상태 조회가 500** 이 된다(`ValueError: could not convert string to float`) |
| 판정 | **실패** |
| 증빙 | [`upload_dates_reversed.json`](http/upload_dates_reversed.json), [`data_status_after_dates_reversed.json`](http/data_status_after_dates_reversed.json), [`upload_dates_gap_duplicate.json`](http/upload_dates_gap_duplicate.json), [`data_status_after_dates_gap_duplicate.json`](http/data_status_after_dates_gap_duplicate.json), [`upload_negative_values.json`](http/upload_negative_values.json), [`data_status_after_negative_values.json`](http/data_status_after_negative_values.json), [`upload_non_numeric.json`](http/upload_non_numeric.json), [`data_status_after_non_numeric.json`](http/data_status_after_non_numeric.json), [`upload_empty_value.json`](http/upload_empty_value.json), [`data_status_after_empty_value.json`](http/data_status_after_empty_value.json), [`upload_gaps_restore.json`](http/upload_gaps_restore.json), [`data_status_after_restore.json`](http/data_status_after_restore.json), [`10_server_upload_gaps.log`](logs/10_server_upload_gaps.log) |
| 문서에 반영 | ③ 의 2절(업로드 검증의 제안), ⑤ 의 5, 6절, 결정 기록 0002. 고칠 곳은 `serving_app/routers/data.py` 의 `upload` |

### V09

**로그 조회와 없는 주소**

| 항목 | 내용 |
| --- | --- |
| 주장 | 로그 파일의 목록과 내용을 API 로 볼 수 있다 |
| 방법 | `http_checks.py --phase pre`, `--phase post` |
| 일시와 환경 | 2026-10-07 15:19, 15:21 |
| 입력 | `/logs`, `/logs/aiops.log`, `/logs/no-such-file.log`, `/no-such-path` |
| 기대 | 목록과 내용이 200, 없는 파일과 없는 주소는 404 |
| 실제 | `/logs` 는 `[{"name": "aiops.log", "size": 0}]`. 내용은 빈 글자. 없는 파일은 404 `로그 파일을 찾을 수 없습니다`. 없는 주소는 404 `Not Found`. 학습과 배치 뒤에도 로그는 0바이트다 |
| 판정 | 통과. 다만 로그에 쌓인 것이 없다 |
| 증빙 | [`logs_list_before.json`](http/logs_list_before.json), [`logs_read_aiops.json`](http/logs_read_aiops.json), [`logs_read_missing.json`](http/logs_read_missing.json), [`not_found.json`](http/not_found.json), [`logs_list_after.json`](http/logs_list_after.json), [`logs_read_aiops_after.json`](http/logs_read_aiops_after.json) |
| 문서에 반영 | ⑤ 의 7절, ③ 의 8절, ⑥ 의 장면 8 |

### V10

**baseline 학습 스크립트**

| 항목 | 내용 |
| --- | --- |
| 주장 | 올린 파일로 스케일러를 맞추고 baseline 모델을 학습해 저장한다 |
| 방법 | `project/` 에서 `python scripts/train_baseline_v1.py`. 주가 예시 파일을 올린 뒤 한 번, 태양광 파일을 올린 뒤 한 번. 앞뒤로 `registry_dump.py` |
| 일시와 환경 | 2026-10-07 15:19, 15:20 |
| 입력 | 가장 최근에 올린 파일 |
| 기대 | 스케일러와 `haic_v1.keras` 가 저장되고 RMSE 가 찍힌다 |
| 실제 | `scaler fit on 756행 -> serving_app/models/scaler.pkl` 을 찍은 뒤 99행 `model.fit(___, ___, ...)` 에서 `NameError`. 종료 코드는 태양광 파일 쪽에서 1 로 기록됐다(주가 예시 쪽은 값을 받지 못했다). **스케일러만 저장되고 모델은 저장되지 않았다.** 태양광 파일로 돌렸을 때도 같고, 그때 스케일러가 종가 105.61 ~ 195.17 에서 발전량 5.886 ~ 338.832 로 덮어써졌다. Production 은 주가로 학습한 버전 1 그대로였다 |
| 판정 | **실패** |
| 증빙 | [`02_train_baseline_haic.log`](logs/02_train_baseline_haic.log), [`04_train_baseline_hadong.log`](logs/04_train_baseline_hadong.log), [`registry_1-after-haic-train.json`](registry/registry_1-after-haic-train.json), [`registry_2-after-hadong-baseline.json`](registry/registry_2-after-hadong-baseline.json) |
| 문서에 반영 | ③ 의 3절(스케일러와 모델이 어긋나는 일), ⑥ 의 장면 3, 4, 결정 기록 0008. 고칠 곳은 빈칸 1. 첫 로그의 종료 코드 줄이 비어 있는 것은 기록할 때 값을 받지 못한 것이고, 실패는 오류 문장으로 확인된다 |

### V11

**학습 기록과 게이트 통과의 경로**

| 항목 | 내용 |
| --- | --- |
| 주장 | 학습의 지표가 MLflow 에 기록되고, 게이트를 통과하면 새 버전이 Production 이 된다 |
| 방법 | `project/` 에서 `python serving_app/train_and_register.py`, 이어서 `registry_dump.py --label 1-after-haic-train` |
| 일시와 환경 | 2026-10-07 15:19 ~ 15:20. 시드 42, 100 epoch |
| 입력 | 스켈레톤의 주가 예시 파일(756행). 실습 코드의 분할(뒤 20%) |
| 기대 | RMSE 가 4.00 이하이면 버전 1 이 Production |
| 실제 | `[GATE PASSED] rmse=2.03 -> HAIC_Predictor v1 promoted to Production`. 실행 기록: `rmse` 2.0278, `mode` scratch, `epochs` 100. 레지스트리: 버전 1, Production. `mlflow.db` 와 `mlruns/` 에 기록됐다. 두 곳에 쓰인 것은 검증용 사본의 폴더를 열어 확인했다. `mlruns/` 의 목록은 증빙으로 남기지 않았다 |
| 판정 | 통과. 주가 예시 파일의 결과다. 태양광 모델이 게이트를 통과한 것이 아니다 |
| 증빙 | [`03_train_register_haic.log`](logs/03_train_register_haic.log), [`registry_1-after-haic-train.json`](registry/registry_1-after-haic-train.json) |
| 문서에 반영 | ⑥ 의 장면 3, ④ 의 2, 7절 |

### V12

**게이트에서 막히면 기존 버전을 유지한다. 지금의 게이트 값이 태양광에 맞는가**

| 항목 | 내용 |
| --- | --- |
| 주장 | (가) 게이트에서 막힌 모델은 등록되지 않고 운영 버전이 그대로다. (나) 지금의 게이트 값으로 태양광 모델을 가릴 수 있다 |
| 방법 | 태양광 파일을 올린 뒤 `python serving_app/train_and_register.py`. 앞뒤로 `registry_dump.py` |
| 일시와 환경 | 2026-10-07 15:20 ~ 15:21(약 21초). 시드 42, 100 epoch |
| 입력 | `datasets/hadong_upload_forecast_jma.csv`. 학습 정답일 2022-07-22 ~ 2025-06-08(1,053건), 시험 정답일 2025-06-09 ~ 2026-02-27(264건) |
| 기대 | (가) 버전이 늘지 않고 Production 이 버전 1 이다. (나) 좋은 모델은 통과하고 나쁜 모델은 막힌다 |
| 실제 | `[GATE FAILED] rmse=41.59 > 4.0 -> 배포 차단, 기존 Production 유지`. 실행 기록은 둘(2.0278, 41.5888)이고 모델 버전은 하나, Production 은 버전 1 이다. (나) 4.00 은 이 구간의 하루 평균 발전량(194kWh)의 2% 다. 직접 학습한 모델(41.59kWh)과 기준 예측 넷(45.26 ~ 82.44kWh)이 모두 열 배 넘게 벗어난다. 통과한 모델을 본 것은 없다 |
| 판정 | (가) 통과(레지스트리 수준). (나) **실패** |
| 증빙 | [`05_train_register_hadong.log`](logs/05_train_register_hadong.log), [`registry_3-after-hadong-train.json`](registry/registry_3-after-hadong-train.json) |
| 문서에 반영 | ③ 의 4절, ⑥ 의 장면 4, 결정 기록 0005. 서버가 버전 1 로 계속 답하는지는 확인하지 못했다고 적었다. 고칠 곳은 `train_and_register.py` 의 `RMSE_GATE` 와 `_register_if_gate_passed` |

### V13

**학습 뒤의 예측, 배치, 드리프트 시뮬레이션, 로그**

| 항목 | 내용 |
| --- | --- |
| 주장 | 학습을 마치면 예측이 되고, 드리프트 배치를 보내면 경고와 재학습이 로그에 남는다 |
| 방법 | 학습 뒤 `http_checks.py --phase post`, `project/` 에서 `python scripts/simulate_drift.py` |
| 일시와 환경 | 2026-10-07 15:21 |
| 입력 | 정상 20행, 이어진 41행. 시뮬레이션은 스크립트가 만든 무작위 가격 41개 |
| 기대 | 예측 200. 시뮬레이션이 `normal` 과 `drift_injection` 의 결과를 찍는다. `aiops.log` 에 세 줄 |
| 실제 | `/health` 의 `model_loaded` 가 `false`. 예측 500, 배치 500. 시뮬레이션은 `[1] 기준 통계: mean=189.80, std=80.02` 를 찍고 `requests.exceptions.HTTPError: 500 Server Error ... /predict/batch-test` 로 멈췄다(종료 코드 1). `aiops.log` 는 0바이트 |
| 판정 | **실패** |
| 증빙 | [`health_after_training.json`](http/health_after_training.json), [`predict_valid_after_training.json`](http/predict_valid_after_training.json), [`batch_41_after_training.json`](http/batch_41_after_training.json), [`06_simulate_drift.log`](logs/06_simulate_drift.log), [`logs_read_aiops_after.json`](http/logs_read_aiops_after.json) |
| 문서에 반영 | ⑥ 의 장면 7, 8, ③ 의 1, 8절, ④ 의 2절. 고칠 곳은 빈칸 2 ~ 4, 6 ~ 11 |

### V14

**MLflow 의 운영 버전으로 서빙한다**

| 항목 | 내용 |
| --- | --- |
| 주장 | `MODEL_SOURCE=mlflow` 로 띄우면 레지스트리의 Production 모델로 예측한다 |
| 방법 | `MODEL_SOURCE=mlflow LOADING_MODE=eager` 로 서버를 띄운다. 이어서 `MODEL_SOURCE=mlflow`(lazy)로 띄워 `/health` 와 `/predict` 를 부른다. 다시 띄웠을 때는 `http_checks.py --out docs/proposal/evidence/http_mlflow_lazy --phase mlflow-lazy` 로 세 요청을 보냈다. 셋째는 ⑤ 9절의 제안 본문(날짜와 소수 예보)이다 |
| 일시와 환경 | 2026-10-07 15:25. 16:58 에 lazy 쪽을 한 번 더 띄워 요청과 응답을 같은 도구로 다시 남겼다 |
| 입력 | 레지스트리의 버전 1, V04 와 같은 20행 |
| 기대 | eager: 서버가 뜨고 `model_loaded` 가 `true`. lazy: 첫 예측이 200 |
| 실제 | eager: 모델을 불러온 뒤 `model_loader.py`, line 125, `scaler = ___` 에서 `NameError`. `Application startup failed. Exiting.` 종료 코드 3. lazy: `/health` 200, `/predict` 500(167행). 다시 띄웠을 때도 같았다. 제안 본문은 422 였고 스무 칸의 `volume` 에 `int_from_float` 오류가 돌아왔다. `date` 에 대한 오류는 없었다 |
| 판정 | **실패** |
| 증빙 | [`07_server_mlflow_eager.log`](logs/07_server_mlflow_eager.log), [`08_server_mlflow_lazy.log`](logs/08_server_mlflow_lazy.log), [`12_server_mlflow_lazy_recheck.log`](logs/12_server_mlflow_lazy_recheck.log), [`http_mlflow_lazy/health.json`](http_mlflow_lazy/health.json), [`http_mlflow_lazy/predict_valid.json`](http_mlflow_lazy/predict_valid.json), [`http_mlflow_lazy/predict_with_date_and_float.json`](http_mlflow_lazy/predict_with_date_and_float.json) |
| 문서에 반영 | ③ 의 11절, ⑥ 의 장면 5, 결정 기록 0008. 고칠 곳은 빈칸 5(125행)와 빈칸 4 |

### V15

**컨테이너**

| 항목 | 내용 |
| --- | --- |
| 주장 | 컨테이너 하나로 8099 에서 같은 서비스가 뜬다 |
| 방법 | 커밋 `58d6ff8` 의 `project/` 를 임시 폴더에 풀고, 거기서 `docker compose -f serving_app/docker-compose.yml config`, 이어서 `docker build --progress=plain -f serving_app/Dockerfile -t solar-aiops-verify:58d6ff8 .` |
| 일시와 환경 | 2026-10-07 15:38 ~ 15:40. Docker 29.6.2, Compose v5.3.1 |
| 입력 | 이미지를 만들 때 스켈레톤의 주가 예시 파일로 학습한다 |
| 기대 | 설정이 서비스 하나와 포트 8099 를 보여 준다. 이미지가 만들어진다. 컨테이너의 `/health` 가 `model_loaded: true` |
| 실제 | 설정: 서비스 `serving-app`, 포트 8099, 통과. 빌드: 여덟 단계 가운데 일곱은 통과(패키지 설치 119초). 마지막 단계에서 `scaler fit on 756행` 뒤 `train_baseline_v1.py`, line 99 의 `NameError` 로 실패. 종료 코드 1. 빌드 뒤 `docker images` 에 그 이름의 이미지가 없다. 컨테이너는 띄우지 못했다 |
| 판정 | 설정은 통과, 빌드는 **실패**, 실행과 호출은 미실행 |
| 증빙 | [`09_docker_build.log`](logs/09_docker_build.log), [`environment.txt`](environment.txt) |
| 문서에 반영 | ⑥ 의 장면 6, ④ 의 7절. 고칠 곳은 빈칸 1 ~ 5. 빌드가 통과해도 컨테이너는 주가 예시 파일의 모델을 서빙한다는 점을 적었다 |

### V16

**레지스트리에서의 승격과 되돌리기**

| 항목 | 내용 |
| --- | --- |
| 주장 | 앱의 승격 방식으로 올리면 이전 버전이 어떻게 되는가. 새 버전을 내리면 이전 버전으로 돌아가는가 |
| 방법 | 검증용 사본의 `project/` 에서 `python <저장소>/tools/proposal/registry_semantics.py`. 앱이 승격할 때 부르는 두 호출(`train_and_register.py` 61 ~ 62행)을 같은 인자로 직접 부르고, 이어서 새 버전을 Archived 로 내린다. 단계마다 레지스트리를 적는다 |
| 일시와 환경 | 2026-10-07 15:43. MLflow 3.16.0 |
| 입력 | V11 의 실행 기록에 있는 모델 |
| 기대 | 확인하려는 것이라 기대가 따로 없다 |
| 실제 | 처음: 버전 1 Production, `models:/HAIC_Predictor/Production` 은 1. 올린 뒤: **버전 1 과 2 가 함께 Production**, 가리키는 버전은 2. 버전 2 를 Archived 로 내린 뒤: 가리키는 버전은 1. "가리키는 버전"은 MLflow 가 이 주소를 풀 때 쓰는 조회(`get_latest_versions`)로 본 것이다. 주소로 모델을 불러와 확인한 것은 아니다 |
| 판정 | 통과. **앱의 재학습을 돌린 결과가 아니라 MLflow 의 동작을 따로 본 것이다** |
| 증빙 | [`registry_semantics.json`](registry/registry_semantics.json) |
| 문서에 반영 | ③ 의 10절(되돌리기의 손 절차, 승격할 때 이전 버전을 Archived 로), ⑥ 의 장면 5, 결정 기록 0008 |

### V17

**응답 시간**

| 항목 | 내용 |
| --- | --- |
| 주장 | 예측 한 건이 1초 안에 돌아온다 |
| 방법 | `http_checks.py --phase latency`: 같은 PC 에서 요청을 50번씩 보내 걸린 시간을 잰다. `model_timing.py`: 레지스트리의 모델을 불러와 (1, 20, 2) 입력 하나를 50번 계산한다 |
| 일시와 환경 | 2026-10-07 15:21, 15:44. 같은 PC 안의 호출이라 네트워크 지연이 없다 |
| 입력 | `/health`, 19개짜리 예측 요청(422), `/data/status`. 모델은 레지스트리의 버전 1(주가 예시 파일로 학습한 모델. 구조는 태양광용과 같다)이고 입력은 무작위 값이다 |
| 기대 | `POST /predict` 의 95번째 백분위가 1초 이하 |
| 실제 | **예측의 응답 시간은 재지 못했다**(500). 모델을 거치지 않는 응답: `/health` 중앙값 0.52ms, 422 응답 0.55ms, `/data/status` 1.43ms. 모델만: 라이브러리를 읽는 데 6.1초, 모델을 불러오는 데 0.89초, 처음 계산 251.5ms, 그 뒤 50번의 중앙값 32.7ms, 95번째 백분위 73.4ms, 최대 216.2ms |
| 판정 | 예측의 응답 시간은 미실행. 나머지는 참고값이다 |
| 증빙 | [`latency_http.json`](latency_http.json), [`latency_model.json`](latency_model.json) |
| 문서에 반영 | ② 의 6절(지금 잰 값 칸에 "재지 못했다"), ① 의 7절, 결정 기록 0004. 모델 계산 시간을 엔드포인트의 응답 시간이라고 적지 않았다 |

### V18

**업로드 파일의 모양, 날짜의 정렬, 분할, 미래 값의 섞임, 값의 범위**

| 항목 | 내용 |
| --- | --- |
| 주장 | 업로드 파일의 d 일 행에 d 일의 발전량과 d+1 일에 대한 예보가 있다. 날짜가 이어져 있다. 창에 대상일의 발전량이 들어가지 않는다 |
| 방법 | `python tools/proposal/data_checks.py`. 실습 코드의 창과 분할을 같은 규칙으로 다시 계산한다(코드를 불러오지 않는다) |
| 일시와 환경 | 2026-10-07 |
| 입력 | `datasets/` 의 업로드 파일 셋, `raw/data_15043409.csv`, `raw/wx_prevruns_daily.csv` |
| 기대 | 원본과의 차이 0, 날짜의 공백과 중복 0 |
| 실제 | 예보 파일: 1,337행, 2022-07-02 ~ 2026-02-27, 공백 0, 중복 0, 빈 값 0. `Close` 가 원본의 하루 합계와 같다(차이 0). `Volume[d]` 가 d+1 일 예보의 원본과 같다(차이 0). `Volume[d]` 와 `Close[d+1]` 의 상관 0.775, 같은 행끼리 0.322. `Volume` 의 99.9% 가 소수. 분할: 표본 1,317, 학습 1,053, 시험 264. 표본 1,317개를 하나씩 보니 모두 정답일이 창의 마지막 날 바로 다음 날이고 창은 이어진 20일이다. 학습의 마지막 정답일이 시험의 첫 정답일보다 앞이다. 시험 구간에 3 ~ 5월이 없다. 스케일러를 학습 행만으로 맞춰도 최소·최대가 같다. 값의 범위: 하루 발전량 0 ~ 379.752kWh(55kW × 24시간은 1,320kWh), 예보 0.95 ~ 28.36MJ/m², 광양 관측 최대 31.40MJ/m², 이 위도의 대기권 밖 일사량 16.5 ~ 41.5MJ/m² |
| 판정 | 통과 |
| 증빙 | [`data_checks.txt`](data_checks.txt) A, B, H, [`data_checks.json`](data_checks.json) |
| 문서에 반영 | ② 의 3, 5절, ③ 의 2, 3절, 결정 기록 0002 |

### V19

**기준 예측의 오차와 상대 게이트의 합격선**

| 항목 | 내용 |
| --- | --- |
| 주장 | 같은 시험 날짜에서 학습 없는 방법들의 오차를 계산할 수 있고, 제안하는 게이트의 합격선이 47.5kWh 다 |
| 방법 | `data_checks.py` 의 C. 대상일 전날까지의 행만 쓴다 |
| 일시와 환경 | 2026-10-07 |
| 입력 | 예보 업로드 파일. 시험 2025-06-09 ~ 2026-02-27 의 264일 |
| 기대 | 조사의 값(7일 평균 71.65, 20일 평균 74.03, 규칙C 45.26)과 같다 |
| 실제 | 어제 값 82.44kWh(합계 오차율 31.4%, 치우침 +0.3%), 7일 평균 71.65(28.2%, +0.8%), 20일 평균 74.03(30.3%, +0.8%), 규칙C 45.26(16.9%, −0.1%). 하루 평균 발전량 194.18kWh. 합격선: 71.65 × 0.80 = 57.32, 45.26 × 1.05 = 47.53 |
| 판정 | 통과. 조사의 값과 같다 |
| 증빙 | [`data_checks.txt`](data_checks.txt) C, [`figures_data.json`](figures_data.json) |
| 문서에 반영 | ② 의 7절, ③ 의 4절, ① 의 6, 7절, 결정 기록 0005 |

### V20

**성능 지표의 정의, 2021년 사건, 정지와 보류의 수**

| 항목 | 내용 |
| --- | --- |
| 주장 | 정지·보류·유효한 날의 규칙을 직접 적용하면 파일의 표시와 같다. 2021년의 하락 전후가 임계값의 양쪽으로 갈린다 |
| 방법 | `data_checks.py` 의 D. 규칙은 `tools/verify/t5_independent_audit.py` 의 정의를 따랐다 |
| 일시와 환경 | 2026-10-07 |
| 입력 | `datasets/hadong_daily_full.csv`. 4,807일 |
| 기대 | 파일의 유효일 열과 모두 같다. 조사의 값(기준선 0.9809, −0.8%, −14.6%)과 같다 |
| 실제 | 기대 발전량이 있는 날 4,738일, 발전량 0 인 날 24일, 정지 49일, 보류 68일, 유효한 날 4,658일. 파일의 열과 모두 같다. 기준선(2021-04-01 까지 365일) 0.9809. 하락 전 배치(대상 04-22 ~ 05-12) 0.9735, 유효한 날 20일, −0.8%. 하락 뒤 배치(대상 06-07 ~ 06-27) 0.8382, 21일, −14.6%. 앞뒤 365일: 2021-05-18 기준 0.9817 → 0.8985(−8.5%), 2024-03-22 기준 0.9007 → 0.9532(+5.8%) |
| 판정 | 통과 |
| 증빙 | [`data_checks.txt`](data_checks.txt) D |
| 문서에 반영 | ① 의 5절, ③ 의 5, 7절, ⑥ 의 장면 11, 결정 기록 0006, 0007. 성능 지표가 사후 값이라는 점을 쓸 때마다 적었다 |

### V21

**2025년 인위 주입 장면과 재학습 자료의 날짜**

| 항목 | 내용 |
| --- | --- |
| 주장 | 기준선을 고정해도 고른 시연 날짜에서 주입한 배치와 그렇지 않은 배치가 갈린다. 배치의 날짜와 재학습 자료의 날짜를 맞출 수 있다 |
| 방법 | `data_checks.py` 의 E. 2025-06-21 부터 발전량에 배율을 곱하고 정지·보류를 다시 판정한 뒤 대상 21일의 성능 지표를 구한다 |
| 일시와 환경 | 2026-10-07 |
| 입력 | `hadong_daily_full.csv`. 기준선은 2025-02-28 까지 365일. 대상 2025-07-11 ~ 07-31. 배율 1.0, 0.86, 0.80, 0.70 |
| 기대 | 조사의 값은 주입 직전 365일을 기준선으로 한 −2.0%, −15.5% 다. 고정 기준선의 값은 조사에 없어 새로 계산한다 |
| 실제 | 기준선 0.950992(유효한 날 352일). 배율 1.0 은 −2.2%(주입 직전 기준선으로는 −2.0%). 0.86 은 −15.6%(−15.5%). 0.80 은 −21.4%. 0.70 은 유효한 날이 0일이고 보류가 21일이라 판정되지 않는다. 2025-07-31 에서 자른 예보 파일의 마지막 41행은 2025-06-21 ~ 07-31 이다 |
| 판정 | 통과. 날짜는 조사에서 결과를 보고 고른 것이다 |
| 증빙 | [`data_checks.txt`](data_checks.txt) E |
| 문서에 반영 | ③ 의 5, 9절, ⑥ 의 장면 7, 8, 10, 결정 기록 0006, 0009 |

### V22

**임계값에 따른 오경보와 감지, 알림까지 걸리는 날, 재학습의 조건**

| 항목 | 내용 |
| --- | --- |
| 주장 | 임계값을 낮추면 오경보가 늘고 높이면 놓침이 는다. −7.5% 가 그 사이다. 날마다 판정하면 14% 수준의 하락은 대부분 4주 안에 임계값을 넘는다. 재학습을 거는 조건은 변화가 없을 때 채워지지 않는다 |
| 방법 | `python tools/proposal/threshold_sweep.py`. 기준선을 고정하고 주 단위 시작일마다 배율을 곱한다. 셋을 센다. (1) 내려간 뒤의 21일이 찬 배치가 임계값을 넘는지. (2) 날마다 그날까지의 21일로 판정할 때 처음 넘는 날. (3) 최근 41일의 앞 20일과 뒤 21일이 함께 넘는 첫날 |
| 일시와 환경 | 2026-10-07. 계산을 보태며 여러 번 다시 돌렸다. (1)의 값은 처음부터 같다 |
| 입력 | `hadong_daily_full.csv`. 기준선 2025-02-28 까지 365일. 시작일 2025-03-08 ~ 11-15 의 7일 간격 37개. 대상은 시작일+20 ~ +40. 유효한 날 15일 이상일 때만 판정 |
| 기대 | 0.86 주입에서 −7.5% 를 넘는 비율이 조사의 값(고정 기준선 91.9%)과 같다 |
| 실제 | −7.5% 에서 변화 없음 1개(2.7%), 8.5% 하락 25개(67.6%), 14% 하락 34개(91.9%). −5% 에서 7개, 28개, 37개. −10% 에서 0개, 20개, 29개. 20% 하락은 10개, 30% 하락은 35개가 판정되지 않는다 (2) 변화가 없어도 임계값을 넘는 구간(2025-04-14 ~ 04-20, 7일)을 만나는 시작일 7개를 뺀 30개에서, 14% 하락은 21일 안 27개, 28일 안 28개, 41일 안 30개(가운데 8일째). 8.5% 하락은 22개, 23개, 23개(가운데 11일째)이고 넘지 못한 7개는 모두 10 ~ 11월의 시작일이다. 변화가 없는 299일을 날마다 판정하면 임계값 아래인 날이 7일, 한 번의 구간이다. (3) 변화가 없으면 37개 가운데 0개. 14% 하락은 32개(가운데 26일째, 7 ~ 35일째), 8.5% 하락은 28개(가운데 31일째, 9 ~ 39일째). 시연 배치는 그대로면 앞 20일 −2.8%, 뒤 21일 −2.2%, 0.86 을 곱하면 −16.3%, −15.6% |
| 판정 | 통과. 조사의 91.9% 와 같다. **표본 안의 계산이다.** 임계값과 날짜를 같은 자료에서 골랐고 배치가 겹친다 |
| 증빙 | [`threshold_sweep.txt`](threshold_sweep.txt), [`threshold_sweep.json`](threshold_sweep.json) |
| 문서에 반영 | ③ 의 6, 9절, ② 의 6절, ⑥ 의 장면 7, 결정 기록 0004, 0006, 0008, 0009 |

### V23

**설비 이상 후보의 하루**

| 항목 | 내용 |
| --- | --- |
| 주장 | 2025-03-31 이 하루 점검 알림의 조건에 든다 |
| 방법 | `data_checks.py` 의 F |
| 일시와 환경 | 2026-10-07 |
| 입력 | `hadong_daily_full.csv` 의 2025-03-31 |
| 기대 | 조사의 값(실제 141.5kWh, 기대 296kWh, 0.48배)과 같다 |
| 실제 | 실제 141.516kWh, 기대 296.2kWh, 비율 0.48. 낮은 날(70% 미만)이고 하루 점검 알림(50% 미만)의 조건에 든다. 정지와 보류는 아니다 |
| 판정 | 통과 |
| 증빙 | [`data_checks.txt`](data_checks.txt) F |
| 문서에 반영 | ③ 의 7절, ⑥ 의 장면 10. 원인은 모른다고 적었다 |

### V24

**하루 발전이 끝나는 시각**

| 항목 | 내용 |
| --- | --- |
| 주장 | 전날 20시에는 그날의 발전이 모두 끝나 있다 |
| 방법 | `data_checks.py` 의 G. 시간대별 값을 발전량으로 가중해 누적 비율을 구한다 |
| 일시와 환경 | 2026-10-07 |
| 입력 | `raw/data_15043409.csv`. 2013-01-01 ~ 2026-02-28 가운데 하루 합계 1kWh 이상인 4,768일 |
| 기대 | 조사의 값(10시 15.8%, 17시 97.6%)과 같다 |
| 실제 | 9시 6.75%, 10시 15.81%, 14시 70.54%, 16시 92.22%, 17시 97.59%, 19시 99.99%, 20시 100.00% |
| 판정 | 통과. 시간 열의 구간은 공식 정의가 없어 추정이다. 발전이 끝나는 시각과 계량 자료를 받는 시각은 다르다 |
| 증빙 | [`data_checks.txt`](data_checks.txt) G |
| 문서에 반영 | ② 의 4절, 결정 기록 0002 |

### V25

**조사 수치의 재현 스크립트가 지금도 같은 값을 낸다**

| 항목 | 내용 |
| --- | --- |
| 주장 | 기획서가 인용한 조사의 재현 스크립트가 지금의 저장소에서 보관된 결과와 같은 값을 낸다 |
| 방법 | `python tools/proposal/rerun_existing_checks.py`. `tools/verify/` 의 스크립트 셋을 다시 돌려 보관된 결과와 견준다. 결과 파일을 스크립트 옆에 쓰는 것은 임시 폴더에서 돌려 보관본을 덮어쓰지 않는다 |
| 일시와 환경 | 2026-10-07 |
| 입력 | `tools/verify/verify_t3t4.py`, `t5_independent_audit.py`, `validate_audit_artifacts.py` 와 그 보관 결과 |
| 기대 | 숫자가 상대 오차 1e-9 안에서 같다 |
| 실제 | `verify_t3t4.py`: 값 331개 가운데 다른 값 0개. `t5_independent_audit.py`: 306개 가운데 0개. 기준선 0.980896, 0.950992. 0.86 주입의 감지 89.19%(주입 직전 기준선), 91.89%(고정 기준선). `validate_audit_artifacts.py`: 오류 0개 |
| 판정 | 통과. 재현한 것은 저장된 자료의 계산이다. 조사의 LSTM 학습을 다시 돌린 것은 아니다 |
| 증빙 | [`existing_checks_rerun.txt`](existing_checks_rerun.txt) |
| 문서에 반영 | 조사의 수치를 인용한 곳마다 "조사"라고 표시하고 조건을 붙였다 |

### V26

**화면 캡처**

| 항목 | 내용 |
| --- | --- |
| 주장 | 기획서의 화면이 떠 있는 서버의 실제 화면이다 |
| 방법 | 서버를 띄우고 `python tools/proposal/capture_screens.py --base http://127.0.0.1:8077 --out docs/proposal/evidence/screens --upload datasets/hadong_upload_forecast_jma.csv`. 헤드리스 Chrome 으로 화면을 열고, 사람이 누르는 단추와 같은 함수를 브라우저 안에서 부른 뒤 보이는 그대로를 저장한다 |
| 일시와 환경 | 2026-10-07 15:47. Chrome 154 |
| 입력 | 대시보드(`/`), API 문서(`/docs`) |
| 기대 | 화면 일곱 장 |
| 실제 | 일곱 장을 저장했다. 대시보드 첫 화면, API 문서 첫 화면, 업로드 뒤("업로드 완료: haic_1791355655.csv (1337행)"), 정상 배치 뒤와 드리프트 배치 뒤(둘 다 "서버 오류 - ... TODO가 아직 구현되지 않았을 수 있습니다", 두 그림이 같다), 로그 패널("(비어 있음)"), `POST /predict` 를 펼친 API 문서 |
| 판정 | 통과. 모두 **지금 상태**의 화면이다. 정상 예측, 버전 전환, 컨테이너, 드리프트 판정, 로그가 쌓인 화면은 **없다** |
| 증빙 | [`01_dashboard_current.png`](screens/01_dashboard_current.png), [`02_swagger_docs_current.png`](screens/02_swagger_docs_current.png), [`03_dashboard_after_upload.png`](screens/03_dashboard_after_upload.png), [`04_dashboard_normal_batch.png`](screens/04_dashboard_normal_batch.png), [`05_dashboard_drift_batch.png`](screens/05_dashboard_drift_batch.png), [`06_dashboard_log_panel.png`](screens/06_dashboard_log_panel.png), [`07_swagger_predict_expanded.png`](screens/07_swagger_predict_expanded.png). 그때의 서버 로그는 [`11_server_capture.log`](logs/11_server_capture.log) |
| 문서에 반영 | ⑥ 의 장면 1, 7, 8, ⑤ 의 1, 8절. 없는 화면은 없다고 적었다 |

### V27

**그림의 색 구분**

| 항목 | 내용 |
| --- | --- |
| 주장 | 그림에서 구분에 쓴 두 색이 색각 이상에서도 갈린다 |
| 방법 | 그림을 만든 작업 도구의 색 검증 스크립트에 두 색을 넣었다. 이 저장소에는 없는 도구다 |
| 일시와 환경 | 2026-10-07 |
| 입력 | 파랑 `#2563eb`, 주황 `#d97706`. 밝은 바탕 |
| 기대 | 다섯 항목 통과 |
| 실제 | 밝기, 채도, 색각 이상에서의 차이, 일반 시각에서의 차이, 바탕과의 대비가 모두 통과 |
| 판정 | 통과 |
| 증빙 | [`palette_check.txt`](palette_check.txt) |
| 문서에 반영 | 그림 여섯 장. 그림마다 막대와 선에 이름을 직접 붙여 색만으로 구분하지 않게 했다 |

### V28

**Mermaid 그림의 문법**

| 항목 | 내용 |
| --- | --- |
| 주장 | 기획서의 Mermaid 그림이 문법에 맞고 그려진다 |
| 방법 | `python tools/proposal/check_mermaid.py`. 문서의 블록을 뽑아 헤드리스 Chrome 에서 Mermaid 11 로 해석하고 그린다. 그린 결과를 그림으로 받아 눈으로 봤다 |
| 일시와 환경 | 2026-10-07. Mermaid 11(CDN) |
| 입력 | ① 의 1개, ④ 의 4개 |
| 기대 | 다섯 블록 모두 통과 |
| 실제 | 다섯 블록 모두 통과. 그린 결과를 그림 파일로 저장해 눈으로 봤다. 전체 구성도는 선이 엇갈려 세 번 고쳐 그렸다 |
| 판정 | 통과. GitHub 가 쓰는 Mermaid 의 판과 다를 수 있다. GitHub 화면에서 한 번 더 본다 |
| 증빙 | [`mermaid_check.txt`](mermaid_check.txt), 그린 결과는 [`mermaid/`](mermaid/) |
| 문서에 반영 | ① 의 4절, ④ 의 1, 3, 4절 |

### V29

**문서의 링크, 표, JSON 예시, 보관 문서의 보존**

| 항목 | 내용 |
| --- | --- |
| 주장 | 문서의 링크가 끊기지 않았고, 표와 JSON 예시가 올바르고, 보관 문서와 서빙 앱을 건드리지 않았다 |
| 방법 | `python tools/proposal/check_docs.py`. 링크의 파일과 위치, 표의 칸 수, JSON 블록, 검증 번호, `docs/research`·`tools/verify`·`tools/jeokryang`·`project` 의 변경을 본다 |
| 일시와 환경 | 2026-10-07 |
| 입력 | `docs/proposal/`, `docs/decisions/`, `docs/followups.md`, `datasets/README.md`, `tools/proposal/README.md` |
| 기대 | 문제 0건. 보관 문서에 변경 없음 |
| 실제 | 문제 0건. 네 폴더에 커밋되지 않은 변경이 없다. 점검한 문서, 링크, 표, JSON 예시의 수는 증빙 파일에 있다. 처음 돌렸을 때는 이 기록이 가리키는 `docs_check.txt` 가 아직 없어 1건이 나왔고, 그 파일이 생긴 뒤 다시 돌려 0건이 됐다 |
| 판정 | 통과. 위치(`#`)의 이름은 GitHub 의 규칙을 흉내 내어 계산했다. GitHub 화면에서 한 번 더 눌러 본다 |
| 증빙 | [`docs_check.txt`](docs_check.txt) |
| 문서에 반영 | 전체 |

### V30

**직접 학습한 모델의 오프라인 평가**

| 항목 | 내용 |
| --- | --- |
| 주장 | 저장소의 학습 코드로 직접 학습한 태양광 모델의 오차와 치우침을 잴 수 있다. 수준 하락이 RMSE 로는 보이지 않는다. 지금 코드의 고정된 둘째 값은 예보를 넣어 학습한 모델에 쓸 수 없다 |
| 방법 | 검증용 사본의 `project/` 에서 `python <저장소>/tools/proposal/offline_model_eval.py`. V12 에서 MLflow 의 실행 기록에 남은 모델(게이트에서 막혀 등록되지 않은 것)을 불러, 같은 스케일러와 실습 코드의 창·분할 함수로 시험 구간을 다시 예측한다. 코드와 자료는 바꾸지 않는다 |
| 일시와 환경 | 2026-10-07 15:50 |
| 입력 | 예보 업로드 파일. 시험 264일(2025-06-09 ~ 2026-02-27). 시드 42 한 번. 시연 배치 2025-06-21 ~ 07-31(대상 07-11 ~ 07-31). 이 모델의 학습 정답일은 2025-06-08 까지다 |
| 기대 | 다시 잰 RMSE 가 MLflow 에 기록된 41.5888 과 같다 |
| 실제 | RMSE 41.59kWh, 합계 오차율 16.6%, 치우침 −6.0%. 예측의 범위 18.6 ~ 305.5kWh, 0 아래는 0건. 달로 나누면 2025-06 에 60.34 대 규칙C 81.81, 아홉 달 가운데 석 달은 규칙C 가 앞선다(2025-11 에 45.59 대 40.20, 2025-12 에 30.17 대 29.64, 2026-01 에 28.78 대 24.48). 시연 배치: 변화 없음 RMSE 45.1kWh(치우침 −8.7%), 발전량 × 0.86 은 34.5kWh(+2.2%), 둘째 값을 1,200,000 으로 고정하면 111.1kWh(예측이 모두 276.4kWh) |
| 판정 | 통과. **서버가 응답한 값이 아니라 오프라인 평가다.** 시드 하나의 결과다 |
| 증빙 | [`offline_model_eval.txt`](offline_model_eval.txt), [`offline_model_eval.json`](offline_model_eval.json) |
| 문서에 반영 | ② 의 6, 7절, ③ 의 4, 5절, ⑥ 의 장면 3, 7, 9, 결정 기록 0002, 0003, 0005, 0006, 0007, 0009 |
