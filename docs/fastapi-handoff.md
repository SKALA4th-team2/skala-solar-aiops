# FastAPI 작업 범위와 인수인계

2026-10-07. 본인은 백엔드 FastAPI까지 맡고, MLOps와 AIOps는 팀원이 이어받는다. 공통 준비인 HAIC 정답 빈칸 11개는 `347af06`에서 완료했다.

## 작업 방식과 체크리스트

사용자 요청대로 **이슈 생성 → 해당 작업 구현·검증 → 커밋·푸시 → 다음 이슈 생성** 순서로 진행한다. `fastapi` 브랜치에 올리며 `main` 병합은 별도다.

| 이슈 | 작업 | 상태 |
| --- | --- | --- |
| [#5](https://github.com/SangMyeong5426/skala-solar-aiops/issues/5) | 공통 업로드 검증·파일 충돌 방지·오류 응답·헬스체크 버전 | `8e322c1` 푸시 완료 |
| [#6](https://github.com/SangMyeong5426/skala-solar-aiops/issues/6) | 태양광 단건·CSV 규격, 대상일·모델 출처 | `88e120a` 푸시 완료 |
| [#7](https://github.com/SangMyeong5426/skala-solar-aiops/issues/7) | 배치 요청·AIOps 연결 계약·대시보드·시뮬레이션 | 구현·검증 완료. 이 문서를 포함한 `Closes #7` 커밋으로 푸시 |

- [x] 담당 경계 기록
- [x] CSV 검증 및 완성 파일만 공개, UUID 파일명
- [x] 모델 미준비 503, 기존 잘못된 CSV 조회 409
- [x] 단건: 연속 20일, 발전량 0~1,320kWh, 다음 날 예보 0~45MJ/m², 대상일 응답
- [x] 배치: dates/prices/volumes/expected 정렬·길이·범위 검사, 실제 예보 사용
- [x] 날짜와 사후 기대값을 모델 입력에서 제외
- [x] AIOps 연결 계약, 미연결은 skipped로 명시
- [x] 대시보드·CLI 요청부와 명세·증빙 동시 갱신
- [ ] 팀원 모델과 판정기를 연결한 실제 품질·재학습·승격 통합 검증 (MLOps/AIOps 담당과 함께)

## 담당 경계

| 담당 | 소유 작업 | 연동 지점 |
| --- | --- | --- |
| 본인: FastAPI | `schemas.py`, `routers/`, `main.py`, API 명세·검증 | 요청 검증 → 모델 호출 → 응답. 업로드·상태·로그 조회 |
| 팀원: MLOps | 학습 스크립트, MLflow, 게이트, 모델·스케일러, 컨테이너 | `model_loader.get_model()`, 실제 레지스트리 버전, 승격 뒤 캐시 교체 |
| 팀원: AIOps | `monitoring/`, 감시·설비 판정·재학습·알림 | `aiops_adapter.configure_evaluator()`에 판정기 연결 |
| 공동 수정 시 조율 | 모델 로더, 배치 라우터, 대시보드, 시뮬레이션 | API 계약을 바꾸면 명세·스키마·호출부를 같이 맞춘다 |

`monitoring/`의 기존 HAIC 구현, 학습 스크립트, 게이트·임계값은 이 작업에서 변경하지 않았다. 모델 로더에는 파일 미준비 검사와 `source` 속성만 추가했다. `data/features.py`, `lstm_model.py`는 입력 의미 주석만 맞췄으며 스케일러·모델 구조는 그대로다.

## MLOps 인수인계

- `get_model()`은 `predict_one(sequence)`, `version`, `source`가 있는 객체를 반환한다. `source`는 `local` 또는 `mlflow`다.
- `sequence`는 `{"close": 당일 발전량, "volume": 다음 날 예보}` 20행이다. 날짜와 `expected`는 들어가지 않는다. 모델 출력은 역변환된 kWh 실수여야 한다.
- API는 음수 출력을 0으로 자른다. 비유한 출력은 503이다. 단건 응답은 소수 둘째 자리로 반올림하고 배치 예측은 계산 정밀도를 유지한다.
- `FileNotFoundError`는 503이다. 로컬 파일 미준비는 TensorFlow 로드 전에 검사한다. 손상 모델·레지스트리 오류의 처리는 별도다.
- 현재 로더의 `v1-local`, `production` 표시는 실습 문자열이다. 실제 레지스트리 버전과 승격 뒤 캐시 교체는 MLOps가 구현한다. 헬스체크의 버전·출처는 현재 캐시에서 읽는다.
- CSV는 `data/uploads/haic_<uuid>.csv`로 저장한다. `latest_upload()`는 수정 시각으로 선택한다. 업로드만으로 모델·스케일러가 자동 생성되지는 않는다.
- 입력 의미가 바뀌었으므로 태양광 예보 데이터로 모델과 스케일러를 함께 만들어야 한다. 기존 HAIC 가중치를 그대로 사용하면 안 된다.

## AIOps 인수인계

앱 시작 시 다음처럼 판정기를 연결한다. 아래 `evaluate`는 팀원이 구현할 함수다.

```python
from serving_app.aiops_adapter import configure_evaluator
configure_evaluator(evaluate)
```

호출 계약:

```python
def evaluate(*, rows: list[dict], predictions: list[dict], model_version: str) -> dict:
    ...
```

- `rows`: 요청 전체 N행. `date`(YYYY-MM-DD), `close`, `volume`, `expected`(관측 기반 기대 발전량 또는 None). 앞 20행까지 전달하므로 재학습 대기 조건을 검사할 수 있다.
- `predictions`: N−20행. 각 예측 대상일의 `date`, `predicted`, `actual`, `expected`. 서버는 요청 간 예측 기록을 합치지 않는다. 중복 배치의 판정·재학습 방지와 최근 21일 선택은 AIOps가 맡는다.
- 반환: `DriftCheck` 또는 그 스키마의 dict. `status`, `model_version`은 필수. 상태는 `ok`, `drift_alerted`, `retrain_triggered`, `facility_check`, `skipped`, `input_anomaly` 중 하나다.
- `pi`, `baseline`, `deviation_pct`, `head_deviation_pct`, `valid_days`, `outage_days`, `hold_days`, `rmse21`, `promoted`, `rmse`, `reason`을 선택적으로 반환할 수 있다. 명시한 null은 유지하고 계산하지 않아 생략한 필드는 응답에서도 생략한다. 숫자를 꾸며 채우지 않는다.
- **미연결 기본 응답**: `{"status":"skipped","model_version":"...","reason":"aiops_not_configured"}`. 예측은 실행하지만 감시·학습·승격은 수행하지 않는다.
- 기존 `check_and_trigger(recent_predictions)`를 그대로 연결하면 입력 계약과 HAIC $4 기준이 맞지 않는다. 태양광 판정·재학습 정책으로 구현한 함수만 연결한다. `expected`는 사후 감시에만 사용한다.
- 판정기 예외는 정상 판정으로 바꾸지 않는다. 재학습의 중복 실행·버전 교체·실패 복구·요청 시간은 팀원 통합 검증에서 확인한다.

## 시뮬레이션과 대시보드

`project/`에서 실행한다.

```bash
# 네트워크 요청 없이 실제 41일로 대시보드용 JSON 생성
.venv/bin/python scripts/simulate_drift.py --csv ../datasets/hadong_upload_forecast_jma.csv --end-date 2025-07-31 --export-json /tmp/solar-batches.json

# 준비된 서버로 정상/14% 하락 배치 전송
.venv/bin/python scripts/simulate_drift.py --csv ../datasets/hadong_upload_forecast_jma.csv --end-date 2025-07-31 --target local
# --target container 또는 both 지원
```

대시보드에서 생성한 JSON을 선택해 정상/14% 하락 버튼을 누른다. 날짜·예보·기대 발전량은 그대로 두고 발전량에만 0.86을 곱한다. 이는 요청 데이터 생성 방식이며 드리프트가 실제로 탐지되었다는 뜻이 아니다. `expected`는 감시 CSV의 날짜로 맞춰 읽고 없으면 null이다. 임계값 판정은 대시보드에서 하지 않는다.

## 검증과 한계

```bash
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pip install -r ../tools/verify/requirements-fastapi.txt
.venv/bin/python ../tools/verify/test_fastapi.py
.venv/bin/python ../tools/verify/capture_fastapi.py --output ../docs/proposal/evidence/fastapi-batch
```

27개 API·CLI 테스트가 통과했다. 모델 계산과 AIOps는 대체 객체로 격리했으며, 실제 CSV·API 검증·JSON 내보내기를 확인했다. 증빙은 [fastapi-batch](proposal/evidence/fastapi-batch/)에 있다. 과거 #5, #6 증빙은 별도 폴더에 보존했다.

8077은 다른 작업 폴더의 서버가 사용 중이라 종료·교체하지 않았다. API 증빙은 TestClient 내부 ASGI 호출 결과다. 실제 학습 모델의 품질, 모델·스케일러 생성, MLflow 등록·승격, AIOps 정책, 컨테이너 실행은 팀원 후속 범위다.

브라우저에서 별도 세션과 모의 API 응답으로 정상·하락 요청 2건(각 41행), 예보·기대값 보존, 하락 배율, 7가지 파이프라인 표시를 확인했다. [검사 결과](proposal/evidence/fastapi-batch/browser-checks.json)와 [검증용 화면](proposal/evidence/fastapi-batch/dashboard-mocked.png)은 실제 모델 성능 증빙이 아니다.
