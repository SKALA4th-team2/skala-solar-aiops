> **2026-10-07 시간별 전환 — 현행:** 현재 시간별학습은 raw/*.json.gz의 previous_day2를 사용한다. 기존 daily previous_day1 생성물과 입력시각이 다르므로 혼용하지 않는다. [운영 안내](../../docs/backend-runbook.md) · [결정0014](../../docs/decisions/0014-hourly-forecast-and-aiops.md). 이하 이전 계약·수치는 설계/검증 이력이며 현행 시간별 계약보다 우선하지 않는다.

# 발전소 지역별 과거 예보

Open-Meteo Previous Runs API의 `models=jma_msm`을 명시해 저장했다. 관측 ASOS나 재분석 데이터가 아니다. `2018-01-01`~`2026-02-28`을 조회하며 **실제 값이 있는 기간은 `coverage.csv`를 기준**으로 한다. API가 빈 값으로 돌려준 과거 기간도 그대로 보존한다.

## 파일

발전소별 파일은 [INDEX.md](INDEX.md)에서 찾는다.

- `raw/{region}_{year}.json.gz`: API 응답 원본(압축). 시간별 6개 변수 × 24/48시간 선행 예보.
- `raw/*.meta.json`: 요청 URL·모델·조회기간·수집 UTC 시각·원본 SHA256. 수집 시각은 당시 예보 발표 시각이 아니다.
- `locations.json`: 13개 지역 대표 좌표와 출처. 같은 지역 발전소가 같은 예보를 공유한다. **발전소별 정밀 좌표 매칭 자료가 아니다.** 삼척 시내와 원덕읍 등 지역 안에서도 거리가 있을 수 있으므로 위치 오차를 고려해야 한다.
- `plant_mapping.json`: 기존 하동 및 추가 발전소/호기의 지역 매핑. 월별 실적·단위 미확인 원본도 지역 매핑은 보관한다.
- `geocoding/`: 좌표 확인용 지명 API 응답. 영월 검색의 불일치 응답은 사용하지 않고 기상청 영월 관측소 좌표를 쓴다.
- `daily/{region}.csv`: 대상 날짜별 예보 집계와 변수별 유효 시간 수.
- `training/{plant_id}.csv`: 발전 실적 날짜에 **그 날짜를 예측한 예보**를 연결한 호기별 파일. 기존 모든 발전 날짜를 유지하며 예보 없는 기간은 결측이다.
- `coverage.csv`: 지역·변수·선행시간별 실제 일별 데이터의 시작/끝/건수.
- `validation.json`, `verification.json`: 수집 범위 및 원본 재집계·날짜 결합 검증 결과.

## 열과 단위

`target_date`는 예측 대상일(KST)이다. `gen_kwh`는 그날의 발전량 정답이며 **입력 변수로 그대로 넣지 않는다.** `generation_valid`가 있는 파일은 기존 발전 실적 품질 판정을 유지한다. 예보가 완전하다고 발전 실적의 품질까지 보장되는 것은 아니다.

| 변수 접두사 | 일별 집계 | 단위 |
| --- | --- | --- |
| shortwave_radiation | 시간평균 W/m² 24개 합 × 0.0036 | MJ/m² |
| temperature_2m | 시간별 값의 평균 | °C |
| sunshine_duration | 시간별 초 합 ÷ 3600 | 시간 |
| cloud_cover | 시간별 값의 평균 | % |
| precipitation | 시간별 강수량 합 | mm |
| wind_speed_10m | 시간별 풍속 평균 | km/h |

각 접두사 뒤에 `_previous_day1` 또는 `_previous_day2`가 붙는다. `_valid_hours` 열은 해당 지역 날짜 00~23시의 값이 존재하는 시간 수(0~24)다. 24개가 모두 있을 때만 일별 값을 만든다. `forecast_day1_complete`, `forecast_day2_complete`는 각각 6개 변수의 완전성 표시이며 누수 검증 통과 표시가 아니다. 결측 보간, 재분석 대체, 다른 선행시간으로 대체하지 않는다.

## 학습 시 시간 기준

`previous_day1`은 **각 유효 시각보다 24시간 앞선 예보**, `previous_day2`는 48시간 앞선 예보다. 따라서 하루 24개 예보가 한 번에 전날 저녁 발표됐다는 뜻이 아니다. 원본 API에는 개별 실행 초기화/공개 시각이 없으므로 고정된 실제 예측 마감 시각의 가용성은 검증하지 않았다. 특히 day1을 모아 다음 날 전체를 예측하는 운영 성능을 주장하려면 발표 지연까지 별도 확인해야 한다. day2는 더 큰 시간 여유가 있지만 자동으로 운영 누수 검증이 끝나는 것은 아니다.

날짜 d를 예측할 때 입력은 d의 예보와 d 이전의 발전 실적/관측만 사용한다. 날짜별 시간 순 분할 후 전처리를 학습 구간에만 맞춘다. `gen_kwh`를 포함한 전체 숫자 열을 자동 입력으로 선택하지 않는다. `Date,Close,Volume` 업로드 형식과 달리 이 파일은 **대상 날짜 기준**이므로 기존 업로드의 d+1 이동을 무심코 다시 적용하지 않는다. 서로 다른 발전소를 한 시계열로 이어 붙이지 않는다.

## 출처 및 재생성

- 예보: [Open-Meteo Previous Runs API](https://open-meteo.com/en/docs/previous-runs-api), JMA MSM. 데이터 CC BY 4.0, 비상업 학습 목적으로 무료 API 사용. 가공: KST 일 집계 및 발전량 결합. [이용 조건](https://open-meteo.com/en/terms), [요금/요청 한도](https://open-meteo.com/en/pricing).
- 대표 좌표: 한국남부발전 [위치정보 15147894](https://www.data.go.kr/data/15147894/fileData.do), 기상청 [영월 관측소](https://www.weather.go.kr/download_01/climate_wind.pdf), Open-Meteo 지명 API(삼척·익산·안동; GeoNames 기반). 원본 및 개별 URL은 함께 보관.
- 발전 실적: 기존 `datasets/multi_plant/README.md`와 `datasets/README.md`의 원본 출처·이용 조건을 따른다.

`project/`에서 `python ../tools/build_plant_forecasts/build.py` 실행. 완료한 요청은 캐시에서 읽으며 재호출하지 않는다. 최대 3개 요청을 동시에 처리하되 시작 간격은 4초 이상이며 429를 임의 우회하지 않는다. 이어서 `python ../tools/build_plant_forecasts/verify.py`로 재검증한다. 이 디렉터리는 위 도구로 생성하며 손으로 수정하지 않는다.
