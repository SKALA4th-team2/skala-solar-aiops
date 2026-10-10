# 모델 저장소 운영 안내

들인 이유와 범위는 [결정0017](decisions/0017-optional-model-archive.md)에, 로컬 사본을 정리하는 기준은 [결정0018](decisions/0018-prune-archived-local-models.md)에 있다.

## 현재 흐름

재학습으로 생긴 승인 모델은 모델·고정 스케일러·manifest를 함께 보관하고 다시 읽어 검증한 뒤 운영에 적용한다. 보관 실패 시 기존 운영 버전을 유지한다. R2를 원본 보관소로, 앱의 모델 파일을 로컬 캐시로 사용한다. 파일과 입력·출력 형식, 프론트는 유지한다.

초기 모델(각 발전소의 v1)은 Git에 들어 있으므로 runtime을 처음 만들 때 보관소로 올리지 않는다. 첫 실행이 네트워크 없이 끝나고, PC마다 같은 v1이 서로 다른 경로로 31벌씩 쌓이지 않는다. v1도 보관소에서 복구되게 하려면 아래 "확인 명령"의 publish로 직접 올린다. 올리지 않은 v1의 로컬 폴더가 없어지면 롤백 API는 404(저장된 버전이 없습니다)를 돌려주고 운영 버전은 바뀌지 않는다.

이전 버전 적용은 승인된 모델을 로드·검증하는 작업이다. 로컬 모델이 있으면 R2 업로드나 다운로드 없이 적용한다. 로컬 버전 디렉터리가 없으면 R2에서 복구한 뒤 적용한다. 롤백하면서 같은 모델을 재업로드하지 않는다. 일부만 남았거나 손상된 로컬 디렉터리는 자동 덮어쓰지 않으며, 내려받기 전에 거절한다. 그 디렉터리를 다른 곳으로 옮긴 뒤 다시 적용한다.

모델 위치·manifest SHA는 로컬 archive/{version}.json과 MLflow 버전 태그에 기록한다. 로컬 기록이 없어도 MLflow의 archive_key·archive_manifest_sha256으로 복구할 수 있다. 모델 객체는 계약/발전소/버전/manifest SHA 경로로 구분하며 다른 내용으로 덮어쓰지 않는다.

## 로컬 사본 정리

보관 기능을 켜면 로컬에는 운영 중인 버전과 그 직전 버전만 남는다. 버전이 쌓여도 로컬 용량이 늘지 않게 하려는 것이다.

- 운영 버전이 바뀔 때마다(재학습 승격, 이전 버전 적용) 나머지 버전의 로컬 폴더를 지운다.
- 지우기 전에 보관소의 세 파일을 다시 읽어 로컬 파일과 같은지 확인한다. 다르거나 읽지 못하면 지우지 않는다. 보관 기록이 없는 버전(자동 보관하지 않는 초기 모델 v1, 보관 기능을 끈 채 만든 버전)도 지우지 않는다.
- 지운 버전은 manifest 사본만 `models/{발전소}/archive/{버전}.manifest.json`에 남는다. 이력 화면에는 상태가 `외부 보관`으로 보이고, `운영 적용`을 누르면 보관소에서 내려받아 검증한 뒤 반영한다.
- 지운 결과는 `local_models_pruned` 이벤트로, 실패는 `local_prune_failed` 이벤트로 남는다. 정리가 실패해도 운영 버전 교체는 그대로 유지된다.
- 정리하지 않으려면 `SOLAR_MODEL_KEEP_LOCAL=1`로 실행한다. 기본 실행(보관 기능 꺼짐)에서는 아무것도 지우지 않는다.

이미 쌓인 버전을 한 번에 정리하려면 아래 명령을 쓴다.

```powershell
.venv\Scripts\python -X utf8 ../tools/hourly/archive_models.py prune --backend r2 --plant hadong-sewage
```

MLflow가 따로 드는 모델 사본(버전마다 평균 101KB)은 정리하지 않는다. 버전 폴더(평균 65KB)보다 크므로 로컬 용량을 더 줄이려면 이것도 다뤄야 한다.

## 로컬 실행

명령은 project/에서 실행한다. 저장소를 pull 한 뒤에는 `pip install -r requirements.txt`를 다시 실행한다. 실행기가 시작할 때 python-dotenv를 읽고 R2 모드는 boto3를 쓰므로, 설치하지 않으면 보관을 쓰지 않아도 서버가 뜨지 않는다. project/.env에 R2 연결 정보와 SOLAR_MODEL_STORE=r2를 넣는다. 프로세스 환경변수가 우선하며 서버는 설정 변경 후 재시작해야 한다. 키를 화면·로그·Git에 남기지 않는다.

```powershell
cd project
Remove-Item Env:SOLAR_MODEL_STORE -ErrorAction SilentlyContinue
.venv\Scripts\python -X utf8 scripts/run_backend.py
```

macOS·Linux에서는 `.venv/bin/python`을 쓴다.

화면은 http://127.0.0.1:8077/ 이다. 기본 모드는 disabled이며 R2 키만 입력해서는 활성화되지 않는다. SOLAR_MODEL_STORE=local과 SOLAR_MODEL_ARCHIVE_DIR를 지정하면 외부 연결 없이 별도 디렉터리에서 보관·복구를 시험한다. local인데 SOLAR_MODEL_ARCHIVE_DIR가 없으면 그 이름을 적은 오류가 난다.

## 확인 명령

```powershell
.venv\Scripts\python -X utf8 ../tools/hourly/verify_r2.py
.venv\Scripts\python -X utf8 ../tools/hourly/test_model_store.py
```

verify는 현재 모델을 R2에서 임시 runtime으로 복구해 해시와 24시간 예측 일치를 확인한다. 운영 파일을 삭제하지 않는다. 실제로 보관한 모델에만 사용할 수 있다.

기존 모델(초기 모델 v1 포함)을 보관하려면 명시적으로 업로드한다. 실제 이력의 발전소와 버전으로 지정한다.

```powershell
.venv\Scripts\python -X utf8 ../tools/hourly/archive_models.py publish --backend r2 --plant hadong-sewage --version 3
```

## 보관이 실패했을 때

재학습 중 보관에 실패하면 작업은 failed로 끝나고 운영 버전은 그대로다. 통과한 후보 버전은 로컬에 등록된 채 남는다. 같은 종료 시각의 파일을 다시 올려도 기존 작업을 재사용하므로 다시 학습하지 않는다. 보관소가 돌아온 뒤 아래 순서로 그 버전을 적용한다.

1. `GET /jobs?plant_id=…`의 실패한 작업에서 오류를 보고, `data/runtime-hourly/models/{발전소}/versions/`에서 후보 버전 번호를 확인한다.
2. 후보를 보관한다. `archive_models.py publish --backend r2 --plant {발전소} --version {번호}`
3. 롤백 API(`POST /plants/{plant_id}/rollback`, 본문 `{"version": 번호}`)로 그 버전을 적용한다. 이력에는 적용 사유가 manual_rollback으로 남는다.

2026-10-09 로컬 폴더 보관소에서 이 순서를 실행해 v1 유지 → 수동 보관 → v2 적용을 확인했다.

## 운영 시 지킬 것

- runtime의 DB·등록부·운영 포인터·보관 기록·재생 이력을 함께 백업한다. API와 작업자를 정지한 상태에서 runtime을 백업한다. MLflow artifact 경로가 절대 경로일 수 있으므로 다른 서버의 복원은 별도 검증한다.
- R2 모델 파일만으로 전체 서비스 상태를 복구할 수 없다. MLflow와 archive 기록을 모두 잃으면 현재 코드로 보관 버전을 자동 탐색하지 않는다.
- 합성 CSV는 기능 테스트용이다. 업로드는 해당 runtime의 최신 실적과 운영 모델을 바꿀 수 있으며, 모델 롤백만으로 업로드 자료가 원복되지 않는다. 실제 운영 자료와 혼용하지 않는다.
- 현재 앱과 작업자는 한 PC에서 실행한다. 새 모델을 보관하는 실행기는 R2 쓰기 권한이 필요하다. 실행 단위를 분리할 때 앱은 읽기 전용 권한을 사용한다.

Docker 이미지의 초기 seed 제외·외부 초기 설치, 서버와 DB 이전, 다중 서버 동기화는 이번 변경에 포함하지 않는다.

## 확인된 결과

| 날짜 | 보관소 | 확인한 것 | 증빙 |
| --- | --- | --- | --- |
| 2026-10-08 | 실제 R2 | 하동 v3을 임시 runtime으로 내려받아 묶음 해시와 24시간 예측이 일치 | [R2 검증](proposal/evidence/r2-local-20261008/verification.json) |
| 2026-10-08 | 모의 처리 | 합성 자료의 CSV 검사, 작업 등록, 5 epoch 학습, 게이트 통과, 후보 파일 생성. 모델 등록과 R2는 모의 처리 | [합성 재학습 검증](proposal/evidence/r2-local-20261008/retrain-sample-validation.json) |
| 2026-10-09 | 로컬 폴더 | 격리 runtime에서 합성 자료 업로드 → 재학습 → 게이트 통과 → 보관 → v2 운영 반영. 로컬 v2와 보관 기록을 지운 뒤 MLflow 태그로 복구했고 24시간 예측이 일치. 보관 실패 시 v1 유지와 복구 순서 | [로컬 보관 검증](proposal/evidence/model-store-local-20261009/verification.json) |
| 2026-10-10 | 실제 R2 (읽기만) | 버킷에 하동 v1 ~ v3의 파일 9개. 세 묶음을 내려받아 manifest·모델·스케일러 해시와 식별 정보가 모두 일치하고 모델이 열려 24개 값을 냄. v3은 manifest가 만들어진 지 1 ~ 2초 뒤에 모델 → 스케일러 → manifest 순서로 올라가 있었음 | [R2 읽기 전용 확인](proposal/evidence/r2-readonly-20261010/verification.json) |
| 2026-10-10 | 로컬 폴더 | 두 번째 재학습으로 v3이 운영에 오르자 로컬에 v1·v3만 남고 v2는 보관소에만 남음. 이력에는 v2가 `외부 보관`으로 보이고, 적용하자 복구되어 24시간 예측이 지우기 전과 일치. v1도 직접 보관한 뒤에는 같은 방식으로 정리·복구 | [로컬 정리 검증](proposal/evidence/model-prune-local-20261010/verification.json), [화면](proposal/evidence/model-prune-local-20261010/history-external-archive.png) |

격리 테스트(`test_model_store.py`)는 2026-10-08에 14개, 2026-10-09에 17개, 로컬 정리를 더한 2026-10-10에 21개가 통과했다.

v3의 업로드 시각은 재학습 직후 코드가 자동으로 올렸다는 것과 맞는다. 다만 그 실행을 직접 본 것은 아니고 버킷에 남은 시각으로 미루어 본 것이다. v1과 v2는 만든 지 각각 약 7시간 29분, 17분 31초 뒤에 올라갔다. 실제 R2를 상대로 한 로컬 정리와 복구는 돌려 보지 않았다. 합성 자료 재학습은 기능 검증이며 예측 성능 근거가 아니다.
