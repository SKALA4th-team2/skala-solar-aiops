# 도메인 매핑표

HAIC 스켈레톤의 개념을 태양광 발전량 예측으로 바꾼 표다. 통합가이드 본문 7번의 양식을 따른다.

"우리 팀" 열은 [결정 기록](../decisions/)의 **제안**을 옮긴 것이다(2026-10-07). 팀이 아직 확정하지 않았다. 확정하면 "상태" 칸을 "확정"으로 바꾸고, 값이 달라지면 이 표와 기획서의 해당 칸을 함께 고친다.

| 템플릿 개념 (HAIC) | 우리 팀: 태양광 발전량 예측 | 상태 |
| --- | --- | --- |
| 예측 대상: 다음날 종가 | 발전소 한 곳의 다음 날 하루 발전량 한 값 (kWh) | 제안 [0002](../decisions/0002-inputs-and-prediction-time.md) |
| 입력 시퀀스: 최근 20거래일 (close, volume) | 이어진 최근 20일의 (그날의 하루 발전량 kWh, **다음 날**에 대한 하루 전 일사량 예보 MJ/m²). 대상일 전날 20시 이후에 예측한다 | 제안 [0002](../decisions/0002-inputs-and-prediction-time.md) |
| 데이터 공급: 대시보드 CSV 업로드 | 대시보드 CSV 업로드. 파일은 `datasets/hadong_upload_forecast_jma.csv`. 열 이름(`Date, Close, Volume`)과 필드 이름은 그대로 두고 뜻과 단위를 바꿔 읽는다 | 제안 [0002](../decisions/0002-inputs-and-prediction-time.md) |
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
