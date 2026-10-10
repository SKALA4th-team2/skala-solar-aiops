# 0018 — 보관한 모델의 로컬 사본 정리

- 상태: 확정 (보관 기능을 켠 경우에만 동작한다)
- 날짜: 2026-10-10
- 정한 사람: 박상명

## 배경

발표 뒤 교수님 피드백은 이렇다. 모델을 버전별로 보관해 두었다가 사용자가 원하는 버전을 골라 실행하게 하되, 로컬에 쌓아 두면 용량을 차지하니 클라우드(R2)에 두라는 것이다.

[결정0017](0017-optional-model-archive.md)의 구현은 재학습한 모델을 R2 에 올리지만 로컬 사본을 그대로 둔다. 같은 모델이 로컬과 R2 양쪽에 남아서 로컬 용량은 줄지 않았다. 이력 화면의 버전 목록도 로컬 폴더에서 만들기 때문에, 로컬 사본을 그냥 지우면 그 버전을 화면에서 고를 수 없게 된다.

## 검토한 선택지

| 선택지 | 얻는 것 | 잃는 것 |
| --- | --- | --- |
| 로컬과 R2 에 모두 둔다(0017 그대로) | 네트워크 없이 어느 버전으로든 바로 돌아간다 | 버전이 늘수록 로컬 용량이 는다. 피드백의 요점에 답이 되지 않는다 |
| 올리자마자 로컬에서 지운다 | 로컬에는 운영 중인 버전만 남는다 | 방금 바꾼 모델에 문제가 있을 때 직전 버전으로 돌아가는 데 네트워크가 필요하다 |
| 운영 중인 버전과 직전 버전만 로컬에 남기고 나머지를 지운다 | 로컬 용량이 버전 수와 무관해진다. 직전 버전으로는 네트워크 없이 돌아간다 | 더 오래된 버전을 고르면 내려받는 시간이 든다 |

## 결정

세 번째를 고른다.

- 운영 버전이 바뀔 때마다(재학습 승격, 이전 버전 적용) 정리한다. 운영 중인 버전과 그 직전 버전은 로컬에 남긴다.
- 지우기 전에 보관소의 세 파일을 다시 읽어 로컬 파일과 바이트가 같은지 확인한다. 하나라도 다르거나 읽지 못하면 지우지 않는다.
- 보관 기록이 없는 버전은 지우지 않는다. 자동 보관하지 않는 초기 모델(v1), 보관 기능을 끈 채 만든 버전이 여기에 든다.
- 지운 버전은 manifest 사본(약 2KB)을 `models/{발전소}/archive/{버전}.manifest.json` 에 남긴다. 이력 화면은 이 사본으로 그 버전을 계속 보여 주고 상태를 `외부 보관`으로 적는다. `운영 적용`을 누르면 보관소에서 내려받아 검증한 뒤 반영한다.
- 정리가 실패해도 이미 끝난 운영 버전 교체는 되돌리지 않는다. `local_prune_failed` 이벤트만 남긴다.
- `SOLAR_MODEL_KEEP_LOCAL=1` 이면 정리하지 않는다. 보관 기능이 꺼져 있으면(`SOLAR_MODEL_STORE=disabled`) 아무것도 지우지 않는다.

## 근거

| 수치 | 조건 (기간, 분할, 시드 수) | 출처 |
| --- | --- | --- |
| 버전 폴더 하나의 로컬 크기는 평균 65KB, MLflow 가 따로 드는 모델 사본은 평균 101KB | 2026-10-10, 한 PC 의 runtime(버전 32개: 발전소 31곳의 v1 과 하동 v2). runtime 전체 48MB 가운데 버전 폴더 2.0MB, MLflow 사본 3.2MB, 재생용 이력 CSV 42MB | `du` 로 직접 잼 |
| 두 번째 재학습으로 v3 이 운영에 오르자 로컬에는 v1, v3 만 남고 v2 는 보관소에만 남았다. 버전 폴더의 합은 133.0KB 로 그대로였다. 정리하지 않고 세 버전을 모두 두면 216.0KB 다 | 2026-10-10, 격리 runtime, 로컬 폴더 보관소, 하동하수처리장, 합성 자료(기능 확인용이며 예측 성능의 근거가 아니다) | [`model-prune-local-20261010/verification.json`](../proposal/evidence/model-prune-local-20261010/verification.json) |
| 로컬에서 지운 v2 를 이력 화면의 경로(롤백 API)로 다시 적용하자 보관소에서 복구됐고, 24시간 예측이 지우기 전과 같았다 | 같은 실행 | 같은 증빙 |
| 실제 R2 를 보관소로 켜고 재학습 두 번: v2, v3 이 만들어진 지 0 ~ 2초 뒤에 올라갔고, 로컬 v2 가 지워진 뒤 이력에서 v2 를 적용하자 0.7초에 복구되어 24시간 예측이 같았다 | 2026-10-10, 실제 R2, 격리 runtime, 합성 자료 | [`r2-prune-restore-20261010/verification.json`](../proposal/evidence/r2-prune-restore-20261010/verification.json) |
| 실제 R2 버킷에는 하동 v1 ~ v3 의 파일 9개가 있고, 내려받은 세 묶음의 해시가 모두 맞았다. v3 은 manifest 가 만들어진 지 1 ~ 2초 뒤에 올라가 있었다 | 2026-10-10, 읽기 전용(목록 조회와 내려받기만) | [`r2-readonly-20261010/verification.json`](../proposal/evidence/r2-readonly-20261010/verification.json) |

## 함께 고칠 곳

- `project/serving_app/model_store.py`(`prune_local`, `history`), `project/serving_app/registry.py`(`activate` 뒤의 정리), `project/serving_app/hourly/app.py`(이력 조회)
- `tools/hourly/archive_models.py`(`prune`), `tools/hourly/test_model_store.py`
- `docs/design/solar-ops-v01/hourly-ui.js` 와 `project/serving_app/static/hourly-ui.js`(상태 열의 `외부 보관`)
- `docs/model-storage.md`, `docs/proposal/4-architecture.md`, `docs/proposal/5-api-spec.md`, `docs/backend-runbook.md`, `AGENTS.md`, `CLAUDE.md`

## 다시 볼 조건

- MLflow 가 드는 모델 사본은 아직 정리하지 않는다. 버전 폴더보다 커서, 로컬 용량을 더 줄이려면 MLflow 의 모델 파일도 보관소로 옮기거나 지워야 한다.
- 확인한 발전소는 하동하수처리장 한 곳이다. 31곳 전체에서 여러 번 재학습이 쌓인 경우는 돌려 보지 않았다.
- 직전 버전까지만 남기는 기준이 운영에 맞지 않으면 남길 개수를 설정으로 뺀다.
