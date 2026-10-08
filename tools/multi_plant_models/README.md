# 발전소별 모델 후보

추가 ASOS 자료를 발전소·호기별로 학습하고, 저장 파일과 MLflow 버전에서 예측을 재현한다. 기존 하동 예보 기반 실험은 `tools/model_benchmark/`에 별도로 보존한다. 기존 서빙 앱의 모델 이름·게이트는 변경하지 않는다.

모든 명령은 `project/`에서 실행한다.

```powershell
.\.venv\Scripts\python.exe -m pip install -r ../tools/multi_plant_models/requirements.txt
.\.venv\Scripts\python.exe -X utf8 -B ../tools/multi_plant_models/run.py
.\.venv\Scripts\python.exe -X utf8 -B ../tools/multi_plant_models/register.py
.\.venv\Scripts\python.exe -X utf8 -B ../tools/multi_plant_models/check_causality.py
.\.venv\Scripts\python.exe -X utf8 -B ../tools/multi_plant_models/audit.py --require-registry
```

`--out docs/proposal/evidence/<새실험명>`으로 새 실행을 분리한다. 같은 출력 경로로 다시 실행하면 완료된 호기는 건너뛴다. 입력·코드·설정을 바꾸었다면 반드시 새 경로를 쓴다. 기본 학습은 프로세스 2개이며 `--workers 1`로 줄일 수 있다. 모델 아티팩트와 MLflow DB는 Git에서 제외한다. 필요한 패키지 버전은 결과의 `environment.json` 및 `requirements-freeze.txt`에 남긴다.

실행 시 학습 소스 원문과 해시를 `source_snapshot/`, `training_code_hashes.json`에 보존하고, 학습 중 코드가 바뀌지 않았는지 확인한다. 최초 2026-10-07 실행은 같은 절차를 수동으로 수행했고, 완료 후 이 자동 보존 절차를 실행 도구에 추가했다. 최초 실행의 실제 학습 코드는 해당 결과 폴더의 스냅샷이다.

## 데이터와 평가

- 카탈로그의 원본 해시, 연속 날짜, 발전량, 일사량 시차를 확인한다. 1,115일 이상 연속되고 2025년 이후 끝나는 가장 최근 구간만 선택한다. 최대 최근 1,480행을 사용한다. 제외 목록은 `screening.json`에 남긴다.
- 입력은 `Close[d] = 발전량[d]`, `Volume[d] = ASOS 관측 일사량[d-1]`이다. 20일 입력창으로 T를 예측하면 마지막 날씨는 T-2이다. 예보나 T일 관측값으로 해석하면 안 된다.
- 마지막 365일 시험, 이전 180일 검증, 나머지 학습이다. 날짜 경계를 넘어 누락 구간을 이어 붙이지 않는다. 시험 기간은 매일 실제 T-1 이력으로 다음 날을 예측하며 모델 가중치는 고정한다.
- LSTM은 기존 수업 구조, 시드42, Adam .001, 120 epoch에서 검증 손실 최소 epoch를 선택한다. XGBoost 6설정, Prophet 3설정을 비교한다. LSTM은 다개소 1차 검증이므로 이전 하동의 3시드 평균과 실험 강도가 다르다.
- 모델별 설정과 앙상블 비중을 검증 구간에서 고정한 후 학습+검증으로 재학습한다. 스케일러도 그 구간에서만 맞추고 모델과 함께 저장한다. 시험 점수로 모델·비중을 다시 선택하거나 성능이 낮은 호기를 제외하지 않는다.
- 단순 기준모델 3종도 비교한다. MLflow에는 개별 모델 3종과 앙상블 2종을 각각 `candidate`로 등록한다. LSTM을 강제로 성능 1위로 표시하거나 Production으로 승격하지 않는다.

## 재사용

각 호기 `models/`에는 `lstm.keras`, `xgboost.ubj`, `prophet.json`, `scaler.json`, `metadata.json`이 있다. 마지막 파일에 발전소 ID·입력 정의·특성 순서·앙상블 비중·학습 기간·출처 해시·성능을 기록한다. 이 폴더를 하나의 묶음으로 다룬다. 다른 호기/날씨 정의의 스케일러와 섞지 않는다.

`bundle.Bundle(모델폴더, 모델종류).predict(frame)` 또는 MLflow `models:/Solar_<plant_id>_<kind>/<version>`으로 불러온다. MLflow 접속 URI는 `registry_index.json`에 있다. 예시 입력은 호기별 `input_example.csv`이며, `target_date` 다음에 오래된 날부터 `close_0, volume_0, ... close_19, volume_19`를 넣는다. 호출자는 값의 실제 날짜가 T-20..T-1임을 보장해야 한다. 날짜가 포함된 원시 이력에서 요청을 만드는 서빙 계층은 별도로 연결해야 한다.

Windows 환경에서 TensorFlow를 NumPy보다 먼저 import하고 `TF_ENABLE_ONEDNN_OPTS=0`을 사용한다. 실행 스크립트는 이를 적용한다.

저장된 역사적 예시 입력을 MLflow 버전으로 예측하는 명령:

```powershell
.\.venv\Scripts\python.exe -X utf8 -B ../tools/multi_plant_models/predict.py --plant 15043406_u1 --kind LSTM --registry
```

`--input <CSV>`를 지정하면 예시 대신 새 요청 파일을 읽는다. `input_example.csv`와 같은 열 순서와 입력의 날씨 시차를 지켜야 한다. `--registry`를 빼면 원래 저장 폴더에서 읽는다. MLflow는 로컬 SQLite·로컬 아티팩트 경로를 쓰므로 다른 컴퓨터로 옮길 때 경로를 재등록해야 한다.

저장 모델은 시험 이전까지 학습한 평가 후보이다. 최신 전체 데이터로 운영 모델을 다시 학습하거나 FastAPI 발전소별 라우팅·자동 재학습·캐시 교체를 연결한 상태는 아니다. 배포 기준은 기존 운영 설계와 함께 별도로 확정해야 한다.
