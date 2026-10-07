# skala-solar-aiops

SKALA 「모델 서빙 및 AIOps 구성」 과정(임성열 교수)의 조별 미니 프로젝트 저장소다. 발표는 2026-10-08 15:00~17:30, 조당 20분 이내다.

태양광 발전소의 다음 날 하루 발전량을 예측하는 모델을 서빙하고, 설비나 예측에 문제가 생기면 감지해 대응하는 파이프라인을 만든다. 수업에서 받은 HAIC 실습 코드(주가 예측)를 태양광 도메인으로 바꿔서 만든다. 데이터는 공공데이터포털의 「한국남부발전(주)\_하동하수처리장 태양광발전실적」(2013-01-01 ~ 2026-02-28, 하루 단위)이다.

## 구조

```text
skala-solar-aiops/
├── README.md              이 문서
├── AGENTS.md              작업 규칙. CLAUDE.md 와 같은 문서다
├── CONTRIBUTING.md        처음 합류할 때 읽는 최소 규칙
├── project/               서빙 앱. HAIC 스켈레톤을 태양광용으로 고쳐 나간다. 폴더 구조는 바꾸지 않는다
├── datasets/              업로드용 데이터와 출처, 만든 방법
├── tools/                 데이터를 만드는 스크립트 등 project/ 밖에서 쓰는 도구
└── docs/
    ├── proposal/          기획서 ①~⑥ 과 도메인 매핑표 (평가 대상)
    │   └── evidence/      ⑥ 동작 화면 캡처와 로그
    ├── decisions/         팀이 정한 것과 그 근거
    ├── research/          사전 조사와 데이터 분석 보고서 (보관 자료)
    ├── presentation/      발표 자료
    └── followups.md       아직 확인하지 못했거나 미뤄 둔 것
```

`project/` 에는 서빙 앱만, `datasets/` 에는 데이터만, `docs/` 에는 문서만 둔다. 무엇을 어디에 두는지는 [`AGENTS.md`](AGENTS.md)에 있다.

## 진행 현황

- [x] 저장소 뼈대와 작업 규칙
- [x] HAIC 스켈레톤 원본 커밋
- [x] 정답 이미지에 따라 HAIC 실습 빈칸 11곳 채우기
- [ ] HAIC 그대로 학습·서빙·자동 재학습이 끝까지 도는지 확인
- [ ] 조사 보고서를 `docs/research/` 에 넣고, 팀이 정할 것을 `docs/decisions/` 에 기록
- [ ] 업로드용 데이터를 `datasets/` 에 넣기
- [ ] 도메인 매핑표 확정 ([`docs/proposal/domain-mapping.md`](docs/proposal/domain-mapping.md))
- [x] FastAPI 태양광 입력·업로드·배치 계약과 대시보드·시뮬레이션 호출부
- [ ] MLOps·AIOps 태양광 모델·게이트·판정·재학습 연결 (팀원 담당)
- [ ] 기획서 ①~③ (설계 40점)
- [ ] 기획서 ④~⑥ 과 시연 (구현·발표 60점)
- [ ] 발표 자료

## 팀

역할은 달라도 결과물은 하나의 파이프라인으로 이어져야 한다. 같은 파일을 두 사람이 동시에 고치지 않도록 맡은 것을 먼저 여기에 적는다.

| 이름 | 맡은 것 | 주로 고치는 곳 |
| --- | --- | --- |
| | 기획 | `docs/proposal/` 1~3 |
| 본인 (`fastapi` 브랜치) | 백엔드 FastAPI, API 명세·검증 | `project/serving_app/` 의 스키마·라우터·앱 진입점 |
| 팀원 (이름 미기입) | MLOps: 학습·모델 등록·배포 | 학습 스크립트, MLflow 게이트, 모델 로더·컨테이너 |
| 팀원 (이름 미기입) | AIOps: 감시·재학습·시연 | `project/serving_app/monitoring/`, 시뮬레이션 |

HAIC 빈칸 1~11은 공통 준비 작업으로 완료했다(`347af06`). 이후 담당 경계와 체크리스트는 [FastAPI 인수인계](docs/fastapi-handoff.md)에 둔다.

## 실행

모든 명령은 `project/` 에서 실행한다. 다른 폴더에서 실행하면 import 경로가 어긋난다.

```bash
cd project
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 서버 (로컬 8077). 대시보드 http://localhost:8077/ , API 문서 http://localhost:8077/docs
uvicorn serving_app.main:app --host 0.0.0.0 --port 8077

# 대시보드에서 CSV 를 올린 뒤, 다른 터미널에서
python scripts/train_baseline_v1.py            # 스케일러와 baseline 모델
python serving_app/train_and_register.py       # MLflow 기록, 게이트, Production 승격
MODEL_SOURCE=mlflow uvicorn serving_app.main:app --host 0.0.0.0 --port 8077

# 컨테이너 (8099)
docker compose -f serving_app/docker-compose.yml up --build

# 드리프트 시뮬레이션
python scripts/simulate_drift.py
```

FastAPI는 태양광 예보 입력 계약을 사용한다. `datasets/hadong_upload_forecast_jma.csv`를 올리고 같은 의미로 학습한 모델·스케일러를 준비해야 한다. 기존 HAIC 모델은 호환되는 태양광 모델이 아니다. AIOps 판정기는 아직 미연결이며 배치 응답에 `skipped`를 표시한다. [인수인계](docs/fastapi-handoff.md)의 남은 MLOps·AIOps 작업을 이어서 진행한다.
