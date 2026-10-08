# ⑤ 시간별 API 계약

현재 규격은 [운영 안내](../backend-runbook.md)의 API 표와 실행 서버 `/openapi.json`이다. 이전 20일 date/close/volume 계약은 시간별 서비스에서 거절한다.

`POST /predict`: plant_id, history[{timestamp,generation_kwh}] 24개, forecast[{timestamp,shortwave_radiation,temperature_2m,cloud_cover,wind_speed_10m}] 24개. 전날과 대상일 모두 00~23시의 정확히 연속된 KST(+09:00) 구간 시작시각이어야 한다. output predictions[{timestamp,predicted_kwh}] 24개와 total_kwh, model_version, contract를 반환한다. total_kwh는 24개 출력의 합이며 개별 출력은 1시간 kWh다.

기상 단위 W/m², °C, %, km/h. 48시간 선행 예보를 입력한다. 구간 결측·중복·시간대 생략·용량 상한 초과·비유한값·구 계약 입력은 422로 거절한다. 미등록 발전소 조회는404, 모델 로드 실패는503이다. 야간 0은 결측이 아니다.

`POST /predict/batch-test`의 rows는 실적과 같은 시간 예보 6열을 합친 행이다. 최소48, 최대8760, 24의 배수다. 최근7일 검사에는 주간48시간이 필요하며 재학습은696시간이 필요하다. 업로드는 같은 CSV 계약과 plant_id를 multipart로 전송한다. 같은 종료시각의 상충 업로드/작업은409다.

`POST /portfolios/all-approved/predict`는 inputs의 키와 각 Predict.plant_id가 같아야 한다. 모든 구성원의 예측 대상 24시간이 같아야 하고, 31개소 중 빠진 개소가 있으면 complete=false, predictions=null, partial_predictions만 제공한다. 가상 합계이며 인센티브 정산 API가 아니다.

작업 조회·롤백·화면 API와 실제 예제는 [운영 안내](../backend-runbook.md), 채택 근거는 [결정 0014](../decisions/0014-hourly-forecast-and-aiops.md)를 참조한다.

## 예측 영속 기록

성공한 단건·배치 응답에 prediction_id와recorded_at이 포함된다. GET /predictions?plant_id=…&limit=50은 최근기록을 반환하며 limit은1~500이다. GET /predictions/{id}는 당시요청·응답·모델버전·입력SHA·기록시각을반환한다. 기록은SQLite에저장되어프로세스재시작후에도유지된다. 새단건요청은새ID이며 과거재생배치는kind=retrospective_batch로구분한다.


## 인센티브 기준 참고 평가

발전 현황 화면에서 선택 발전소와 최근 24/72/168시간에 대해 네 가지를 확인한다: 시간별 용량 기준 절대 예측오차율과 대상 시간 평균, 6%·8% 이하 시간 비율, 평가 대상·제외 시간, 기준단가를 적용한 모의 금액. 8% 이하 비율은 6% 이하 시간을 포함하며 분모는 평가 대상 시간이다. 평가 대상이 없으면 오차율과 비율은 미산정(null/—)이고 금액은 0원이다.

2025-05 공개 전력시장운영규칙 별표2의 예측제도 기준을 고정한 시나리오다. 시간별 설비이용률 ≥10%에 대해 용량 기준 오차율 ≤6%는 4원/kWh, 6% 초과~8% 이하는 3원/kWh, 그 외는 0원/kWh를 적용한다. 실제 발전량(kWh)을 유효용량(kW) × 1시간으로 나눈 값이 설비이용률이다. 두 차수 예측이 있을 때는 각 절대오차율의 평균을 사용한다. 현재 화면은 제출 1·2차 기록이 없어 단일 예측을 두 차수의 대용으로 사용한다.

실적 발전량을 거래량의 대용으로 쓰며, 출력제어·고장·정비 미제공 시 없음으로 가정한다. 기본 계수는 1.0이고 제주 입찰·예측제도 동시 참여 가정 시 0.5를 선택할 수 있다. 선택은 참여 사실을 확인하는 것이 아니다. 개소별 참고값으로, 서로 다른 지역·등록자원을 합쳐 참여자격을 확정하지 않는다. 현재 운영 모델의 과거 재생이므로 독립 평가나 실제 지급액으로 표시하지 않는다.

구현: serving_app/hourly/incentives.py. `GET /ui/incentives?plant_id=hadong-sewage&hours=24&coefficient=1`로 같은 결과와 시간별 내역·가정을 조회한다. hours는 24/72/168, coefficient는 1/0.5만 허용한다. 기존 `/ui/energy`에도 기간별 incentives를 포함한다.

[적용 기준 원문, 81~83쪽](https://marketrule.kpx.or.kr/lmxdata/attach/2025/5/upload_5127126665285383397_p3.pdf). 규칙 적용 버전은 kpx-2025-05-scenario-v1이며 최신 개정 자동 반영은 하지 않는다.
