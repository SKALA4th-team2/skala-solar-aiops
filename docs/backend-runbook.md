# 시간별 백엔드·프론트 운영 안내

현재 기본 서비스는 **31개소 시간별 LSTM**이다. [결정 0014](decisions/0014-hourly-forecast-and-aiops.md)가 이전 일별 계약을 대체한다. 승인된 모델과 스케일러는 저장소의 hourly-seed에 포함되어 있다.

## 실행

모든 명령은 project/에서 실행한다.

```powershell
py -3.11 -m venv .venv
.venv\Scripts\python -X utf8 -m pip install -r requirements.txt
.venv\Scripts\python -X utf8 scripts/run_backend.py
```

기존 .venv가 있으면 재생성할 필요가 없다. 화면 http://127.0.0.1:8077/ , API 명세 http://127.0.0.1:8077/docs . 실행기는 시간별 API와 단일 학습 작업자를 함께 시작한다. API만 실행하면 자동 재학습이 진행되지 않는다. Ctrl+C는 둘 다 종료한다. 로그는 logs/api-stdout.log, worker-stdout.log, aiops-hourly.log다. /health의 contract, worker_alive, plants를 확인한다.

기본 SOLAR_MODEL_CONTRACT=solar_hourly_24_jma_day2_v1, SOLAR_STATE_DIR=project/data/runtime-hourly. 예전 serving_app.main:app은 일별 보관 구현이므로 현재 실행 명령으로 사용하지 않는다.

## API

| 메서드·경로 | 시간별 계약 |
|---|---|
| GET /plants | 승인된 31개 모델·용량 |
| GET /health | 계약·작업자 heartbeat |
| GET /ui/sample?plant_id=hadong-sewage | 실제 보관/업로드 자료의 prediction, batch 예시 |
| POST /predict | plant_id, history 24개, forecast 24개 → predictions 24개와 total_kwh |
| GET /predictions 및 /predictions/{id} | 예측 입력·출력·버전·시각의 영속 기록 |
| GET /ui/energy?plant_id=… | 최근 최대 168시간 실제·현재 모델 재생, 대상일 24개 예측 |
| POST /predict/batch-test | plant_id, rows → 시간별 예측·모니터링·조건부 작업 등록 |
| POST /data/upload | multipart plant_id와 file; 자동 모니터링 |
| GET /data/status?plant_id=… | 최신 시간별 업로드 상태 |
| GET /plants/{plant_id}/status | 모델·모니터링·작업·업로드 |
| POST /plants/{plant_id}/retrain | Batch 형식, 최소 696시간, 수동 재학습 큐 등록 |
| GET /jobs 또는 /jobs/{id} | queued/running/succeeded/rejected/failed |
| POST /plants/{plant_id}/rollback | {"version":1}; 저장된 통과 버전으로 복귀 |
| POST /portfolios/all-approved/predict | inputs: {plant_id: Predict 본문}; 동일 대상시간의 31개 가상 합계 |
| GET /preview-api/dashboard/{resource} | current/history/alerts/info/dataset/metrics/timeseries/predictions |
| GET /logs 및 /logs/aiops-hourly.log | 시간별 AIOps 이벤트 로그 |

history 행은 timestamp, generation_kwh. forecast 행은 timestamp, shortwave_radiation, temperature_2m, cloud_cover, wind_speed_10m. timestamp는 2026-02-27T00:00:00+09:00 같은 KST 구간 시작이다. 두 배열은 전날 00~23시, 대상일 00~23시이며 빈 시간·중복·순서 오류를 거절한다. 야간 0은 정상 값이다. 발전량은 1시간 kWh, 기상 단위는 각각 W/m², °C, %, km/h다. 예보는 학습과 동일한 48시간 선행 자료여야 한다.

CSV 열 순서:

```csv
timestamp,generation_kwh,shortwave_radiation,temperature_2m,cloud_cover,wind_speed_10m
```

UTF-8, 최소 48행, 최대 8760행/5MB, 완전한 연속 날짜(24의 배수). 모든 행에 실제 발전량과 해당 시간의 보관 예보가 있어야 한다. 일별 Date/Close/Volume 파일은 사용할 수 없다. 새 업로드의 종료시각은 기존보다 오래될 수 없고 동일 종료시각에서 다른 내용을 덮어쓸 수 없다. 향후 예보만으로 예측할 때는 /predict에 history/forecast를 분리해 보낸다.

## 모델·재학습

`data/runtime-hourly/models/{plant_id}/versions/{version}/` 아래 model.keras, scaler.pkl, manifest.json을 항상 함께 보관한다. current.json은 승인된 버전 포인터다. `.pkl`만으로 LSTM을 서빙하지 않는다. scaler.pkl은 고정 정규화와 기준선 계수를 저장하며 재학습에서 다시 fit하지 않는다. MLflow native TensorFlow 등록본을 다시 로드해 출력을 비교한다.

최근 7일·주간 최소 48시간의 예보 대비 저하와 오차를 감시한다. 주간 연속 저발전은 재학습 대신 점검 보류다. 자동 큐에 들어가려면 새 데이터 29일과 기존 훈련기간 이후라는 조건도 만족해야 한다. 보관 자료 재생은 기존 학습 기간에 포함되므로 학습 기간 중복 보류가 정상이다. 설비 고장 확정 진단이나 ASOS 관측 보정 검사는 아니다.

최초 학습 2024년 이전/검증 2024하반기/평가 2025. 성능 통과 후 최신 데이터 재학습 모델을 배포하므로 화면 과거 재생 RMSE는 독립 평가 성능이 아니다. 현재 수집 보관자료는 2026-02-27까지이며 오늘의 실시간 예측이라고 표시하지 않는다.

## 재생성·검증

```powershell
.venv\Scripts\python -X utf8 ../tools/hourly/prepare.py
.venv\Scripts\python -X utf8 ../tools/hourly/train.py --workers 2
.venv\Scripts\python -X utf8 ../tools/hourly/finalize.py
.venv\Scripts\python -X utf8 ../tools/hourly/verify.py
node ../tools/design/publish-runtime.mjs
```

prepare는 tools/hourly/candidates.json의 기존 승인 등록부와 원본 시간별 실적·JMA 보관 파일을 필요로 한다. train은 완료 result.json을 재사용한다. 처음부터 다시 실험하려면 별도 실행 디렉터리로 코드를 구성하고 기존 증빙을 보존한다. finalize는 품질 통과 모델만 운영 목록에 반영한다. verify는 운영 모델을 읽고 별도 runtime-verify-*에 실제 재학습을 수행해 운영 가중치를 바꾸지 않는다. 생성 증빙은 docs/proposal/evidence/hourly_20261007/이다.

다른 PC에서는 저장소를 clone/pull하면 승인된 hourly-seed도 함께 받는다. 별도 ZIP 설치 없이 [제출 안내](submission/README.md)에 따라 실행한다. 실행기가 해당 PC 경로의 MLflow에 모델을 다시 등록한다. 승인 seed만 Git에 포함하며 운영 DB와 재학습 산출물은 제외한다. Docker 명령은 `docker compose -f serving_app/docker-compose.yml up --build`이며 포트는 8099다. GitHub Actions의 Linux Docker에서 실제 빌드·31개 예측·자동 재학습·롤백·재시작 후 예측 기록 보존을 확인했다. 실행 근거와 모델 묶음은 [제출 안내](submission/README.md)를 따른다.


## 인센티브 기준 참고 평가

발전 현황 화면에서 선택 발전소와 최근 24/72/168시간에 대해 네 가지를 확인한다: 시간별 용량 기준 절대 예측오차율과 대상 시간 평균, 4%·6% 이하 시간 비율, 평가 대상·제외 시간, 기준단가를 적용한 모의 금액. 6% 이하 비율은 4% 이하 시간을 포함하며 분모는 평가 대상 시간이다. 평가 대상이 없으면 오차율과 비율은 미산정(null/—)이고 금액은 0원이다.

2026-07-25 공개 전력시장운영규칙 별표2의 예측제도 기준을 고정한 시나리오다. 시간별 설비이용률 ≥10%에 대해 용량 기준 오차율 ≤4%는 4원/kWh, 4% 초과~6% 이하는 3원/kWh, 그 외는 0원/kWh를 적용한다. 실제 발전량(kWh)을 유효용량(kW) × 1시간으로 나눈 값이 설비이용률이다. 두 차수 예측이 있을 때는 각 절대오차율의 평균을 사용한다. 현재 화면은 제출 1·2차 기록이 없어 단일 예측을 두 차수의 대용으로 사용한다.

실적 발전량을 거래량의 대용으로 쓰며, 출력제어·고장·정비 미제공 시 없음으로 가정한다. 기본 계수는 1.0이고 제주 입찰·예측제도 동시 참여 가정 시 0.5를 선택할 수 있다. 선택은 참여 사실을 확인하는 것이 아니다. 개소별 참고값으로, 서로 다른 지역·등록자원을 합쳐 참여자격을 확정하지 않는다. 현재 운영 모델의 과거 재생이므로 독립 평가나 실제 지급액으로 표시하지 않는다.

구현: serving_app/hourly/incentives.py. `GET /ui/incentives?plant_id=hadong-sewage&hours=24&coefficient=1`로 같은 결과와 시간별 내역·가정을 조회한다. hours는 24/72/168, coefficient는 1/0.5만 허용한다. 기존 `/ui/energy`에도 기간별 incentives를 포함한다.

[적용 기준 원문, 별표2 Ⅴ](https://www.kpx.or.kr/boardDownload.es?bid=0030&list_no=77795&seq=4). 규칙 적용 버전은 kpx-2026-07-25-scenario-v1이며 최신 개정 자동 반영은 하지 않는다.

리뷰 보완: 인센티브 응답은 rule_profile=kpx-2026-07-25-scenario-v1, le4/le6 지표를 사용한다. 과거 날짜에도 이 규칙을 고정 적용하므로 과거 지급액 복원이 아니다. training_scope에 total_hours, training_overlap_hours, label을 제공하며 선택 구간의 학습 포함 여부를 표시한다. 감시 응답 state는 기존 작업의 실제 status를 유지한다. existing_job_terminal은 완료 작업 재조회로 신규 학습이 없다는 뜻이다.
