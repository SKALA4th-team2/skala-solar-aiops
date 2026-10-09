# 모델 저장소 운영 안내

## 현재 흐름

새 승인 모델은 모델·고정 스케일러·manifest를 함께 보관하고 다시 읽어 검증한 뒤 운영에 적용한다. 보관 실패 시 기존 운영 버전을 유지한다. R2를 원본 보관소로, 앱의 모델 파일을 로컬 캐시로 사용한다. 파일과 입력·출력 형식, 프론트는 유지한다.

이전 버전 적용은 승인된 모델을 로드·검증하는 작업이다. 로컬 모델이 있으면 R2 업로드나 다운로드 없이 적용한다. 로컬 버전 디렉터리가 없으면 R2에서 복구한 뒤 적용한다. 롤백하면서 같은 모델을 재업로드하지 않는다. 일부만 남았거나 손상된 로컬 디렉터리는 자동 덮어쓰지 않는다.

모델 위치·manifest SHA는 로컬 archive/{version}.json과 MLflow 버전 태그에 기록한다. 로컬 기록이 없어도 MLflow의 archive_key·archive_manifest_sha256으로 복구할 수 있다. 모델 객체는 계약/발전소/버전/manifest SHA 경로로 구분하며 다른 내용으로 덮어쓰지 않는다.

## 로컬 실행

명령은 project/에서 실행한다. project/.env에 R2 연결 정보와 SOLAR_MODEL_STORE=r2를 넣는다. 프로세스 환경변수가 우선하며 서버는 설정 변경 후 재시작해야 한다. 키를 화면·로그·Git에 남기지 않는다.

```powershell
cd C:\Users\teo\workspace\skala-solar-aiops\project
Remove-Item Env:SOLAR_MODEL_STORE -ErrorAction SilentlyContinue
.venv\Scripts\python -X utf8 scripts/run_backend.py
```

화면은 http://127.0.0.1:8077/ 이다. 기본 모드는 disabled이며 R2 키만 입력해서는 활성화되지 않는다. SOLAR_MODEL_STORE=local과 SOLAR_MODEL_ARCHIVE_DIR를 지정하면 외부 연결 없이 별도 디렉터리에서 보관·복구를 시험한다.

## 확인 명령

```powershell
.venv\Scripts\python -X utf8 ../tools/hourly/verify_r2.py
.venv\Scripts\python -X utf8 ../tools/hourly/test_model_store.py
```

verify는 현재 모델을 R2에서 임시 runtime으로 복구해 해시와 24시간 예측 일치를 확인한다. 운영 파일을 삭제하지 않는다. 실제로 보관한 모델에만 사용할 수 있다.

기존 모델을 보관하려면 명시적으로 업로드한다. 실제 이력의 발전소와 버전으로 지정한다.

```powershell
.venv\Scripts\python -X utf8 ../tools/hourly/archive_models.py publish --backend r2 --plant hadong-sewage --version 3
```

## 운영 시 지킬 것

- runtime의 DB·등록부·운영 포인터·보관 기록·재생 이력을 함께 백업한다. API와 작업자를 정지한 상태에서 runtime을 백업한다. MLflow artifact 경로가 절대 경로일 수 있으므로 다른 서버의 복원은 별도 검증한다.
- R2 모델 파일만으로 전체 서비스 상태를 복구할 수 없다. MLflow와 archive 기록을 모두 잃으면 현재 코드로 보관 버전을 자동 탐색하지 않는다.
- 합성 CSV는 기능 테스트용이다. 업로드는 해당 runtime의 최신 실적과 운영 모델을 바꿀 수 있으며, 모델 롤백만으로 업로드 자료가 원복되지 않는다. 실제 운영 자료와 혼용하지 않는다.
- 현재 앱과 작업자는 한 PC에서 실행한다. 새 모델을 보관하는 실행기는 R2 쓰기 권한이 필요하다. 실행 단위를 분리할 때 앱은 읽기 전용 권한을 사용한다.

Docker 이미지의 초기 seed 제외·외부 초기 설치, 서버와 DB 이전, 다중 서버 동기화는 이번 변경에 포함하지 않는다.

## 확인된 결과

2026-10-08 격리 테스트 14개 통과. 실제 R2에 하동 v1·v2·v3 보관과 manifest SHA를 확인했다. v3는 다운로드·SHA·24시간 예측 일치를 검증했다. 합성 자료 재학습은 기능 검증이며 예측 성능 근거가 아니다. [R2 검증](proposal/evidence/r2-local-20261008/verification.json), [합성 재학습 검증](proposal/evidence/r2-local-20261008/retrain-sample-validation.json).
