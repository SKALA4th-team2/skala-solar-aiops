# FastAPI 작업 범위와 인수인계

2026-10-07. 사용자 요청으로 본인 작업 범위는 백엔드 FastAPI까지다. MLOps와 AIOps는 팀원이 이어받는다. 공통 준비인 HAIC 정답 빈칸 11개는 `347af06`에서 완료했다.

## 진행 방식

사용자 요청에 따라 한 작업씩 **이슈 생성 → 구현·검증 → 커밋·푸시**를 마친 후 다음 이슈를 만든다. 첫 작업은 [#5](https://github.com/SangMyeong5426/skala-solar-aiops/issues/5) 공통 업로드 검증·오류 처리다. 태양광 입력 규격 적용은 승인되었으며 다음 작업으로 진행한다.

## 작업 체크리스트

- [x] README에 담당 범위 기록
- [x] CSV의 숫자·빈 값·유한값·음수·날짜 형식·중복·역순·컬럼 수 검사
- [x] 같은 시각 업로드의 파일명 충돌 방지, 완전히 쓴 파일만 학습 측에 노출
- [x] 잘못 저장된 기존 CSV 조회는 409, 모델·스케일러 파일 미준비는 503
- [x] `/health`에 현재 캐시 모델의 `model_version` 추가. 미로딩이면 null
- [x] FastAPI TestClient 검증 15개: 업로드, 상태, 예측 전달, 배치 분할, 모델 미준비, Swagger와 로그
- [x] 현재 API 명세·검증 증빙 정리
- [ ] 태양광 입력 규격 적용: 사용자가 0002의 API 규격 적용을 승인함. 다음 이슈에서 구현
- [ ] 태양광 배치 입력과 AIOps 데이터 전달 계약 확정
- [ ] 태양광 규격에 맞춰 대시보드·시뮬레이션 요청부 동시 수정
- [ ] 팀원 모델을 연결한 실제 예측 200과 학습·승격 후 통합 검증

## 담당 경계

| 담당 | 소유 작업 | 경계 |
| --- | --- | --- |
| 본인: FastAPI | `schemas.py`, `routers/`, `main.py`, API 문서·검증 | 요청 검사 → 모델 호출 → 응답. 업로드와 상태·로그 조회 |
| 팀원: MLOps | `train_baseline_v1.py`, `train_and_register.py`, MLflow, 모델·스케일러, 컨테이너 | 학습, 품질 게이트, 등록·승격, 실제 레지스트리 버전, 모델 교체 |
| 팀원: AIOps | `monitoring/`, 감시·재학습·시연 알고리즘 | 판정 기준, 기대 발전량·정지 처리, 재학습 중복 방지, 알림 |
| 연동 시 함께 | `model_loader.py`, `routers/predict.py`, `static/index.html`, `simulate_drift.py` | FastAPI가 요청·응답을 바꾸면 호출부를 함께 맞춘다. 감시 계산·게이트·모델 교체는 팀원이 구현한다 |

이번 `model_loader.py` 수정은 로컬 파일 존재 여부 검사뿐이다. 모델 계산·MLflow 로딩·캐시 교체 정책은 바꾸지 않았다. `monitoring/`, 학습 스크립트, 게이트·임계값도 이번 작업에서 바꾸지 않았다.

## 현재 연동 계약

- 모델 제공자: `model_loader.get_model()` → `predict_one(sequence)`와 `version`을 가진 객체. `sequence`는 최근 20행의 `close`, `volume`이다.
- FastAPI는 모델 제공자가 반환한 버전을 그대로 표시한다. 현재 실습 로더의 `production` 문자열을 레지스트리 버전 번호로 바꾸는 것은 MLOps 담당이다.
- `FileNotFoundError`는 예측 API에서 503이 된다. 로컬 파일이 없으면 TensorFlow를 불러오기 전에 이 오류를 발생시킨다. 잘못된 모델 파일·MLflow 레지스트리 오류까지 모두 503으로 바꾸지는 않는다.
- 현재 배치 API는 HAIC 계약을 유지한다. `prices`를 20개씩 잘라 예측하고, `check_and_trigger(recent_predictions)`에 최근 21개의 `predicted`, `actual`을 전달한다. 거래량 고정값도 아직 HAIC 값이다.
- AIOps는 현 함수의 반환 객체가 `drift_check`로 전달된다는 점을 유지한다. 날짜·예보·기대 발전량을 받는 태양광 계약은 결정 0002 및 0006~0008과 함께 후속 확정한다. 기대 발전량을 모델 입력에 넣지 않는다.
- 업로드 파일은 `data/uploads/haic_<uuid>.csv`다. `latest_upload()`는 수정 시간으로 고르므로 이름 변경과 호환된다. UTF-8 BOM은 제거하고 다른 데이터는 변환하지 않는다.
- 현재 CSV는 날짜가 엄격한 오름차순이어야 한다. HAIC 거래일 입력을 유지하므로 주말 등의 날짜 간격은 허용한다. 태양광용 하루 간격 검사와 상한은 아직 적용하지 않았다.
- `/health`의 `status: ok`는 서버가 응답한다는 뜻이다. 모델 미로딩이면 `model_loaded: false`, `model_version: null`이며 헬스체크 자체가 모델을 로드하지 않는다.

## 검증

`project/`에서 실행한다.

```bash
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pip install -r ../tools/verify/requirements-fastapi.txt
.venv/bin/python ../tools/verify/test_fastapi.py
```

모델 계산과 AIOps를 대체 객체로 격리한 15개 API 테스트가 통과했다. 로컬 파일 미준비 검사는 실제 로더를 호출한다. 업로드·로그 검사는 임시 폴더를 사용한다. 학습·승격·예측 품질은 측정하지 않았다. 증빙은 [api-tests.txt](proposal/evidence/fastapi/api-tests.txt), [TestClient 응답](proposal/evidence/fastapi/http-results.json), [OpenAPI](proposal/evidence/fastapi/openapi.json)에 있다.

8077 포트가 이미 사용 중이라 새 서버를 띄우는 실제 네트워크 검증은 실행하지 않았다. 기존 서버를 종료하거나 수정하지 않았다. 위 응답 증빙은 **TestClient로 앱 내부 ASGI 경로를 호출한 결과**이며 실제 네트워크 응답이나 운영 모델의 품질 증빙이 아니다.
