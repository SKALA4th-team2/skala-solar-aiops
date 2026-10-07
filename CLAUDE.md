# 작업 규칙

SKALA 「모델 서빙 및 AIOps 구성」 과정의 조별 미니 프로젝트 저장소다. 이 문서는 이 저장소에서 작업할 때 지킬 규칙만 담는다. 프로젝트 개요, 진행 현황과 실행 명령은 [`README.md`](README.md)에 있다.

## 이 문서는 두 이름으로 존재한다

`AGENTS.md` 와 `CLAUDE.md` 는 같은 문서다. 도구마다 읽는 파일이 달라 두 이름으로 둔다. 한쪽을 고치면 `cp CLAUDE.md AGENTS.md` 로 다른 쪽을 맞추고 같은 커밋에 넣는다.

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

## 데이터

- `datasets/` 의 파일은 손으로 고치지 않는다. 만드는 스크립트를 `tools/` 에 두고 다시 만든다.
- 파일마다 출처, 이용 조건, 열의 뜻, 만든 방법을 [`datasets/README.md`](datasets/README.md)에 적는다.
- API 키가 필요한 자료는 각자 `.env` 에 키를 넣어 받는다. `.env` 는 커밋하지 않는다. 에이전트는 키를 입력하거나 화면에 출력하지 않는다.

## 문서

- 기획서는 [`docs/proposal/`](docs/proposal/)에 항목별 파일로 쓴다. 여섯 항목은 앞 항목의 결과가 다음 항목의 근거가 되도록 이어져야 한다.
- 팀이 정한 것은 [`docs/decisions/`](docs/decisions/)에 한 건씩 남긴다. 기획서 ③ 의 숫자는 결정 기록을 근거로 가리킨다.
- [`docs/research/`](docs/research/)의 보고서는 보관 자료다. 고치지 않는다. 판단이 바뀌면 결정 기록에 적는다.
- 증빙 캡처와 로그는 `docs/proposal/evidence/` 에 둔다. 서버를 내리기 전에 먼저 남긴다.
- 트러블슈팅은 "오류 메시지 → 원인 → 해결 명령 → 해결 전후 결과" 형식으로 쓴다.

## Git

- 커밋은 `type(scope): 요약` 형식으로 쓴다. type 은 `feat` `fix` `docs` `chore` `refactor` `test`, scope 는 `serving` `mlops` `aiops` `data` `proposal` `docs` 등이다.
- 스켈레톤 원본은 첫 커밋에 그대로 있다. 태양광용 수정은 그 위의 변경 내역으로 남긴다.
- 모델 파일, MLflow 기록, 로그, 업로드 파일은 커밋하지 않는다. `.gitignore` 가 막는다.
- 원격 저장소는 비공개로 만든다. 강사가 배포한 스켈레톤 코드가 들어 있고, 학습 목적으로만 쓰라는 조건이 붙어 있다.
- 작업 흐름은 [`CONTRIBUTING.md`](CONTRIBUTING.md)에 있다.

## 범위 밖

- MLflow 서버, Prometheus·Grafana, Kubernetes 는 교재의 실습 범위가 아니다. MLflow 는 로컬 sqlite, 컨테이너는 단일 컨테이너다.
- 개인 서브노트와 개인 실습은 각자의 폴더에 둔다. 이 저장소에 넣지 않는다.
