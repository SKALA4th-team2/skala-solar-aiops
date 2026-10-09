# 하동 재학습 기능 테스트 자료

`hadong-synthetic-drift.csv`는 실제 관측 자료가 아닌 합성 자료다. 자동 재학습과 모델 버전 생성·R2 보관 기능 확인에만 사용하고 예측 성능이나 제도 참여 근거로 사용하지 않는다.

생성 도구는 `tools/hourly/make_retrain_sample.py`다. 명령은 `project/`에서 실행한다.

```powershell
.venv\Scripts\python -X utf8 ../tools/hourly/make_retrain_sample.py
```

현재 하동 모델과 `data/runtime-hourly/history/hadong-sewage.csv`의 최근 연속 29일을 읽는다. 기상 열은 보관 이력에서 가져오고, 시각은 기존 학습 종료와 최근 업로드 종료 중 더 늦은 날의 다음 날부터 이동한다. 발전량은 설비 용량 상한을 적용한 일사량 기준선의 50%로 합성한다. 날씨와 시각이 이동한 자료이므로 실제 해당 기간의 예보·발전 실적이 아니다. 기반 이력의 출처·이용 조건은 `datasets/hourly/README.md` 및 `datasets/README.md`를 따른다. 추가 수집은 하지 않는다.

열은 timestamp(+09:00, 1시간 구간 시작), generation_kwh(1시간 발전량), shortwave_radiation(W/m²), temperature_2m(°C), cloud_cover(%), wind_speed_10m(km/h) 순서다. 696행이며 날짜 경계·연속성·용량 상한·드리프트 판정을 검사한 뒤 생성한다. 동명 JSON에 원본 경로·SHA·원래 기간·변환 방법·사용 모델·판정·CSV SHA를 남긴다. 파일은 손으로 수정하지 않고 도구로 재생성한다.

## 화면 테스트

운영 runtime(`data/runtime-hourly`, 8077)에 올리지 않는다. 업로드는 그 runtime의 최신 실적을 합성 자료로 바꾸고, 통과하면 운영 버전도 바꾼다. 더 오래된 종료 시각의 파일은 409로 거절되므로 2027-03-28까지의 합성 자료를 올린 뒤에는 실제 자료(2026-02-27까지)를 다시 올릴 수 없고, 모델을 롤백해도 업로드 자료는 원복되지 않는다. 그래서 별도 runtime과 포트에서 확인한다.

1. `project/`에서 별도 runtime으로 앱과 작업자를 실행한다. 보관소는 다른 폴더(local)를 쓴다.

   ```powershell
   $env:SOLAR_STATE_DIR = "$PWD\data\runtime-retrain-test"
   $env:SOLAR_LOG_DIR = "$PWD\logs\retrain-test"
   $env:SOLAR_MODEL_STORE = "local"
   $env:SOLAR_MODEL_ARCHIVE_DIR = "$PWD\data\model-archive"
   .venv\Scripts\python -X utf8 scripts/run_backend.py --port 8078
   ```

   ```bash
   SOLAR_STATE_DIR="$PWD/data/runtime-retrain-test" SOLAR_LOG_DIR="$PWD/logs/retrain-test" \
   SOLAR_MODEL_STORE=local SOLAR_MODEL_ARCHIVE_DIR="$PWD/data/model-archive" \
   .venv/bin/python -X utf8 scripts/run_backend.py --port 8078
   ```

2. http://127.0.0.1:8078/ 에서 발전소를 하동하수처리장으로 선택한다.
3. CSV 업로드에서 `hadong-synthetic-drift.csv`를 선택해 업로드한다.
4. 서비스 운영에서 작업 대기 → 학습·검증 → 운영 반영 상태를 확인한다.
5. 이력 · 알림에서 새 버전과 운영 적용 결과를 확인한다. 검증 또는 보관 실패 시 기존 버전을 유지한다.

끝나면 서버를 내리고 `data/runtime-retrain-test`를 지우면 처음 상태로 돌아간다. 이 폴더와 `data/model-archive`는 Git에 올라가지 않는다. 실제 R2까지 확인하려면 SOLAR_MODEL_STORE를 r2로 바꾼다. 이때 합성 자료로 만든 모델이 버킷에 남는다.

같은 종료 시각의 파일을 다시 올리면 기존 작업을 재사용하며 새 모델을 매번 만들지 않는다. 새 작업이 필요하면 현재 학습 종료와 업로드 종료를 반영하여 도구로 다시 생성한다.

2026-10-08 검증: 별도 임시 runtime에서 CSV 검사·작업 등록·5 epoch 학습·기존 게이트 통과·후보 모델 파일 생성을 확인했다. 모델 등록과 운영 적용은 모의 처리했고 실제 R2에는 새 후보를 업로드하지 않았다. [검증 기록](../../../docs/proposal/evidence/r2-local-20261008/retrain-sample-validation.json).

2026-10-09 검증: 위 절차와 같은 별도 runtime과 로컬 폴더 보관소에서 업로드 → 드리프트 판정 → 재학습 → 게이트 통과 → 보관 → v2 운영 반영을 실제로 끝까지 실행했다. 실제 R2에는 연결하지 않았다. [검증 기록](../../../docs/proposal/evidence/model-store-local-20261009/verification.json).

현재 CSV는 2027-02-28부터 2027-03-28까지 696시간이며, 하동 v1을 기반으로 격리 재학습을 실제 실행해 기존 승인 게이트 통과를 확인했다. CSV SHA와 검증 결과는 동명 JSON 및 검증 기록에 연결한다. 생성 도구는 드리프트 조건까지 검사하므로 다른 기간으로 재생성한 파일은 학습 게이트도 별도로 검증해야 한다.
