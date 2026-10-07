# 도메인 매핑표

HAIC 스켈레톤의 개념을 태양광 발전량 예측으로 바꾼 표다. 통합가이드 본문 7번의 양식을 따른다.

"우리 팀" 열은 [결정 기록](../decisions/)의 **제안**을 옮긴 것이다(2026-10-07). 0002의 API 입력 계약은 사용자 승인으로 확정했다. 나머지 제안은 팀 확정 전이다. 확정하면 "상태" 칸을 "확정"으로 바꾸고, 값이 달라지면 이 표와 기획서의 해당 칸을 함께 고친다.

| 템플릿 개념 (HAIC) | 우리 팀: 태양광 발전량 예측 | 상태 |
| --- | --- | --- |
| 예측 대상: 다음날 종가 | 발전소 한 곳의 다음 날 하루 발전량 한 값 (kWh) | API 입력 계약 확정 [0002](../decisions/0002-inputs-and-prediction-time.md) |
| 입력 시퀀스: 최근 20거래일 (close, volume) | 이어진 최근 20일의 (그날의 하루 발전량 kWh, **다음 날**에 대한 하루 전 일사량 예보 MJ/m²). 대상일 전날 20시 이후에 예측한다 | API 입력 계약 확정 [0002](../decisions/0002-inputs-and-prediction-time.md) |
| 데이터 공급: 대시보드 CSV 업로드 | 대시보드 CSV 업로드. 파일은 `datasets/hadong_upload_forecast_jma.csv`. 열 이름(`Date, Close, Volume`)과 필드 이름은 그대로 두고 뜻과 단위를 바꿔 읽는다 | API 입력 계약 확정 [0002](../decisions/0002-inputs-and-prediction-time.md) |
| 배포 게이트: RMSE ≤ $4.00 | 같은 시험 날짜의 7일 평균 RMSE 의 80% 이하이면서 규칙C RMSE 의 105% 이하, 치우침 ±10% 이내. 지금의 자료면 47.5kWh 이하 | 제안 [0005](../decisions/0005-deployment-gate.md) |
| 드리프트 신호: 변동성 3배 급변 | 발전소의 출력 수준 저하. 날마다 최근 41일을 보고, 뒤 21일의 성능 지표(실제 ÷ 관측 날씨로 계산한 기대 발전량)가 고정 기준선보다 7.5% 넘게 낮을 때 알린다. 시연에서는 발전량에 0.86 을 곱해 만든다 | 제안 [0006](../decisions/0006-monitoring-metric-and-thresholds.md), [0009](../decisions/0009-demo-plan.md) |
| 재학습: 최근 21거래일 fine-tuning | 최근 41행(입력 20일 + 판정 21일)으로 이어서 학습. 앞 20일도 내려간 수준일 때만 건다. 정지나 보류인 날이 섞여 있으면 미룬다 | 제안 [0008](../decisions/0008-retraining-and-version-switch.md), [0007](../decisions/0007-facility-vs-model-branch-and-alerts.md) |
| 알림: `aiops.log` 의 `[WARN]` | `aiops.log` 의 문장. 수준 저하, 게이트 실패, 설비 점검 필요를 문장으로 구분한다. 밖으로 보내는 알림은 없다 | 제안 [0007](../decisions/0007-facility-vs-model-branch-and-alerts.md) |
| 이해관계자: 투자 분석가, 운영자 | 예측 사용자는 가상의 전력 중개 사업자의 운영 담당자. 서비스 운영자는 솔루션을 공급하는 우리 팀. 점검 알림을 받는 사람은 설비 담당자 | 제안 [0001](../decisions/0001-customer-and-scope.md) |

통합가이드의 표에 없지만 함께 정한 것이다.

| 개념 | 우리 팀 | 상태 |
| --- | --- | --- |
| 오차의 지표와 용량 | RMSE(하루 kWh), 합계 오차율, 치우침. 용량 55kW. 제도의 오차율 4%, 6% 는 배경으로만 쓴다 | 제안 [0003](../decisions/0003-capacity-and-error-metrics.md) |
| 운영 목표 | 예측 응답 1초 이하, 예측 시간대의 가용성 99% 이상, 기준 예측 대비 품질, 수준 저하를 4주 안에 알림 | 제안 [0004](../decisions/0004-service-level-objectives.md) |
| 설비 이상과 모델 품질 저하 | 정지와 보류는 점검 알림과 재학습 보류. 그 밖의 수준 저하는 알림과 재학습 후보 | 제안 [0007](../decisions/0007-facility-vs-model-branch-and-alerts.md) |
| 버전의 교체와 확인 | 승격 뒤 서빙 모델을 다시 불러온다. 응답에 레지스트리의 버전 번호를 싣는다 | 제안 [0008](../decisions/0008-retraining-and-version-switch.md) |

## 여러 발전소와 포트폴리오의 개념 (확장 제안)

위의 두 표는 발전소 한 곳의 서비스다. HAIC 스켈레톤에는 종목이 하나였고 "묶음"에 해당하는 개념이 없다. 여러 발전소로 넓힐 때 새로 생기는 개념을 따로 적는다. 모두 결정 기록 [0010](../decisions/0010-multi-plant-scope-and-scheme.md) ~ [0012](../decisions/0012-single-pc-retrain-jobs.md)의 **제안**이고 구현하지 않았다. 설계는 [확장 문서](multi-plant-extension.md)에 있다.

| 개념 | 템플릿 (HAIC) | 지금: 발전소 한 곳 | 넓힌 뒤: 여러 발전소 | 상태 |
| --- | --- | --- | --- | --- |
| 예측의 대상 | 종목 하나 | 발전소 한 곳. 식별자가 없다 | 발전소(`plant_id`)마다 따로. 기본 발전소는 `hadong-sewage` | 제안 [0011](../decisions/0011-multi-plant-forecast-and-identity.md) |
| 묶음 | 없다 | 없다. 고객의 묶음은 말로만 있다 | 포트폴리오(`portfolio_id`)와 구성 버전. **가상의 묶음**이라고 적는다 | 제안 [0010](../decisions/0010-multi-plant-scope-and-scheme.md) |
| 묶음의 값 | 없다 | 없다 | 같은 대상일의 발전소별 예측의 합(하루 kWh). 빠진 발전소가 있으면 합계라고 부르지 않는다 | 제안 [0011](../decisions/0011-multi-plant-forecast-and-identity.md) |
| 설비 용량 | 없다 | 55kW. 코드의 입력 상한(1,320kWh)에 들어 있다 | 발전소 등록부의 값(단위, 종류, 근거, 유효 기간). 묶음은 중복 없이 더한 **설비 용량 합계**(kW, MW). 발전량의 합과 다르다 | 제안 [0010](../decisions/0010-multi-plant-scope-and-scheme.md) |
| 제도의 기준 | 없다 | 배경으로만 쓴다 | 묶음 안 태양광·풍력의 설비 용량 합계 20MW **초과**. 우리 합계와 견준 값은 참고다. 요건을 채웠다고 쓰지 않는다 | 제안 [0010](../decisions/0010-multi-plant-scope-and-scheme.md) |
| 데이터 공급 | CSV 하나를 올린다 | CSV 하나. 가장 최근 파일을 쓴다 | 발전소와 자료 종류를 주어 올린다. 발전소별 폴더에서 고른다 | 제안 [0011](../decisions/0011-multi-plant-forecast-and-identity.md) |
| 모델과 스케일러 | 하나씩 | 하나씩(`HAIC_Predictor`, `scaler.pkl`) | 발전소마다 하나씩(`solar-daily-<plant_id>`). 묶음 기록으로 짝을 확인한다 | 제안 [0011](../decisions/0011-multi-plant-forecast-and-identity.md) |
| 배포 게이트 | 모델 하나에 한 번 | 모델 하나에 한 번 | 발전소마다 따로. 한 곳이 막혀도 다른 곳은 그대로. 합계는 "검증됨" 표시의 조건으로만 | 제안 [0011](../decisions/0011-multi-plant-forecast-and-identity.md) |
| 드리프트 신호 | 종목 하나의 변동성 | 발전소 한 곳의 출력 수준 저하 | 발전소별 수준 저하. 여럿이 함께 내려가면 공통 요인(날씨, 예보 입력). 구성의 변경과 자료의 누락은 드리프트가 아니다 | 제안 ([확장 문서 8.3절](multi-plant-extension.md#83-aiops)) |
| 재학습 | 요청 안에서 바로 | 요청 안에서 바로 | 조건을 채운 발전소만, 작업으로 떼어 한 번에 하나씩 | 제안 [0012](../decisions/0012-single-pc-retrain-jobs.md) |
| 알림 | 로그 한 줄 | 로그의 문장 | 문장에 발전소, 모델, 자료, 작업의 식별자를 싣는다 | 제안 ([확장 문서 8.3절](multi-plant-extension.md#83-aiops)) |
| 품질의 지표 | RMSE(달러) | RMSE(하루 kWh), 합계 오차율, 치우침 | 발전소별 지표와, 예측 합계와 실제 합계로 구한 포트폴리오 지표를 같은 대상일에서 함께. 발전소별 RMSE 를 더하지 않는다 | 제안 [0011](../decisions/0011-multi-plant-forecast-and-identity.md) |

## 지금의 코드와의 거리

표의 "우리 팀" 열은 설계다. 커밋 `58d6ff8` 의 `project/` 는 아직 HAIC 스켈레톤 그대로다. 게이트와 드리프트의 기준이 4.00 이고, 드리프트 시뮬레이션이 변동성을 3배로 키운 무작위 가격이며, 빈칸 11곳이 남아 있다. 무엇이 돌고 무엇이 돌지 않는지는 [검증 기록](evidence/validation.md)에 있다.

## 표가 정해지면 함께 정해지는 것

| 표의 칸 | 정해지는 것 | 고칠 곳 |
| --- | --- | --- |
| 입력 시퀀스 | 요청 스키마, 업로드 파일의 열과 검증 | `serving_app/schemas.py`, `serving_app/routers/data.py`, `datasets/` |
| 배포 게이트 | 게이트 지표와 기준값 | `serving_app/train_and_register.py` |
| 드리프트 신호 | 판정 방법, 임계값, 시뮬레이션 배치 | `serving_app/monitoring/drift_detector.py`, `serving_app/routers/predict.py`, `scripts/simulate_drift.py` |
| 재학습 | 재학습에 쓰는 데이터 범위와 성공 기준 | `serving_app/monitoring/retrain_trigger.py` |
| 알림 | 로그의 문장 | `serving_app/monitoring/retrain_trigger.py`, `serving_app/static/index.html` |

고칠 곳의 상세는 [④ 의 6절](4-architecture.md#6-haic-스켈레톤에서-바꿀-곳과-그대로-둘-곳)에, 함께 맞출 곳의 전체 목록은 [`../../AGENTS.md`](../../AGENTS.md)의 표에 있다.

## FastAPI 구현 진행 (2026-10-07)

이슈 #6에서 날짜가 연속인 20일, 발전량 0~1,320kWh, 다음 날 예보 0~45MJ/m², 대상일 응답과 업로드 검증을 적용했다. (20, 2) 모델 구조는 유지했다. 배치·AIOps와 학습·배포 정책은 각 후속 담당 작업이다. 위 초기 코드 대조는 `58d6ff8` 당시의 기록이다.

이슈 #7에서 배치 API도 같은 입력 의미로 바꿨다. `SIMULATED_VOLUME`과 대시보드 `DEFAULT_BASE_PRICE`를 제거하고 실제 CSV의 예보를 사용한다. 날짜·기대 발전량은 AIOps 어댑터에만 전달한다. 대시보드의 RMSE 임계값 판정은 제거했고 서버의 판정 결과만 표시한다. 기존 HAIC 감시 함수와 임계값은 보존하되 태양광 API에서 호출하지 않는다.
