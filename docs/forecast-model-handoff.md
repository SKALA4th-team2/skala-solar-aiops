> **2026-10-07 시간별 전환 — 현행:** 현재 운영은 시간별31개소 LSTM. 이번 학습·검증 코드는 tools/hourly/, 증빙 hourly_20261007이다. 아래 XGBoost·Prophet·LSTM·앙상블 비교는 일별 과거 실험이다. [운영 안내](backend-runbook.md) · [결정0014](decisions/0014-hourly-forecast-and-aiops.md). 이하 이전 계약·수치는 설계/검증 이력이며 현행 시간별 계약보다 우선하지 않는다.

# 예보 모델 → AIOps 인수인계

> **최신 정리:** 사용자 요청으로 성능 미달 6개·용량 미확인 4개를 운영 목록, 학습 입력과 운영 모델에서 제거했다. 현재 승인된 33개만 서비스한다. 추가 승인에 따라 해당 개소의 과거 모델 사본·실험 증빙 1,289개 파일도 삭제했다. 정상 개소와 공유하는 원자료는 유지한다. 아래 43개/보류 10개 수치는 이전 검증 이력이다.

> 2026-10-07 백엔드 통합 후속: 아래는 통합 이전의 인수인계 기록이다. 현재 다개소 서빙·AIOps 연결 상태와 실행법은 [백엔드 안내](backend-runbook.md), 적용 정책은 [0013](decisions/0013-backend-aiops-implementation.md)을 따른다. 아래의 미연결/단일 발전소 설명은 이전 상태이며, 프론트는 변경하지 않았다.

2026-10-07에 최신 GitHub `main`의 README, `docs/fastapi-handoff.md`, 입력 결정 기록과 실제 API 코드를 검토했다. 기준 커밋은 `9ad93b1571c8300f3e26d00837cba338a94987c4`다. 프론트의 `feat/solar-ops-frontend`도 별도로 확인했으며 그 브랜치의 이전 백엔드 코드를 최신 계약으로 취급하지 않았다.

이번 작업은 새 지역별 예보 자료로 **AIOps가 불러올 모델을 만드는 작업**이다. CSV 업로드 자체는 학습이나 모델 생성이 아니다. 예전 ASOS 관측 기반 모델과 이번 JMA MSM 예보 모델은 별도다.

## 완료 확인

43개 호기 모두 학습에 성공했다. 평가용/최신용 각각 LSTM·XGBoost·Prophet을 저장해 개별 모델 파일 258개와 스케일러 86개가 있다. LSTM은 MLflow에 43개 이름, 총 86개 버전으로 등록했다. 전체 원본·지표·파일 검증, 실제 레지스트리 버전·별칭·짝지은 파일 검증을 통과했다. 결과는 [성능표](proposal/evidence/forecast_models_20261007/report.txt), [전체 검증](proposal/evidence/forecast_models_20261007/independent_audit.json), [레지스트리 검증](proposal/evidence/forecast_models_20261007/registry_audit.json)에 있다.

2025년 시험에서 LSTM은 43개 모두 7일 평균보다 RMSE가 낮았고, 예보 기반 RuleC보다 낮은 호기는 31개였다. 검증 구간에서 선택된 모델은 앙상블 42개, XGBoost 1개다. 이는 시험 구간의 우승 모델 수가 아니다. 하동 시험 RMSE는 LSTM 41.13, XGBoost 43.04, Prophet 44.38, 일반 앙상블 42.03 kWh/일이다. 교수님 요구에 맞춰 기본 서빙 모델은 LSTM으로 두고 비교 결과도 함께 보존했다.

## 결과 위치

결과 루트: `docs/proposal/evidence/forecast_models_20261007/`.

| 파일/폴더 | 내용 |
| --- | --- |
| `report.txt`, `all_metrics.csv` | 전체 완료 후의 개소별 시험 성능과 비교 결과 |
| `screening.json`, `protocol.json` | 학습 대상 43개 호기, 사전 제외 6개 매핑 항목과 검증 절차 |
| `plants/<plant_id>/evaluation/` | 2024-12-31까지 학습한 2025년 재생·시연용 묶음 |
| `plants/<plant_id>/release/` | 최대 2026-02-28까지 재학습한 최신 데이터용 묶음 |
| `plants/<plant_id>/result.json` | 해당 호기 학습과 양쪽 묶음의 재로딩이 완료되었음을 나타내는 결과 |
| `registry_index.json` | 실제 MLflow 등록 버전, 별칭, 로컬 추적 DB URI |
| `independent_audit.json` | 전체 완료 후 원본·스케일러·지표·해시·등록 목록 검증 |
| `github_api_integration.json` | 최신 API 코드에 실제 하동 모델을 연결한 단건·21개 배치 예측 검사 |

각 묶음에 `model.keras`(LSTM), `scaler.pkl`(수업 HAICScaler의 저장 형식), `scaler.json`, `xgboost.ubj`, `prophet.json`, `metadata.json`, `bundle_hashes.json`이 있다. 앙상블은 세 모델과 metadata의 `ensemble_weights`로 구성한다. `.pkl` 확장자 하나로 모든 모델을 통일할 필요는 없다.

**모델과 스케일러는 같은 묶음을 사용한다.** 이어서 학습할 때는 기존 스케일러를 다시 fit하지 않는다. 다른 입력 의미나 전체 재학습으로 새 기준을 만들 때는 모델과 스케일러를 한 버전으로 함께 만든다.

## 입력과 호출

예측 대상일이 T이면 연속 20일 T−20부터 T−1까지를 오래된 순서로 보낸다. 각 행은 아래 의미다.

```json
{"date": "2024-12-31", "close": 200.0, "volume": 11.5}
```

여기서 `close`는 12월 31일 발전량(kWh), `volume`은 **1월 1일 대상 일사량 예보**(MJ/m²)다. 요청 최상위는 `{"sequence": [20개 행]}`. 모델에 T의 실제 발전량이나 T의 관측 일사량을 넣지 않는다. 소수 예보와 발전량 0을 허용한다.

각 호기의 `evaluation_request.json`, `release_request.json`은 실제 자료에서 생성한 호출 예시다. 기본 하동 ID는 `15043409_u1`이다. [실행 명령](../tools/forecast_models/README.md)의 `predict.py`는 어느 호기든 원 단위 입력을 받아 kWh 예측을 반환한다.

프로그램에서는 `tools/forecast_models/bundle.py`의 `ForecastModel(묶음_폴더)`를 사용하면 된다. `predict_one(sequence)`, `version`, `source` 인터페이스가 최신 API의 `get_model()` 반환 계약에 맞는다. TensorFlow를 먼저 import하고 모델은 프로세스에서 한 번 로드하여 재사용한다. XGBoost/Prophet/앙상블 실행은 `predict.py`를 참고한다.

## MLflow

추적 저장소는 결과 루트의 `mlflow/mlflow.db`인 로컬 SQLite다. 이름은 `SolarForecast_<plant_id>_LSTM`, 평가용 별칭은 `replay`, 최신용 별칭은 `candidate`다. 각 버전은 **native TensorFlow flavor**로 등록해 `mlflow.tensorflow.load_model()`로 다시 읽고 예측 일치를 검사했다. 스케일러와 metadata는 모델 아티팩트의 `extra_files/`에 함께 있다.

native MLflow 모델은 **스케일된 20×2 입력 → 스케일된 발전량 출력**이다. raw kWh를 그대로 넘기면 안 된다. 같은 버전의 `extra_files/scaler.pkl`로 변환·역변환하고 최종 발전량을 0 이상으로 제한한다. 로컬 `ForecastModel`은 이 과정을 처리한다.

이름이 기존 `HAIC_Predictor`와 다르므로 기존 MLflow 환경변수만 켠다고 새 모델이 자동으로 선택되지는 않는다. 실제 등록 목록의 `model_uri`와 짝지은 스케일러를 로더에 연결해야 한다. Production 승격은 하지 않았다.

## 확인한 연결과 남은 연결

하동 평가용 LSTM과 스케일러는 기존 로컬 경로 `project/serving_app/models/haic_v1.keras`, `scaler.pkl`에 설치했다. `forecast_manifest.json`에는 실제 버전·기간·입력 의미가 들어 있다. 서버 재시작이나 실행 중 캐시 교체는 하지 않았다.

최신 GitHub API 소스를 별도 보관한 상태에서 TestClient로 실제 가중치의 단건·배치·헬스, 기존 HAICScaler 재로딩을 검사했다. 이어서 학습 가능한지는 임시 모델에서 한 번의 가중치 업데이트로 확인했다. 자동 재학습 전체 파이프라인을 시험한 것은 아니다. 로컬의 다른 작업 내용을 보호하기 위해 원격 API 코드를 현재 브랜치에 일괄 덮어쓰지 않았다.

검증 실행 환경의 정확한 버전은 `environment.json`에 있다. 최신 GitHub와 TensorFlow 2.21.0은 같지만 NumPy/MLflow/FastAPI의 일부 버전은 다르며, 그 requirements를 새 컨테이너에 설치한 시험은 하지 않았다. 검토한 Dockerfile은 빌드 중 `sample_haic_prices.csv`로 모델을 다시 학습하고 `MODEL_SOURCE=mlflow`를 사용한다. 따라서 이번 파일을 복사한 뒤 그 Dockerfile을 그대로 빌드하면 새 예보 모델의 배포가 되지 않는다. 배포 담당자는 샘플 학습 단계를 모델 묶음 주입으로 바꾸고 원하는 로더·MLflow URI를 연결해야 한다.

현재 최신 API는 plant_id가 없고 발전량 상한이 1320kWh이므로 모든 대규모 발전소를 같은 HTTP 요청 스키마로 즉시 받지는 못한다. **43개 호기의 모델 생성과 다개소 API 완성은 다른 단계다.** 개소 선택·개소별 상한, 모델 버전별 캐시, AIOps `configure_evaluator` 연결, 재학습 승격과 롤백 정책은 후속 연결 대상이다. 하동 API 검사에서도 드리프트 판정은 `aiops_not_configured`로 건너뛴다.

2025년 정답을 흘려보내는 시연에는 evaluation/replay를 사용한다. release/candidate는 이미 그 기간을 학습했으므로 과거 시험 성능 입증에 사용하지 않는다. 기존 주가 실습의 달러 RMSE 기준을 태양광 자동 승격 기준으로 그대로 사용하지 않는다.

## 해석의 한계

`previous_day1`은 대상 시간별 24시간 전 예보를 모은 자료다. 모든 시간대 값이 특정 전일 20시에 발표·가용했는지는 확인되지 않아 `publication_cutoff_verified=false`로 남겼다. 지역 대표 좌표를 공유하므로 발전소 정확한 좌표의 기상은 아니다. 하루 발전량 평가이며 전력시장 시간별 정산·인센티브 충족을 입증하지 않는다.

실험은 개소별 LSTM 시드 42 한 번, 고정 2025년 시험 구간이다. 다른 기간의 과거 실험 숫자와 직접 우열을 주장하지 않는다. 성능이 낮다는 이유로 시험 결과를 보고 호기를 빼지 않는다. 사전 품질·자료량 기준과 실제 제외 사유는 screening에 남긴다.
