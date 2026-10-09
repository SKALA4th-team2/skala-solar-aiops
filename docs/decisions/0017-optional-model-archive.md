# 0017 — 재학습 모델의 선택적 외부 보관

- 상태: 확정 (선택 기능이다. 기본 실행은 쓰지 않는다)
- 날짜: 2026-10-09
- 정한 사람: 채수아(구현, PR #17), 박상명(병합)

## 배경

재학습으로 생긴 모델은 그 PC 의 runtime 폴더(`project/data/runtime-hourly`)와 로컬 MLflow 에만 있다. 초기 모델 31개는 [결정0016](0016-version-approved-model-seeds.md)으로 Git 에 넣었지만 재학습 산출물은 Git 에 넣지 않는다. PC 를 잃거나 runtime 을 지우면 재학습 버전으로 되돌릴 수 없다.

[`AGENTS.md`](../../AGENTS.md)의 범위 밖 항목은 "PC 한 대에서 돌린다"고 적고 있어, 외부 저장소를 들이는 것은 따로 정해야 했다.

## 검토한 선택지

| 선택지 | 얻는 것 | 잃는 것 |
| --- | --- | --- |
| 로컬에만 둔다(이전 방식) | 외부 의존이 없다 | PC 한 대가 고장 나면 재학습 버전을 잃는다 |
| 재학습 모델도 Git 에 넣는다 | 서비스를 더 들이지 않는다 | "자동 재학습 결과를 Git 에 자동 push 하지 않는다"는 결정0016 과 어긋나고 저장소가 계속 커진다 |
| 객체 저장소(Cloudflare R2)에 선택적으로 보관한다 | 버전마다 바뀌지 않는 사본이 남고, 로컬에서 없어진 버전을 복구한다 | 키를 관리해야 하고 네트워크에 묶인다. 보관소만으로는 서비스 전체 상태를 복구하지 못한다 |
| 운영 DB 와 MLflow 까지 외부로 옮긴다 | 서버를 바꿔도 이어서 운영한다 | 교재 범위(로컬 sqlite, PC 한 대)를 벗어나고 발표 전에 검증할 수 없다 |

## 결정

세 번째를 고른다.

- 기본값은 `SOLAR_MODEL_STORE=disabled` 다. `local`(다른 폴더) 또는 `r2` 로 바꿔야 켜진다. R2 키만 넣어서는 켜지지 않는다.
- 보관하는 것은 재학습으로 승인된 버전의 `model.keras`, `scaler.pkl`, `manifest.json` 이다. 경로는 `계약/발전소/버전/manifest SHA` 이고 이미 있는 객체를 다른 내용으로 덮어쓰지 않는다.
- 순서는 등록 → 보관 → 다시 읽어 검증 → 운영 버전 교체다. 보관이 실패하면 교체하지 않는다.
- 초기 모델(각 발전소의 v1)은 Git 에 있으므로 runtime 을 만들 때 자동으로 보관하지 않는다. 필요하면 `tools/hourly/archive_models.py publish` 로 올린다. PR #17 리뷰에서 정했다.
- 운영 DB, MLflow 기록, 업로드, 로그는 계속 로컬에 둔다. 옮기지 않는다.

## 근거

| 수치 | 조건 (기간, 분할, 시드 수) | 출처 |
| --- | --- | --- |
| 하동 v3 을 R2 에서 내려받은 묶음의 해시가 맞고, 24시간 예측이 내려받기 전과 같다 | 2026-10-08, 실제 R2, 임시 runtime | [`r2-local-20261008/verification.json`](../proposal/evidence/r2-local-20261008/verification.json) |
| 재학습 모델의 검증 7일(168시간) RMSE 4.47kWh, 한도 5.46kWh, 같은 7일의 기존 모델 RMSE 6.56kWh (모두 1시간 발전량 기준). 통과한 v2 를 보관한 뒤 운영에 반영했고, 로컬 v2 를 지운 뒤 복구한 모델의 24시간 예측이 지우기 전과 같다 | 2026-10-09, 로컬 폴더 보관소, 격리 runtime, 시드 1개(42). 합성 자료라 기능 확인용이며 예측 성능의 근거가 아니다 | [`model-store-local-20261009/verification.json`](../proposal/evidence/model-store-local-20261009/verification.json) |
| 초기 모델을 자동 보관하던 코드에서는 runtime 을 처음 만들 때 보관소에 파일 93개(발전소 31곳 × 3개)가 올라갔다. 고친 뒤에는 0개다 | 2026-10-09, 로컬 폴더 보관소 | 같은 증빙 |

재학습 직후 실제 R2 로 자동 업로드되는 흐름은 저장소에 증빙이 없다. 2026-10-08 의 합성 재학습 검증은 모델 등록과 R2 를 모의 처리했다.

## 함께 고칠 곳

- `AGENTS.md`, `CLAUDE.md` 의 범위 밖
- `docs/proposal/4-architecture.md`, `docs/model-storage.md`, `docs/backend-runbook.md`
- `project/serving_app/model_store.py`, `project/serving_app/registry.py`, `project/scripts/seed_runtime.py`
- `tools/hourly/test_model_store.py`, `tools/hourly/archive_models.py`, `tools/hourly/verify_r2.py`

## 다시 볼 조건

- R2 버킷과 키를 누가 관리하는지, 발표 뒤에 버킷을 어떻게 할지 정해지면 여기에 적는다([`followups.md`](../followups.md)).
- 재학습 직후의 R2 자동 업로드를 실제 버킷으로 확인하면 근거 표에 더한다.
- 앱과 학습 작업자를 다른 PC 로 나누거나 운영 DB 를 옮기게 되면 권한(앱은 읽기 전용)과 동기화를 다시 정한다.
