# 제출 및 다른 PC 실행

승인된 시간별 모델 31개와 scaler.pkl, manifest.json, 등록부 및 재생용 이력을 Git에 포함한다. clone/pull만으로 seed를 받으며 별도 모델 다운로드나 재학습이 필요 없다. 운영 DB·MLflow 실행 기록·로그·업로드·가상환경·키는 포함하지 않는다.

## 최초 실행

Python 3.11 설치 후 모든 명령을 project/에서 실행한다.

```powershell
py -3.11 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -X utf8 scripts/run_backend.py
```

기존 가상환경은 다시 만들지 않아도 된다. 실행기가 모델·스케일러 SHA를 확인하고 새 PC의 로컬 MLflow에 31개 모델을 등록한다. 최초 등록은 시간이 걸릴 수 있다. 화면은 http://127.0.0.1:8077/ 이며 /health의 status=ok, worker_alive=true, plants=31을 확인한다. 별도 API 키는 필요 없다. uvicorn을 직접 실행하지 않고 run_backend.py를 사용한다.

기존 운영 상태가 있는 PC는 새로 pull한 seed로 운영 모델을 강제 덮어쓰지 않는다. 새 초기 상태로 검증하려면 별도 SOLAR_STATE_DIR를 지정한다. 기존 DB나 모델을 임의 삭제하지 않는다.

## 선택적 ZIP 전달과 재학습

오프라인 전달은 solar-hourly-seed.zip과 동명 .zip.manifest.json을 함께 project/submission/에 놓고 scripts/install_bundle.py로 설치할 수 있다. 현재 Git seed와 다른 묶음은 섞지 않는다. ZIP은 필수가 아니다.

원자료 재학습은 requirements-training.txt 설치 후 tools/hourly/prepare.py → train.py → finalize.py를 사용한다. 기존 평가와 구분하려면 HOURLY_EVIDENCE_DIR를 새 경로로 지정한다. seed 갱신은 모델·스케일러·manifest의 승인과 해시를 함께 검증한 뒤 커밋한다.

## 컨테이너 검증

[원본 재학습 및 Docker 검증 실행](https://github.com/SangMyeong5426/skala-solar-aiops/actions/runs/37643858606)이 성공했다. 코드 c96a102에서 33개 후보를 재학습해 같은 31개소를 승인했고, Linux Docker에서 31개 예측·자동 재학습·v1→v2→v1·컨테이너 재시작 후 예측 기록 보존을 확인했다. [실제 HTTP 결과](../proposal/evidence/submission_20261008/docker-initial/summary.json), [재시작 결과](../proposal/evidence/submission_20261008/docker-initial/restart-persistence.json), [컨테이너 상태](../proposal/evidence/submission_20261008/docker-initial/compose-ps.json)를 보관했다.

워크플로우는 `.github/workflows/submission.yml`이다. PR과 main/final push에서 저장소의 seed를 직접 검증하고 Docker를 실행한다. 별도 모델 다운로드 없이 새 checkout으로 기동하는 경로를 검사한다. 수동 실행의 retrain=true를 선택할 때만 원자료 재학습을 수행한다. artifact에는 선택적 모델 ZIP과 manifest, Swagger HTML, Docker 버전·빌드·컨테이너 로그가 포함되며 보존 기간은 30일이다. 모델의 기본 배포 경로는 Git이다.

Docker가 있는 PC에서는 저장소를 받은 뒤 다음과 같이 실행한다.

```powershell
docker compose -f serving_app/docker-compose.yml up --build -d
```

화면 http://127.0.0.1:8099/ . 상태는 /health의execution_unit=container와worker_alive=true로확인한다. 운영기본은SOLAR_DEMO_MODE=0이다. 합성시험시만1로설정하고별도volume에서실행한다.

## 발표 순서

① 이해관계자 불편 →② 시간별 LSTM과독립성능 →③ 품질게이트·보류·재학습정책 →④ 실제구조 →⑤ 입력검증·예측기록 →⑥ v1→v2→v1·Docker·재시작 증빙 순서로설명한다. 발표용 시나리오는 docs/proposal/6-demo.md에있다.

실시간자료수집,실제예보공개시각,현장관측기상검증,장기가용성99%,정산요건충족은실증한것이아니다. 합성드리프트기능시연의RMSE를 모델의독립예측성능으로발표하지않는다.


## 최종 확인

[최종 코드 Docker 실행](https://github.com/SangMyeong5426/skala-solar-aiops/actions/runs/37647422068)은 **전체 성공**했다. 검증 코드 c3cc07a, 원본 재학습 seed는 c96a102 실행의 승인 묶음이다. 이후 변경은 증빙과 문서뿐이다. [HTTP 통합 결과](../proposal/evidence/submission_20261008/docker-final/summary.json), [재시작 영속성](../proposal/evidence/submission_20261008/docker-final/restart-persistence.json), [CI 기록](../proposal/evidence/submission_20261008/docker-final/ci-run.json)을 보관했다.

앞선 서빙 재검증에서는 기능 검사가 모두 통과한 뒤 빈 pip 캐시 정리에서 CI만 실패했다. 재학습을 생략할 때 캐시도 생략하도록 수정했으며 위 최종 실행에서 해결을 확인했다.

이 PC의 `project/submission/solar-aiops-final.zip`은 코드·문서·31개 seed를 함께 담은 전달용 묶음이다. 압축을 푼 뒤 project/에서 Python 3.11 가상환경과 requirements.txt를 설치하고 scripts/run_backend.py를 실행한다. seed가 포함되어 있으므로 별도 학습 없이 시작할 수 있다. 환경 파일·키·운영 DB·가상환경은 포함하지 않는다.


2026-10-08 추가: 발전 현황의 인센티브 참고 평가 패널에서 시간별 예측오차율, 4%·6% 충족률, 평가 대상·제외 시간, 예상 인센티브 모의 금액을 조회한다. 24/72/168시간 선택과 계수 1.0/0.5 시나리오를 지원한다. 계산 조건은 결정 0015와 API 명세를 따른다. 단일 예측·과거 재생 기반이며 실제 지급액 판정이 아니다.

## 과거 Actions 모델 배포 기록

결정0016 이전에는 Git에 모델이 없어 Actions artifact의 ZIP과 manifest를 별도로 설치했다. 현재는 승인 seed가 Git에 있으므로 이 단계가 필요 없다. 기존 Actions artifact는 보존 기간 30일인 검증/백업 자료이며 필수 배포 경로가 아니다.
