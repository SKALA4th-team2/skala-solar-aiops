# 작업 규칙

SKALA 「모델 서빙 및 AIOps 구성」 과정의 조별 미니 프로젝트 저장소다. 이 문서는 이 저장소에서 작업할 때 지킬 규칙만 담는다. 프로젝트 개요, 진행 현황과 실행 명령은 [`README.md`](README.md)에 있다.

## 이 문서는 두 이름으로 존재한다

`AGENTS.md` 와 `CLAUDE.md` 는 같은 문서다. 도구마다 읽는 파일이 달라 두 이름으로 둔다. 한쪽을 고치면 `cp CLAUDE.md AGENTS.md` 로 다른 쪽을 맞추고 같은 커밋에 넣는다.

## 현행 시간별 계약

결정0014가 과거 일별 계약을 대체한다. 입력·게이트·모니터링 변경은 serving_app/hourly/{schemas,model,policy,worker}.py, tools/hourly/, docs/backend-runbook.md, docs/proposal/5-api-spec.md, docs/design/solar-ops-v01/hourly-ui.js 및 생성된 static과 함께 맞춘다. 아래 스켈레톤 일별 경로 표는 과거 구현 추적용이다.

## 기준 문서

- 평가 기준과 기획서 요건은 통합가이드(`SKALA_AIOps_통합가이드_최종_배포.pdf`)다. 강사 저작물이라 저장소에 넣지 않는다. 요건은 [`docs/proposal/README.md`](docs/proposal/README.md)에 옮겨 적었다.
- 데이터와 설계의 근거는 [`docs/research/`](docs/research/)의 조사 보고서다.
- 팀이 정한 것은 [`docs/decisions/`](docs/decisions/)에, 아직 확인하지 못했거나 미뤄 둔 것은 [`docs/followups.md`](docs/followups.md)에 있다. 추측으로 메우지 않는다.

## 설계, 숫자, 코드는 이어져 있다

같은 숫자와 같은 약속이 문서와 코드 여러 곳에 적힌다. 한 곳만 고치면 발표 자료와 실제 동작이 어긋난다. 아래 묶음 가운데 하나를 고치면 같은 묶음의 나머지를 같은 변경에서 함께 맞춘다.

| 바꾸는 것 | 함께 맞출 곳 |
| --- | --- |
| 배포 게이트 기준 | `docs/decisions/`, `docs/proposal/3-operations-design.md`, `serving_app/train_and_register.py` 의 `RMSE_GATE`, `scripts/train_baseline_v1.py` 의 게이트 문구와 비교값 |
| 드리프트 판정 기준과 창 길이 | `docs/decisions/`, `docs/proposal/3-operations-design.md`, `serving_app/monitoring/drift_detector.py` 의 `RMSE_THRESHOLD` 와 `WINDOW_SIZE`, `serving_app/routers/predict.py` 의 `[-21:]`, `serving_app/static/index.html` 의 `WINDOW_SIZE` 와 `RMSE_THRESHOLD`, `serving_app/monitoring/retrain_trigger.py` 의 로그 문구 |
| 입력의 길이와 뜻 (20일, 두 값) | `docs/proposal/domain-mapping.md`, `datasets/README.md`, `data/features.py` 의 `SEQ_LEN`, `serving_app/schemas.py`, `serving_app/lstm_model.py` |
| 요청과 응답의 모양 | `docs/proposal/5-api-spec.md`, `serving_app/schemas.py`, 해당 라우터, `serving_app/static/index.html`, `scripts/simulate_drift.py` |
| 시뮬레이션 배치를 만드는 방식 | `docs/proposal/6-demo.md`, `scripts/simulate_drift.py`, `serving_app/static/index.html` 의 `DEFAULT_BASE_PRICE`, `serving_app/routers/predict.py` 의 `SIMULATED_VOLUME` |

`retrain_trigger.py` 가 남기는 로그 문장은 대시보드가 읽는다. 글자를 바꾸면 대시보드도 함께 고친다.

### 여러 발전소로 넓힐 때의 묶음

현재 서비스는 시간별 모델을 통과한 31개 발전소를 다룬다. 여러 발전소로 넓히는 설계는 [`docs/proposal/multi-plant-extension.md`](docs/proposal/multi-plant-extension.md)에 있다. 그 작업을 할 때는 아래 묶음도 같은 변경에서 맞춘다.

| 바꾸는 것 | 함께 맞출 곳 |
| --- | --- |
| 발전소 식별자와 등록부 (`plant_id`, 용량과 단위, 유효 기간) | `docs/decisions/0011-*.md`, `docs/proposal/multi-plant-data-contract.md`, `datasets/plants/plants.csv`, `datasets/README.md`, `tools/multi_plant/common.py` 의 열 목록과 `SCHEMA_VERSION`, `data/storage.py` 의 업로드 선택, `serving_app/schemas.py` 의 입력 상한(`MAX_GENERATION_KWH`), `serving_app/routers/data.py` |
| 포트폴리오 구성 (`portfolio_id`, 구성 버전, 설비 용량의 합산) | `docs/decisions/0010-*.md`, `docs/proposal/multi-plant-data-contract.md`, `datasets/plants/portfolio_members.csv`, `tools/multi_plant/portfolio_capacity.py`, `docs/proposal/5-api-spec.md` 의 포트폴리오 응답 |
| 모델과 스케일러의 짝 (모델 이름, 경로, 묶음 기록) | `docs/decisions/0011-*.md`, `serving_app/model_loader.py`, `serving_app/train_and_register.py`, `scripts/train_baseline_v1.py`, `data/features.py` 의 `HAICScaler` 기본 경로, `tools/multi_plant/bundle_check.py` 의 `FEATURE_SCHEMA` 와 `model_name_for` |
| 발전소별과 합계의 평가 지표 | `docs/decisions/0011-*.md`, `docs/proposal/2-solution-and-goals.md`, `docs/proposal/multi-plant-extension.md`, `tools/multi_plant/evaluate.py` |
| 재학습 작업과 실행 단위 (작업 기록, 한도, 로컬과 컨테이너의 경로) | `docs/decisions/0012-*.md`, `docs/proposal/single-pc-operation.md`, `docs/proposal/4-architecture.md`, `serving_app/monitoring/retrain_trigger.py`, `serving_app/docker-compose.yml`, `serving_app/Dockerfile` |
| 로그 문장에 싣는 식별자 (`plant=`, `model=`, `data=`, `job=`) | `docs/decisions/0007-*.md`, `docs/proposal/3-operations-design.md`, `docs/proposal/6-demo.md`, `serving_app/monitoring/retrain_trigger.py`, `serving_app/static/index.html` 의 로그 패널 안내문 |

제도의 기준은 "주요자원(태양광·풍력) 설비 용량 합계 20MW 초과"라고 쓴다. "이상"이라고 쓰지 않고, 발전량의 기준으로 읽히게 쓰지 않는다.

## `project/` 는 폴더 구조를 바꾸지 않는다

`project/` 는 강사가 배포한 HAIC 스켈레톤에서 출발한다. 안의 파일을 옮기거나 폴더 이름을 바꾸지 않는다. 교재의 명령, Docker 빌드, 트러블슈팅 안내가 이 구조를 전제로 한다. 내용은 태양광 도메인에 맞게 고친다.

- 모든 명령은 `project/` 에서 실행한다. `serving_app/` 안에서 실행하면 import 경로가 어긋난다.
- 가상환경은 `project/.venv` 에 Python 3.11 로 만든다.
- 로컬 서버는 8077, 컨테이너는 8099 포트를 쓴다. `scripts/simulate_drift.py` 는 `--target local|container|both` 로 보낼 곳을 고른다.
- 스케일러(`scaler.pkl`)는 태양광 데이터를 올린 뒤 `scripts/train_baseline_v1.py` 로 한 번 만든다. 그 뒤 재학습에서는 다시 맞추지 않는다. 가중치가 그 기준으로 학습돼 있어서, 다시 맞추면 에러 없이 예측만 틀어진다. 업로드 파일의 종류를 바꿔 두 번째 입력의 뜻이 달라지면 스케일러와 모델을 함께 다시 만든다.
- 문서, 데이터 원본, 도구는 `project/` 안에 두지 않는다. 각각 `docs/`, `datasets/`, `tools/` 에 둔다.
- `routers/data.py`, `routers/logs.py`, `static/index.html` 은 완성형으로 받은 배관 코드다. 도메인 문구나 단위 때문에 고쳐야 하면 고치되, 위 표의 묶음을 함께 맞춘다.
- 스켈레톤의 빈칸 11곳(`___`)은 HAIC 실습의 정답 그대로 먼저 채운다. 태양광용 수정은 그 뒤의 변경으로 나눈다.

## 수치

- **우리가 직접 실행해 얻은 값만 결과로 적는다.** 교재의 예시 수치나 조사 보고서의 수치를 우리 시연 결과 자리에 옮겨 적지 않는다.
- 조사 보고서의 수치를 근거로 인용할 때는 출처와 조건(기간, 분할 방식, 시드 수)을 함께 적는다.
- 예측 시점에 받을 수 없는 값을 입력에 쓴 결과는 쓸 때마다 그렇게 표시한다. 예를 들어 예측 대상일의 실제 관측 날씨를 넣은 결과는 "예보가 완벽하다고 가정한 상한"이다.
- 지표에는 단위를 붙인다(하루 kWh, %). HAIC 코드에 남아 있는 달러 표기는 고칠 때 함께 바꾼다.
- 수치에는 그것이 무엇의 값인지를 같은 문장에 적는다. 설비 용량(kW, MW)은 기간이 붙지 않는 값이고 발전량(kWh, MWh)은 기간이 붙는 값이다. "20MW 초과"가 아니라 "설비 용량 합계 20MW 초과"라고 쓴다.
- 포트폴리오의 오차는 예측의 합과 실제의 합으로 구한다. 발전소별 RMSE 를 더한 값을 포트폴리오의 RMSE 라고 쓰지 않는다. 구성원이 빠진 합을 합계라고 쓰지 않는다.
- 합성 자료, 복제한 자료, 용량을 배로 늘린 자료의 수치는 기능 확인과 부하 시험에만 쓴다. 예측 성능이나 제도 요건의 근거로 쓰지 않는다.
- 하루 합계를 24칸으로 나눈 값으로 제도의 정산용 성능을 말하지 않는다.

## 데이터

- `datasets/` 의 파일은 손으로 고치지 않는다. 만드는 스크립트를 `tools/` 에 두고 다시 만든다. 발전소 등록부와 포트폴리오 구성(`datasets/plants/*.csv`)은 사람이 적는 파일이다. 적은 뒤에 `python tools/multi_plant/validate.py --data-root datasets/plants` 로 검증한다.
- 결측을 0 으로 채우지 않는다. 모르는 용량, 위치, 시각은 칸을 비운다. 서로 다른 발전소의 행을 이어 붙여 창을 만들지 않는다.
- 여러 발전소의 정규화 실적(`datasets/plants/generation/`)은 원자료에서 다시 만들 수 있으므로 커밋하지 않는다.
- 파일마다 출처, 이용 조건, 열의 뜻, 만든 방법을 [`datasets/README.md`](datasets/README.md)에 적는다.
- API 키가 필요한 자료는 각자 `.env` 에 키를 넣어 받는다. `.env` 는 커밋하지 않는다. 에이전트는 키를 입력하거나 화면에 출력하지 않는다.

## 문서

- 기획서는 [`docs/proposal/`](docs/proposal/)에 항목별 파일로 쓴다. 여섯 항목은 앞 항목의 결과가 다음 항목의 근거가 되도록 이어져야 한다.
- 현재 구현된 다개소 시간별 기능은 제출용 여섯 항목에 반영한다. 과거 확장 제안은 보관 원문으로 분리한다. [`multi-plant-extension.md`](docs/proposal/multi-plant-extension.md), [`multi-plant-data-contract.md`](docs/proposal/multi-plant-data-contract.md), [`single-pc-operation.md`](docs/proposal/single-pc-operation.md)에 쓰고, 현행 여섯 항목과 구현·증빙을 맞춘다. 지금의 구현, 제안하는 설계, 직접 돌린 결과를 표기로 가른다.
- 팀이 정한 것은 [`docs/decisions/`](docs/decisions/)에 한 건씩 남긴다. 기획서 ③ 의 숫자는 결정 기록을 근거로 가리킨다.
- [`docs/research/`](docs/research/)의 보고서는 보관 자료다. 고치지 않는다. 판단이 바뀌면 결정 기록에 적는다.
- 증빙 캡처와 로그는 `docs/proposal/evidence/` 에 둔다. 서버를 내리기 전에 먼저 남긴다.
- 트러블슈팅은 "오류 메시지 → 원인 → 해결 명령 → 해결 전후 결과" 형식으로 쓴다.

## Git

- 커밋은 `type(scope): 요약` 형식으로 쓴다. type 은 `feat` `fix` `docs` `chore` `refactor` `test`, scope 는 `serving` `mlops` `aiops` `data` `proposal` `docs` 등이다.
- 스켈레톤 원본은 첫 커밋에 그대로 있다. 태양광용 수정은 그 위의 변경 내역으로 남긴다.
- 팀 합의(결정0016)에 따라 승인된 배포용 `project/serving_app/models/hourly-seed/`의 모델 31개, 고정 스케일러, manifest, 등록부와 재생용 이력만 커밋한다. 모델·스케일러·manifest는 한 묶음으로 SHA와 승인 게이트를 검증한다. 재학습 중 생성되는 모델, MLflow 기록, 운영 DB, 로그, 업로드, API 키는 계속 제외한다. seed 갱신은 팀 검토 후 수행하며 실행 중 모델을 자동 커밋하지 않는다.
- 원격 저장소는 비공개로 만든다. 강사가 배포한 스켈레톤 코드가 들어 있고, 학습 목적으로만 쓰라는 조건이 붙어 있다.
- 작업 흐름은 [`CONTRIBUTING.md`](CONTRIBUTING.md)에 있다.

## 범위 밖

- MLflow 서버, Prometheus·Grafana, Kubernetes 는 교재의 실습 범위가 아니다. MLflow 는 로컬 sqlite, 컨테이너는 단일 컨테이너다. 여러 발전소로 넓혀도 같다. FastAPI, 학습, MLflow, AIOps 를 PC 한 대에서 돌리고 메시지 브로커를 들이지 않는다. 재학습 모델의 외부 보관(R2)은 결정0017의, 보관한 버전의 로컬 사본 정리는 결정0018의 선택 기능이고 기본 실행은 쓰지 않는다. 운영 DB 와 MLflow 기록은 계속 로컬에 둔다.
- 시간대별 예측은 사용자 요청으로 결정0014에서 구현 범위에 포함했다. 전력거래소 실제 제출과 지급액 확정은 범위 밖이다. 결정0015의 명시적 가정에 따른 인센티브 참고 지표·모의 금액 계산은 구현 범위다. 여러 발전소의 자료를 모아도 제도의 참여 요건을 채웠다고 쓰지 않는다.
- 개인 서브노트와 개인 실습은 각자의 폴더에 둔다. 이 저장소에 넣지 않는다.
