# 다개소 시간별 자료 계약

plant_id는 서비스에서 승인한 개소의 고정 식별자다. 하동은hadong-sewage,나머지는원본데이터ID와호기로 구성한다. capacity_kw는 설비용량이며 시간별발전량kWh와구분한다. 운영목록은 runtime-hourly/catalog.json,재현용 후보목록은 tools/hourly/candidates.json이다.

모델·스케일러·manifest는 같은 버전에 저장하고 manifest의plant_id,contract,version,model_name과SHA를 확인한다. 실패 개소 모델은 운영목록·seed에서 제외한다. source ID,원본 SHA,지역격자,시간자료 SHA를 screening.json으로 추적한다.

CSV의6열은 timestamp,generation_kwh,shortwave_radiation,temperature_2m,cloud_cover,wind_speed_10m 순서다. timestamp는KST(+09:00)구간시작. 발전량kWh,예보W/m²·°C·%·km/h. 24개가하루이며 완전한연속날짜를요구한다. 자세한 입력·오류·정규화 계약은 [API](5-api-spec.md), [시간별 자료](../../datasets/hourly/README.md), [운영 안내](../backend-runbook.md)에 있다.
