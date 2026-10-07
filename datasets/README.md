# 데이터

대시보드에 올릴 업로드용 CSV 와 그 바탕이 되는 자료를 둔다. `project/data/` 는 서빙 앱의 코드 폴더이므로 데이터는 여기에 따로 둔다.

어느 파일을 쓸지는 아직 확정하지 않았다. 2026-10-07 현재 예측에는 `hadong_upload_forecast_jma.csv` 를, 지난 뒤의 감시에는 `hadong_daily_full.csv` 를 쓰자는 제안이 결정 기록 [0002](../docs/decisions/0002-inputs-and-prediction-time.md)와 [0009](../docs/decisions/0009-demo-plan.md)에 있다. 확정되면 이 문단을 바꾼다.

## 업로드 파일

모두 UTF-8 이고 열은 `Date, Close, Volume, Stop` 이다. `Close` 는 그날 하루 발전량(kWh)이다. 서빙 앱은 `Stop` 열을 읽지 않는다.

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
- **원본 스키마로는 올라가도 `/predict` 가 통과하지 않는다.** `serving_app/schemas.py` 가 `close` 는 0 보다 커야 하고 `volume` 은 정수여야 한다고 검사한다. 발전량은 0 인 날이 있고 날씨 값은 소수다.

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

광양시 관측값(업로드 파일의 일사량과 일조 시간, `hadong_daily_full.csv` 의 날씨 열)은 기상청 종관기상관측(ASOS) 일자료에서 왔다. 연도별 원본은 크기가 커서 넣지 않았다. 이 자료의 이용 조건은 아직 확인해 적지 않았다([`../docs/followups.md`](../docs/followups.md) 5번).

이용 조건의 근거는 [`../docs/research/prestudy/`](../docs/research/prestudy/)의 `research_2-data-definition.md` 와 `research_3b-weather-open.md` 에 있다.

## 규칙

- 여기 있는 파일은 손으로 고치지 않는다. 만든 스크립트는 [`../tools/`](../tools/)에 있다.
- 서빙 앱이 실제로 읽는 것은 대시보드로 올린 사본(`project/data/uploads/`)이다. 그 폴더는 커밋하지 않는다.
- Open-Meteo 자료를 다시 받을 때는 한 번 받아 파일로 저장하고 반복 호출하지 않는다. 무료 한도가 있다.
