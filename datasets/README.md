> **2026-10-07 시간별 전환 — 현행:** 현재 운영 입력은 hourly/README.md의 실제 시간별 실적·JMA48h선행예보다. 이전 일별파일은 보관자료이며 시간별자료로 분할하지 않는다. [운영 안내](../docs/backend-runbook.md) · [결정0014](../docs/decisions/0014-hourly-forecast-and-aiops.md). 이하 이전 계약·수치는 설계/검증 이력이며 현행 시간별 계약보다 우선하지 않는다.

# 데이터

대시보드에 올릴 업로드용 CSV 와 그 바탕이 되는 자료를 둔다. `project/data/` 는 서빙 앱의 코드 폴더이므로 데이터는 여기에 따로 둔다.

FastAPI 입력 계약은 사용자 승인으로 `hadong_upload_forecast_jma.csv`의 뜻을 따른다. 감시 자료와 시연 구간은 별도 담당 작업이다. 2026-10-07 현재 예측에는 `hadong_upload_forecast_jma.csv` 를, 지난 뒤의 감시에는 `hadong_daily_full.csv` 를 쓰자는 제안이 결정 기록 [0002](../docs/decisions/0002-inputs-and-prediction-time.md)와 [0009](../docs/decisions/0009-demo-plan.md)에 있다. 확정되면 이 문단을 바꾼다.

## 업로드 파일

아래 기존 하동 파일은 UTF-8 이고 열은 `Date, Close, Volume, Stop` 이다. `Close` 는 그날 하루 발전량(kWh)이다. 서빙 앱은 `Stop` 열을 읽지 않는다. 여러 발전소 확장 파일은 아래 별도 절을 참고한다.

파일마다 `Volume` 에 든 값이 다르다. **대상일**은 맞히려는 날(내일)이다.

| 파일 | 행 수와 기간 | `Volume` 에 든 값 | 예측 시점에 받을 수 있는가 |
| --- | --- | --- | --- |
| [`hadong_upload.csv`](hadong_upload.csv) | 4,746행, 2013-01-02 ~ 2025-12-30 | 하루 전의 광양시(266) 관측 일사량 (MJ/m2) | 받을 수 있다 |
| [`hadong_upload_forecast_jma.csv`](hadong_upload_forecast_jma.csv) | 1,337행, 2022-07-02 ~ 2026-02-27 | 다음 날에 대한 하루 전 일사량 예보 (MJ/m2). Open-Meteo Previous Runs API 를 모델을 지정하지 않고 부른 값(Best Match)이다. 표본 대조에서는 일본 기상청(JMA) MSM 과 같았지만 전 기간이 JMA 라는 근거는 없다. 파일 이름의 `jma` 는 그 표본에서 온 것이다([T3](../docs/research/merged/T3-weather-input.md)) | 전날 낮부터 받을 수 있는 것으로 보인다 (이틀 치만 대조한 추정) |
| [`hadong_upload_forecast_proxy.csv`](hadong_upload_forecast_proxy.csv) | 4,746행, 2013-01-02 ~ 2025-12-30 | 다음 날의 광양시 **실제 관측** 일사량 (MJ/m2) | **받을 수 없다.** 예보가 완벽하다고 가정한 상한이다 |
| [`alt/hadong_upload_sunshine.csv`](alt/hadong_upload_sunshine.csv) | 위와 같음 | 하루 전의 광양시 관측 일조 시간 (시간) | 받을 수 있다 |
| [`alt/hadong_upload_forecast_proxy_sunshine.csv`](alt/hadong_upload_forecast_proxy_sunshine.csv) | 위와 같음 | 다음 날의 광양시 실제 관측 일조 시간 (시간) | **받을 수 없다.** 상한이다 |

### 쓸 때 주의할 점

- **상한 파일로 얻은 수치는 현실 성능이 아니다.** `forecast_proxy` 가 붙은 파일을 올린 화면과 그 결과를 적는 문서에는 "예보가 완벽하다고 가정한 값"이라고 적는다. 이 파일은 대상일 칸뿐 아니라 그 전날 칸의 관측도 예측 시점에는 아직 공개되지 않은 값이다.
- **`hadong_upload.csv` 의 `Volume` 은 성능을 올리지 않는다.** 조사에서 지난 관측 날씨는 발전량만 넣은 것과 차이가 없었다. 입력 모양 (20, 2) 를 유지하려고 넣은 열이다.
- **`hadong_upload_forecast_jma.csv` 는 2022-07 이후만 있다.** 그 전의 사건(예: 2021년 5월의 출력 하락)은 이 파일로 시연할 수 없다. `Stop` 은 전 행 0 이다.
- **정지일은 지우지 않고 `Stop` 열로 표시만 했다.** 실습 코드가 행이 이어져 있다고 보고 창을 만들기 때문이다. `hadong_upload.csv` 에는 `Stop = 1` 인 날이 43일 있다. 이 가운데 4일(2015-05-04, 2016-12-27, 2018-07-11, 2020-09-08)은 그날의 날씨 관측을 봐야 붙는 사후 표시다. 학습 표본을 빼는 데만 쓰고 모델 입력이나 서빙 시점 판정에는 쓰지 않는다.
- **파일 종류를 바꾸면 스케일러와 모델을 다시 만든다.** `hadong_upload.csv` 와 `hadong_upload_forecast_proxy.csv` 는 값의 범위가 같아 스케일러 하나로 둘 다 쓸 수 있다. 나머지는 범위가 다르다.
- **현재 FastAPI는 0 발전량과 소수 예보를 받는다.** `/predict`는 날짜가 연속인 20일의 `date`, `close`(0~1,320kWh), `volume`(0~45MJ/m²)을 받는다. CSV도 같은 범위와 연속 날짜를 검사한다. 원본 HAIC 요청 및 날짜가 빠진 관측 파일은 현재 규격과 다르다.

### 조사 단계에서 잰 수치

아래는 조사 단계의 값이다. 우리 서버로 직접 돌려 얻은 결과가 아니므로 시연 결과 자리에 옮겨 적지 않는다. 실습 절차 그대로(전체 행으로 스케일, 앞 80% 학습, 100 epoch) 학습한 시험 구간의 RMSE(하루 kWh)다.

| 파일 | 시험 구간 | RMSE (씨앗 42, 43, 44) | 출처 |
| --- | --- | --- | --- |
| `hadong_upload.csv` | 946문제, 2023-05-30 ~ 2025-12-30 | 78.99, 78.49, 80.04 | [ASOS 보고서](../docs/research/asos-report.md) 4절 |
| `hadong_upload_forecast_jma.csv` | 264문제, 2025-06-09 ~ 2026-02-27 | 41.59, 42.22, 44.72 | [보완 조사 1](../docs/research/prestudy/gap_1.md) |
| `hadong_upload_forecast_proxy.csv` (상한) | 946문제, 2023-05-30 ~ 2025-12-30 | 23.73, 22.85, 22.60 | [ASOS 보고서](../docs/research/asos-report.md) 4절 |

세 파일은 시험 구간이 서로 달라 위아래로 바로 견줄 수 없다. 같은 구간으로 맞춘 비교는 보완 조사 1 에 있다.

## 분석용 자료

| 파일 | 내용 |
| --- | --- |
| [`hadong_daily_full.csv`](hadong_daily_full.csv) | 4,807행, 2013-01-01 ~ 2026-02-28. 날짜별 한 줄로 발전 실적, 광양시 관측 날씨, 정지 표시, 성능 지표(실제 발전량 ÷ 그날 날씨로 계산한 기대 발전량)를 합친 것. 28열. 업로드 형식이 아니라서 올리면 400 으로 거절된다. 2026-01 ~ 02 는 날씨와 성능 지표가 비어 있다 |

| [`jeokryang_daily.csv`](jeokryang_daily.csv) | 4,838행, 2013-01-01 ~ 2026-03-31. 하동군 적량면 관측 자료를 하루 값으로 바꾼 것. 열은 `gsr_mj`(하루 일사량, MJ/m2), `n_hours`(일사량 값이 있는 시간 수), `predawn_mj`(해 뜨기 전 누적값), `after_sunset_mj`(19시 뒤에 더 쌓인 양), `tmax_c`(시간별 기온의 최댓값), `rain_mm`(하루 강수량) |

`hadong_daily_full.csv` 의 열의 뜻은 [ASOS 보고서](../docs/research/asos-report.md) 4절에 있다.

### `jeokryang_daily.csv` 를 쓸 때 주의할 점

- **기준 자료로 쓰지 않는다.** 센서의 수준이 여러 번 계단처럼 바뀌었다. 광양 관측 대비 비율이 2022 ~ 2023년 0.53, 2024년 2월 이후 0.66 안팎이다. 여러 해에 걸친 학습이나 드리프트 감시의 기준으로 쓰면 가짜 변화가 생긴다.
- 하루 일사량이 유효한 날은 4,838일 가운데 3,436일이다. 2018-04-11 ~ 2021-10-20 이 통째로 비어 있다.
- 값의 수준이 광양의 3분의 2 정도다. 두 자료를 섞어 쓰려면 구간별로 환산해야 한다.
- 원본의 일사량 열은 그날 0시부터 쌓인 누적값이고, 하루 값은 그날의 최댓값이다. 밤에 조금씩 쌓이는 영점 오차는 빼지 않았다.
- 근거와 수치는 [적량면 관측 자료 검토](../docs/research/jeokryang-sensor.md)에 있다.

## 원본

| 파일 | 출처 | 이용 조건 |
| --- | --- | --- |
| [`raw/data_15043409.csv`](raw/data_15043409.csv) | 공공데이터포털 [「한국남부발전(주)\_하동하수처리장 태양광발전실적\_20260228」](https://www.data.go.kr/data/15043409/fileData.do). CP949, 4,807행. 하루 합계와 시간대별 24칸 | 무료, 이용허락범위 제한 없음. 출처 표기 조건은 붙어 있지 않다 |
| [`raw/wx_prevruns_daily.csv`](raw/wx_prevruns_daily.csv) | Open-Meteo Previous Runs API. 하루 전·이틀 전 일사량 예보의 하루 합계 등. 1,369행, 2022-06-01 ~ 2026-02-28 | CC BY 4.0. 무료 API 는 비상업 용도에 한한다. 자료를 보여 주는 곳 옆에 `Weather data by Open-Meteo.com` 링크를 둔다 |
| [`raw/wx_archive_daily.csv`](raw/wx_archive_daily.csv) | Open-Meteo 과거 날씨 API(재분석). 4,807행, 2013-01-01 ~ 2026-02-28 | 위와 같음 |

적량면 시간 자료(`하동_적량면_667831A001_시간자료_20130101_20260331.csv`, 11.6MB)는 넣지 않았다. 출처 기관과 이용 조건을 아직 확인하지 못했다([`../docs/followups.md`](../docs/followups.md) 6번). 하루 값을 다시 만들려면 이 파일을 받아 `tools/jeokryang/01_build_daily.py` 에 경로를 준다.

광양시 관측값(업로드 파일의 일사량과 일조 시간, `hadong_daily_full.csv` 의 날씨 열)은 기상청 종관기상관측(ASOS) 일자료에서 왔다. 연도별 원본은 크기가 커서 넣지 않았다. 2026-10-07 데이터 확장 시 사용자 ASOS 원본과 하동 값을 대조하고 필요한 관측소·열을 `multi_plant/weather/`에 추가했다. [ASOS 일자료 API](https://www.data.go.kr/data/15059093/openapi.do)의 이용 조건은 무료·공공누리 제1유형(출처표시)임을 확인했다. 사용자 연도별 파일의 실제 수집 응답 기록은 없으므로 파일명·해시를 함께 남겼다.

이용 조건의 근거는 [`../docs/research/prestudy/`](../docs/research/prestudy/)의 `research_2-data-definition.md` 와 `research_3b-weather-open.md` 에 있다.

## 여러 발전소 자료

여러 발전소로 넓히기 위한 준비다(2026-10-07). 서비스는 아직 발전소 한 곳만 읽는다. 계약의 본문은 [`../docs/proposal/multi-plant-data-contract.md`](../docs/proposal/multi-plant-data-contract.md)에, 배경은 [`../docs/proposal/multi-plant-extension.md`](../docs/proposal/multi-plant-extension.md)에 있다.

### 자료의 종류

| 종류 | 파일 | 출처 | 단위 | 만드는 법 |
| --- | --- | --- | --- | --- |
| 발전소 등록부 | [`plants/plants.csv`](plants/plants.csv) | 한국남부발전의 공시(설비 사양, 설비 현황, 발전소 위치) | 용량은 적힌 그대로 `kW` 또는 `MW`. 좌표는 도 | **사람이 적는다.** 한 줄에 발전소 하나의 한 유효 기간. 용량과 좌표의 근거를 함께 적고 모르는 칸은 비운다 |
| 포트폴리오 구성 | [`plants/portfolio_members.csv`](plants/portfolio_members.csv) | 우리가 정한 가상의 구성 | 없다 | **사람이 적는다.** 구성원이 바뀌면 구성 버전을 올린다 |
| 하루 발전량 | `plants/generation/<plant_id>/generation_daily.csv` | 발전소별 원자료 | kWh (그날 하루) | `tools/multi_plant/convert_kospo_raw.py`. 커밋하지 않는다 |
| 시간대별 발전량 | `plants/generation/<plant_id>/generation_hourly.csv` | 발전소별 원자료 | kWh (그 한 시간). 시간 h 는 (h−1)시 ~ h시 | 위와 같다. 커밋하지 않는다 |
| 계보 | `plants/generation/<plant_id>/manifest.json` | 변환 도구 | 원자료와 결과의 해시(SHA-256) | 위와 같다 |
| 기상 자료 | 아직 없다 | 발전소별 예보와 관측 | 일사량의 하루 합계 MJ/m² | 계약만 정했다. 발전소별 예보를 받는 도구는 과제다 |

- 등록부와 구성은 손으로 적는 파일이다. 아래 "규칙"의 "손으로 고치지 않는다"는 원자료와 만든 자료에 대한 것이다. 적은 뒤에는 `python tools/multi_plant/validate.py --data-root datasets/plants` 로 검증한다.
- `plants/generation/` 은 원자료에서 다시 만들 수 있어 커밋하지 않는다(`.gitignore`). 저장소를 받은 뒤 한 번 만든다.

```bash
# 저장소 루트에서
python tools/multi_plant/convert_kospo_raw.py --raw datasets/raw/data_15043409.csv --plant-id hadong-sewage --out-root datasets/plants
```

### 지금 들어 있는 것

| 식별자 | 내용 | 값 |
| --- | --- | --- |
| 발전소 `hadong-sewage` | 하동하수처리장태양광. 경남 하동군 하동읍 신기리 2-2 | 설비 용량 55kW(공시 설치용량). 좌표 35.05885, 127.7799 |
| 포트폴리오 `virtual-vpp` | 구성 버전 1. 구성원은 `hadong-sewage` 한 곳 | **가상의 묶음이다.** 실제 집합전력자원이 아니고, 하동이 실제로 어느 묶음에 들어 있는지는 확인되지 않았다. 설비 용량 합계 55kW(20MW 의 0.275%) |

- 설비 용량은 **kW, MW** 이고 기간이 붙지 않는다. 발전량은 **kWh** 이고 기간이 붙는다. 용량의 합과 발전량의 합을 섞지 않는다.
- 제도의 참여 요건(묶음 안 태양광·풍력의 설비 용량 합계 20MW 초과)에 한참 못 미친다. 자료를 여러 곳 모아도 요건을 채웠다고 쓰지 않는다([결정 기록 0010](../docs/decisions/0010-multi-plant-scope-and-scheme.md)).

### 새 발전소를 등록하는 절차

단계마다의 통과 조건은 [자료 계약 6절](../docs/proposal/multi-plant-data-contract.md)에 있다.

1. 원자료를 받아 둔다. 출처의 주소, 이용 조건, 받은 날을 아래 "원본"의 표처럼 적는다. 파일을 고치지 않는다.
2. `plants/plants.csv` 에 한 줄을 더한다. `plant_id` 는 영문 소문자, 숫자, 붙임표로 짓고 한번 정하면 바꾸지 않는다.
3. `convert_kospo_raw.py` 로 정규화 실적을 만든다. 형식이 다른 원자료는 변환 도구를 하나 더 쓴다.
4. `validate.py` 로 검증한다. 오류가 0건이어야 한다.
5. `coverage.py` 로 그 발전소의 기간과, 포트폴리오에 넣었을 때의 공통 기간을 본다.
6. `plants/portfolio_members.csv` 에 넣는다. 구성 버전을 올리고 적용 기간을 적는다.
7. 발전소별 예보를 붙여 업로드 파일을 만들고 학습한다. 이 단계는 서비스가 여러 발전소를 받게 된 뒤에 할 수 있다.

### 추가를 검토한 자료

**저장소에 넣지 않았다.** 다른 발전소의 원자료는 백엔드를 돌릴 PC 에 둘 예정이고, 저장소에 넣을지는 정하지 않았다([`../docs/followups.md`](../docs/followups.md) 27번). 도구는 `--data-root` 와 `--raw` 로 저장소 밖의 폴더를 읽는다.

| 발전소 | 원자료 | 설비 용량(공시) | 확인한 것 |
| --- | --- | --- | --- |
| 하동공설운동장태양광 | [data.go.kr/15043404](https://www.data.go.kr/data/15043404/fileData.do) | 369.85kW | 형식이 하동하수처리장과 같다. 4,807일, 0 인 날 47일. 하루 발전량이 지금의 입력 상한 1,320kWh 를 넘는 날이 1,936일이다 |
| 하동변전소태양광 | [data.go.kr/15043405](https://www.data.go.kr/data/15043405/fileData.do) | 48.3kW | 4,807일, 0 인 날 41일 |
| 하동군보건소태양광 | [data.go.kr/15043406](https://www.data.go.kr/data/15043406/fileData.do) | 40kW | 4,807일, 0 인 날 7일. 발전소 위치 공시에 좌표가 없다 |
| 하동정수장태양광 | [data.go.kr/15043408](https://www.data.go.kr/data/15043408/fileData.do) | 93.02kW | 4,807일, 0 인 날 29일. 머리 줄에 `(kw)` 가 없다 |

- 네 곳 모두 한국남부발전이 공공데이터포털에 낸 자료이고 페이지에 "무료, 이용허락범위 제한 없음"이라고 적혀 있다(이전 조사 때 저장한 페이지에서 확인).
- 이 PC 에 이전 조사 때 받아 둔 사본으로 변환, 검증, 평가를 돌렸다. 사본의 해시가 [`tools/verify/official-result.json`](../tools/verify/official-result.json)의 공식 파일과 같다. 결과는 [검증 기록](../docs/proposal/evidence/multi-plant/validation.md)의 M04 ~ M06 에 있다.
- 같은 군 안의 발전소라 같은 날씨를 겪는다. 다섯 곳을 더해도 설비 용량 합계는 606.17kW 다.
- 하동 밖의 발전소는 아직 확인하지 않았다. 조사 기록에는 한국남부발전의 발전소별 실적 파일이 40개라고 적혀 있다([T1](../docs/research/merged/T1-plant-data.md)).

## 여러 발전소 확장 데이터

[`multi_plant/`](multi_plant/README.md)에 추가 발전실적 원본 39개와 ASOS를 연결한 호기별 데이터를 둔다. 34개 실적 파일의 43개 호기에서 연속 날짜 검사를 통과한 업로드 CSV 78개(113,944행)를 만들었다. 위의 기존 하동 업로드 파일 목록과 별도의 확장 자료다.

새 업로드 파일은 `Date,Close,Volume` 세 열이며, `Volume`은 달력상 하루 전 ASOS 일사량(MJ/m²)으로 통일했다. `Stop`은 임의 생성하지 않았다. 발전소별 시작 파일은 [`multi_plant/INDEX.md`](multi_plant/INDEX.md)에 있다. 여러 발전소나 떨어진 구간을 한 파일로 이어 붙이지 않는다.

사용자 제공 ASOS 2013~2025 원본은 먼저 기존 하동 일별 4,748행·업로드 4,746행과 대조해 일치함을 확인한 뒤 필요한 관측소 18개와 열만 추렸다. 결과는 [`multi_plant/weather_verification.json`](multi_plant/weather_verification.json), 학습 코드 입력 검증은 [`multi_plant/validation.json`](multi_plant/validation.json)에 있다. 모델 학습과 다중 모델 서빙은 이번 데이터 추가에 포함하지 않는다.

## 파일 관리 규칙

- 여기 있는 파일은 손으로 고치지 않는다. 만든 스크립트는 [`../tools/`](../tools/)에 있다. 발전소 등록부와 포트폴리오 구성(`plants/*.csv`)은 사람이 적는 파일이고, 적은 뒤에 도구로 검증한다.
- 서빙 앱이 실제로 읽는 것은 대시보드로 올린 사본(`project/data/uploads/`)이다. 그 폴더는 커밋하지 않는다.
- Open-Meteo 자료를 다시 받을 때는 한 번 받아 파일로 저장하고 반복 호출하지 않는다. 무료 한도가 있다.


## 발전소 지역별 과거 예보 저장

[`plant_forecasts/`](plant_forecasts/README.md)에 Open-Meteo JMA MSM 과거 예보 원본과 지역별 일 집계, 발전소별 학습 테이블을 저장한다. 6개 변수(일사량·기온·일조시간·구름량·강수량·풍속)의 24/48시간 선행 예보를 요청하며 실제 유효 기간은 `coverage.csv`에 기록한다. 출처·CC BY 4.0 이용 조건·단위·집계법·지역 대표 좌표의 한계는 해당 README에 있다. 생성 도구는 [`../tools/build_plant_forecasts/`](../tools/build_plant_forecasts/README.md)다. **발표 시각이 없는 고정 선행시간 자료이므로 운영 예측 마감 기준의 누수 검증은 미완료다.**

## 2026-10-07 백엔드 통합

운영 등록부는 bootstrap.py가 source_id에서 생성한다. 업로드의 Volume은 d+1 예보, Expected는 d 관측 일사량으로 추정한 사후 기대 발전량이다. 기대 발전량 계수는 개소별 2022–2023년 자료에 맞추고, PI 기준선은 2024년 마지막 365일에서 정한다. 결측·설비 이상은 제외하며 용량 미확인 개소는 보류한다.

## 2026-10-08 PR의 데이터 보관 정책

이 절이 위의 일별·확장 검토 당시 설명보다 우선한다. 시간별 재현을 위해 수집 원본과 출처 메타데이터를 비공개 Git에 보관한다. `multi_plant/raw/{source_id}.csv`별 출처·수집 시각·SHA·이용 조건은 동명 JSON 및 sources.json에, 예보 원본은 `plant_forecasts/raw/*.meta.json`에 기록한다. 남부발전 자료는 수집 당시 이용허락범위 제한 없음, Open-Meteo는 CC BY 4.0 출처표시 조건을 따른다. 세부 조건은 각 폴더 README를 따른다.

`datasets/plants/generation/`과 `datasets/hourly/plants/`는 원본에서 재생성하므로 Git에서 제외한다. 기존 일별 `multi_plant/daily`, `uploads` 및 `plant_forecasts/daily`, `training`은 과거 검증의 고정 자료로 이 PR에서 유지하고 신규 시간별 가공본은 추가하지 않는다. 증빙 JSON·그림은 발표 재현 근거로 보관하고 모델·DB·로그는 제외한다. 저장소 용량 감소를 위한 과거 자료 이관은 팀 검토 사항이며 이 리뷰 수정에서 원자료를 삭제하지 않는다. 현행 재생성 경로는 tools/hourly/prepare.py이며 ASOS 일별 가공본은 시간별 모델 입력이 아니다.
