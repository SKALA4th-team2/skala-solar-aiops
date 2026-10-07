# skala-solar-aiops

SKALA 「모델 서빙 및 AIOps 구성」 과정(임성열 교수)의 조별 미니 프로젝트 저장소다. 발표는 2026-10-08 15:00~17:30, 조당 20분 이내다.

태양광 발전소의 다음 날 하루 발전량을 예측하는 모델을 서빙하고, 설비나 예측에 문제가 생기면 감지해 대응하는 파이프라인을 만든다. 수업에서 받은 HAIC 실습 코드(주가 예측)를 태양광 도메인으로 바꿔서 만든다. 데이터는 공공데이터포털의 「한국남부발전(주)\_하동하수처리장 태양광발전실적」(2013-01-01 ~ 2026-02-28, 하루 합계와 시간대별 24칸)이다.

## 여러 발전소로 넓히는 준비

지금의 서비스는 **발전소 한 곳**(하동하수처리장, 설비 용량 55kW)만 다룬다. 고객으로 둔 전력 중개 사업자는 발전소를 여러 곳 묶어 운영하므로, 여러 발전소의 자료를 받아 발전소별 예측과 그 합계를 함께 내는 쪽으로 넓히려 한다. **아직 구현하지 않았다.** 2026-10-07 에 한 것은 준비다.

- 제도 조건을 공식 규정으로 다시 확인했다. 재생에너지 발전량 예측제도의 참여 요건은 묶음 안 태양광·풍력의 **설비 용량** 합계가 20MW 를 **초과**하는 것이고(발전량의 기준이 아니다), 용량 말고도 등록, 계량, 구성 비율, 등록시험이 따로 있다. 우리 자료의 설비 용량 합계는 55kW 이고 하동군 5곳을 더해도 606.17kW 다. 그래서 포트폴리오는 "가상의 묶음"이라고 적고, 자료를 모았다는 것을 요건을 채웠다고 쓰지 않는다.
- 지금 코드의 단일 발전소 가정 11가지를 찾아 변경안과 함께 정리했다.
- 여러 발전소 자료의 계약과, 그것을 검증·변환·평가하는 도구를 만들어 합성 자료와 하동 5곳의 실제 자료로 돌렸다.
- 한 PC 에서 서빙과 학습을 함께 돌릴 때의 학습 시간, 메모리, 학습 중의 예측 시간을 쟀다.

읽는 순서는 [`docs/proposal/multi-plant-extension.md`](docs/proposal/multi-plant-extension.md)(배경, 제도 조건, 변경 계약, 다음 구현의 순서) → [`multi-plant-data-contract.md`](docs/proposal/multi-plant-data-contract.md)(자료 계약과 새 자료를 넣는 절차) → [`single-pc-operation.md`](docs/proposal/single-pc-operation.md)(한 PC 의 구조와 규모)다. 직접 돌린 기록은 [`docs/proposal/evidence/multi-plant/validation.md`](docs/proposal/evidence/multi-plant/validation.md)에 있다.

## 구조

```text
skala-solar-aiops/
├── README.md              이 문서
├── AGENTS.md              작업 규칙. CLAUDE.md 와 같은 문서다
├── CONTRIBUTING.md        처음 합류할 때 읽는 최소 규칙
├── project/               서빙 앱. HAIC 스켈레톤을 태양광용으로 고쳐 나간다. 폴더 구조는 바꾸지 않는다
├── datasets/              업로드용 데이터와 출처, 만든 방법
│   └── plants/            발전소 등록부와 포트폴리오 구성 (여러 발전소 준비)
├── tools/                 데이터를 만드는 스크립트 등 project/ 밖에서 쓰는 도구
│   └── multi_plant/       여러 발전소 자료의 검증, 변환, 용량 합산, 기간 확인, 평가
└── docs/
    ├── proposal/          기획서 ①~⑥ 과 도메인 매핑표 (평가 대상). 여러 발전소 확장 문서 세 편
    │   └── evidence/      ⑥ 동작 화면 캡처와 로그. multi-plant/ 에 여러 발전소 준비의 검증 기록
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
- [x] 조사 보고서를 `docs/research/` 에 넣고, 팀이 정할 것을 `docs/decisions/` 에 기록 (결정 기록 12건이 있다. 0002 의 API 입력 계약만 확정이고 나머지는 "제안"이다)
- [x] 업로드용 데이터를 `datasets/` 에 넣기
- [ ] 도메인 매핑표 확정 ([`docs/proposal/domain-mapping.md`](docs/proposal/domain-mapping.md))
- [x] FastAPI 태양광 입력·업로드·배치 계약과 대시보드·시뮬레이션 호출부
- [ ] MLOps·AIOps 태양광 모델·게이트·판정·재학습 연결 (팀원 담당). 게이트는 아직 주가의 눈금(4.00)이라 태양광 모델이 통과하지 못한다
- [ ] 기획서 ①~③ (설계 40점). 초안이 있고 값은 결정 기록의 제안을 따른다
- [ ] 기획서 ④~⑥ 과 시연 (구현·발표 60점). 초안이 있다. 서버에서 돌린 장면은 일부다
- [x] 여러 발전소로 넓히는 준비: 제도 조건의 재확인, 자료 계약, 검증·평가 도구, 한 PC 측정, 설계 문서, 결정 기록 제안 세 건(0010 ~ 0012)
- [ ] 여러 발전소를 받는 서비스의 구현. 순서는 [확장 문서 9절](docs/proposal/multi-plant-extension.md#9-다음-구현-작업)
- [ ] 다른 발전소의 자료 넣기. 백엔드를 돌릴 PC 에 두고 [자료 계약 6절](docs/proposal/multi-plant-data-contract.md#6-새-자료를-넣는-절차)의 절차로 넣는다
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

### Windows 에서

위 명령은 macOS 와 리눅스의 셸 기준이다. Windows(PowerShell)에서는 가상환경을 켜지 않고 그 안의 파이썬을 바로 부르는 쪽이 간단하다. 환경 변수는 명령 앞에 붙이지 않고 따로 준다.

```powershell
cd project
py -3.11 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt

.venv\Scripts\python -m uvicorn serving_app.main:app --host 0.0.0.0 --port 8077
.venv\Scripts\python scripts\train_baseline_v1.py
.venv\Scripts\python serving_app\train_and_register.py
$env:MODEL_SOURCE = "mlflow"; .venv\Scripts\python -m uvicorn serving_app.main:app --host 0.0.0.0 --port 8077
```

- **Windows 에서 직접 돌려 확인한 것이 아니다.** 이 저장소의 검증은 macOS 에서 했다. `requirements.txt` 의 패키지(특히 tensorflow)가 Windows 에 그대로 설치되는지도 확인하지 못했다. 설치가 되지 않으면 WSL2 나 컨테이너(`docker compose`)에서 돌린다. 컨테이너 안은 리눅스라 위의 셸 명령이 그대로 통한다.
- 줄 끝은 `.gitattributes` 로 LF 에 고정했다. Windows 에서 받아도 파일의 해시와 컨테이너로 복사되는 파일이 다른 PC 와 같다.
- `tools/multi_plant/` 의 도구는 `python` 대신 `project\.venv\Scripts\python` 으로 부르면 된다. 출력은 UTF-8 로 고정했다. 한 PC 측정 도구(`single_pc_probe.py`)는 Windows 에서 메모리를 읽는 방법이 달라 값을 macOS 의 것과 그대로 견주지 않는다.

여러 발전소 자료의 검증과 평가는 저장소 루트에서 돌린다. 표준 라이브러리만 쓴다. 쓰는 법은 [`tools/multi_plant/README.md`](tools/multi_plant/README.md)에 있다.

```bash
# 저장소 루트에서
python tools/multi_plant/selftest.py                                    # 합성 자료로 실패 사례 21건 점검
python tools/multi_plant/convert_kospo_raw.py --raw datasets/raw/data_15043409.csv --plant-id hadong-sewage --out-root datasets/plants
python tools/multi_plant/validate.py --data-root datasets/plants        # 등록부, 구성, 실적이 계약을 지키는가
python tools/multi_plant/portfolio_capacity.py --data-root datasets/plants --portfolio virtual-vpp
python tools/multi_plant/coverage.py --data-root datasets/plants --portfolio virtual-vpp
python tools/multi_plant/evaluate.py --data-root datasets/plants --portfolio virtual-vpp --start 2025-06-09 --end 2026-02-27
```

FastAPI는 태양광 예보 입력 계약을 사용한다. `datasets/hadong_upload_forecast_jma.csv`를 올리고 같은 의미로 학습한 모델·스케일러를 준비해야 한다. 기존 HAIC 모델은 호환되는 태양광 모델이 아니다. AIOps 판정기는 아직 미연결이며 배치 응답에 `skipped`를 표시한다. [인수인계](docs/fastapi-handoff.md)의 남은 MLOps·AIOps 작업을 이어서 진행한다.
