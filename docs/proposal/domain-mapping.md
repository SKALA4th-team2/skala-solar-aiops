# 시간별 도메인 매핑

현재 계약 solar_hourly_24_jma_day2_v1은 기존 일별 HAIC close/volume 계약을 대체한다.

| 입력 | 의미 | 단위/길이 |
|---|---|---|
| history.timestamp | 전날 1시간 구간 시작 | KST +09:00, 00~23시 |
| history.generation_kwh | 전날 같은 시간 발전량 | kWh,24개 |
| forecast.timestamp | 대상일 1시간 구간 시작 | 전날에 연속,00~23시 |
| shortwave_radiation | 48h 선행 구간 일사량 평균 | W/m² |
| temperature_2m / cloud_cover / wind_speed_10m | 같은 종료시각 예보 | °C / % / km/h |
| predictions.predicted_kwh | 각 1시간 발전량 | 24개 |

모델 24×9 →24×1, 특징과 고정 스케일은 [결정 0014](../decisions/0014-hourly-forecast-and-aiops.md). Close/Volume/Expected를 임의로 이름만 바꿔 사용할 수 없다. 예보 자료의 일사량 시간정렬과 선행시간이 일치해야 한다. ASOS 일별 관측 자료를 시간별 기대 발전량으로 사용하지 않는다.
