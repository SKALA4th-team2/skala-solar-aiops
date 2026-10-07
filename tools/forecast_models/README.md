# 새 지역 예보 기반 모델

GitHub `main`의 `9ad93b1571c8300f3e26d00837cba338a94987c4`에서 README, FastAPI 인수인계, 입력 결정 기록, 모델 로더와 라우터를 확인하고 만든 학습 도구다. 원격 소스는 증빙의 `github_snapshot/`에 보관했다. 작업 중인 로컬 브랜치를 원격으로 덮어쓰지는 않았다.

새 `datasets/plant_forecasts/`의 JMA MSM `previous_day1` 일사량 예보를 사용한다. 이전 `multi_plant_models/`의 ASOS 관측 기반 모델과 입력의 의미가 달라 모델과 스케일러를 모두 새로 학습한다. 결과와 사용상의 제한은 [모델 인수인계](../../docs/forecast-model-handoff.md)를 참고한다.

## 파일과 역할

- `train.py`: 날짜 연속성 검사, 사전 제외, 검증 구간에서 설정 선택, 평가용/최신용 각각 세 모델 학습과 저장·재로딩 검사.
- `bundle.py`: `ForecastModel(directory)`; `.predict_one(sequence)`, `.version`, `.source`를 제공하는 LSTM 어댑터.
- `predict.py`: 저장된 LSTM, XGBoost, Prophet, 앙상블을 실제 입력으로 실행하는 CLI.
- `register.py`: 짝지은 스케일러를 포함한 native TensorFlow MLflow 등록과 재로딩 비교.
- `register_completed.py`: 이번 학습이 끝나는 호기부터 순차 등록하는 실행 도구.
- `audit.py`: 원본 날짜 조회로 입력·정답 정렬, 학습 전용 스케일러, 지표, 앙상블, 해시를 별도로 재검사.
- `verify_registry.py`: 실제 MLflow DB의 버전·별칭·native flavor와 저장된 스케일러/metadata 파일의 일치를 검사.
- `verify_causality.py`: 임시 데이터 사본의 미래값을 바꿔 이전 시점 입력이 바뀌지 않는지 검사.
- `verify_api.py`: 보관한 최신 GitHub API를 실제 모델로 단건·배치·헬스 검사하고 임시 가중치에서 한 번의 추가 학습을 검사.
- `install_local.py`: 선택한 모델/스케일러를 기존 로컬 앱 경로에 복사. 기존 파일이 있으면 증빙 폴더에 백업한다.

모든 명령은 `project/`에서 실행한다. Windows의 TensorFlow DLL 충돌을 피하도록 실행 스크립트는 TensorFlow를 NumPy/MLflow보다 먼저 import한다.

2026-10-07 최신 main 설치 후 이 PC의 `.venv`는 저장소 requirements 전용 환경이다. 기존 실험 패키지는 `.venv-models-20261007`에 보존했다. **아래 학습·비교 명령을 기존 실험 환경에서 재실행할 때는 `.venv/Scripts/python.exe` 대신 `.venv-models-20261007/Scripts/python.exe`를 사용한다.** 보존 환경의 실행은 해당 Python 경로를 직접 사용하며, 이동 전 경로가 들어 있을 수 있는 활성화 스크립트나 pip.exe를 사용하지 않는다.

```powershell
# 저장된 하동 모델로 예측. --input 생략 시 저장된 20일 입력 예시 사용
.venv/Scripts/python.exe -X utf8 -B ../tools/forecast_models/predict.py
.venv/Scripts/python.exe -X utf8 -B ../tools/forecast_models/predict.py --plant 15043409_u1 --model selected
.venv/Scripts/python.exe -X utf8 -B ../tools/forecast_models/predict.py --plant 15043409_u1 --role release --model LSTM --input request.json

# 중단된 동일 실행 재개: 완료된 result.json은 건너뜀
.venv/Scripts/python.exe -X utf8 -B ../tools/forecast_models/train.py --workers 3
.venv/Scripts/python.exe -X utf8 -B ../tools/forecast_models/register.py

# 전체 완료 후 검증
.venv/Scripts/python.exe -X utf8 -B ../tools/forecast_models/audit.py --registry
.venv/Scripts/python.exe -X utf8 -B ../tools/forecast_models/verify_registry.py
.venv/Scripts/python.exe -X utf8 -B ../tools/forecast_models/verify_causality.py
.venv/Scripts/python.exe -X utf8 -B ../tools/forecast_models/verify_api.py

# 기존 앱의 기본 경로에 하동 2025년 재생용 모델 설치
.venv/Scripts/python.exe -X utf8 -B ../tools/forecast_models/install_local.py --plant 15043409_u1 --role evaluation
```

기본 출력은 `docs/proposal/evidence/forecast_models_20261007/`이다. 다른 데이터나 코드를 새로 실험할 때는 **새 출력 폴더**를 사용하고, 그 폴더에 검토한 `github_review.json`과 `github_snapshot/main/project/`를 먼저 준비해야 한다. 실행 중 학습 코드와 원본 자료를 바꾸지 않는다. `source_snapshot/`과 해시 검사가 변경을 검출한다.

Python 3.11.9와 실제 패키지 버전은 결과의 `environment.json`을 기준으로 한다. 이번 실행은 TensorFlow 2.21.0 / Keras 3.14.1, NumPy 1.26.4, pandas 2.0.3, XGBoost 3.2.0, Prophet 1.5.0, MLflow skinny 3.17.0이다. 프로젝트의 기존 requirements 전체를 이번 모델 환경으로 바꾸지 않았다.

## 학습과 비교

입력은 연속 20일의 `(발전량[d], 다음날 일사량예보[d+1])`, 정답은 다음 날 하루 발전량이다. 원본의 `target_date`는 예보 **대상일**이므로 한 번만 정렬한다. 결측·무효 발전량을 보간하지 않고 해당 날짜를 포함하는 창을 제외한다. 유효 발전량 0은 허용한다.

- 학습: 2024-07-01 이전, 검증: 2024-07~12, 시험: 2025-01~12.
- 사전 조건: 학습 365일 이상, 검증 90일 이상, 시험 240일 이상, 정답 0 비율 25% 이하. 원본 `review_only`/`raw_only_not_daily_training`은 제외.
- LSTM: 수업 모델 32→32→16→Dense16→1, 시드 42, 최대 120 epoch 중 검증 손실 최저 epoch 선택. 개소마다 시드 한 번이다.
- XGBoost: 깊이 2/3/5 × 학습률 .03/.08의 6개 설정. Prophet: changepoint prior .01/.05/.2의 3개 설정.
- 앙상블: 세 모델의 비음수 합계 1 가중치를 검증에서 선택. 일반 앙상블과 LSTM 비중 50% 이상 앙상블을 모두 저장.
- 설정과 가중치를 먼저 동결하고 학습+검증 구간에서 평가 모델을 다시 학습한 뒤 시험한다. 시험 결과를 보고 설정을 다시 고르지 않는다.
- 이후 동결된 설정으로 전체 유효 데이터를 다시 학습해 최신용을 별도로 저장한다. 최신용에 과거 시험 성능을 새 성능처럼 붙이지 않는다.

세 모델과 Persistence/Mean7/예보 RuleC를 동일 날짜에서 비교한다. LSTM이 모든 개소에서 반드시 가장 좋다고 가정하지 않는다. 교수님 요구와 기존 인터페이스에 맞춰 주 서빙 모델은 LSTM으로 유지하고, 비교 결과와 앙상블도 남긴다.

모델 파일과 MLflow DB/아티팩트는 Git에서 제외된다. 다른 팀원에게 전달할 때는 `plants/<ID>/<role>/` 전체 묶음을 파일 저장소 등으로 별도 전달한다. `.keras`만 전달하면 스케일러와 입력 정의를 잃는다.
