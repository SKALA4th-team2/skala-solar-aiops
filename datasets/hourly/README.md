# 실제 시간별 학습 자료

생성: project/에서 `.venv\Scripts\python -X utf8 ../tools/hourly/prepare.py`.

원본 한국남부발전 시간별 CSV의 1~24시 발전량을 사용한다. 하동은 datasets/raw/data_15043409.csv, 나머지는 datasets/multi_plant/raw/{dataset_id}.csv이며 호기 열로 분리한다. 일합계와 시간합계를 대조하고 원본의 kW라는 표기는 1시간 구간 발전량 kWh로 해석한다. 이는 원자료 구조에 따른 해석이며 정산 계량 인증이 아니다. 기상은 datasets/plant_forecasts/raw/{region}_{year}.json.gz의 previous_day2 자료와 meta의 원본 SHA256을 검증한다. 출처·이용 조건은 [전체 데이터 안내](../README.md)와 [예보 자료 안내](../plant_forecasts/README.md)를 따른다. Open-Meteo 출처 표시를 프론트에 유지한다.

열: timestamp(KST +09:00 구간 시작), generation_kwh, shortwave_radiation(W/m²), temperature_2m(°C), cloud_cover(%), wind_speed_10m(km/h). 일사량 유효 종료시각을 -1시간 이동한다. 다른 기상 변수는 같은 예보 종료시각의 값이다. 하루 합계를 분할한 데이터가 아니다.

날짜별 24시간 완전성, 일합계 일치, 발전량 0~설비용량, 예보 물리 범위, 충돌 중복, 이전 하루 존재를 검사한다. 결측 날짜를 건너뛰어 LSTM 창을 이어 붙이지 않는다. 학습 최소365일·검증90일·평가180일이 필요하다. screening.json에 제외 날짜 수·원본 및 생성 SHA·지역격자 출처를 기록한다.

데이터 자격 33개, 시간별 모델 성능 통과31개. 신인천전망대·용수리는 시간별 품질 게이트 미달로 서비스에서 제외됐다. plants/*.csv는 재생성 가능하므로 Git 제외다. source CSV와 후보 평가 증빙은 제외 이유를 재현할 수 있도록 보관하고 active catalog/seed에는 통과31개만 포함한다.

[결정 0014](../../docs/decisions/0014-hourly-forecast-and-aiops.md)의 시각·선행시간·평가·운영 정책을 따른다. 현재 파일의 최종 완전일은 2026-02-27이다. 지역격자 예보는 현장 시간별 관측이 아니다.
