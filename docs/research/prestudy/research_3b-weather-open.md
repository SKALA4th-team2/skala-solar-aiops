# 조사 3b-weather-open (3. 날씨 데이터) — 출처 검증을 마친 결과

## 1. (1) 하동 좌표(북위 35.07, 동경 127.75)에 대해 2013~2026년의 일별 일사량 합계, 일조 시간, 구름양, 기온을 로그인이나 키 없이 받을 수 있는가. API 주소와 매개변수, 시험 호출 결과

- 상태: 확인함 / 검증 판정: 출처가 뒷받침함
- 답: 받을 수 있다. 2026-10-06에 키 없이 다시 호출해 2013-01-01~2026-02-28의 4,807일을 결측 없이 받았다(발전실적 CSV와 날짜 수가 같다).

① Open-Meteo 과거 날씨 API(ERA5 재분석)
https://archive-api.open-meteo.com/v1/archive?latitude=35.07&longitude=127.75&start_date=2013-01-01&end_date=2026-02-28&daily=shortwave_radiation_sum,sunshine_duration,cloud_cover_mean,temperature_2m_mean&timezone=Asia%2FSeoul&models=era5
- 단위: 일사량 MJ/m²(÷3.6 하면 kWh/m²), 일조 시간 초, 구름양 %, 기온 °C. 응답 약 0.17MB, 4개 변수 모두 null 0개. 격자점 35.0N/127.75E.
- 주의 1(고침): models 를 빼면 기본값(Best Match)은 문서 표기대로 ERA5, ERA5-Land, ECMWF IFS 9km를 이어 붙인 값이다. 직접 비교하니 일사량은 2013~2016년 1,461일 전부 ERA5와 같고 2017년부터는 3,346일 중 21일만 같았다(차이 RMSE 1.68 MJ/m²). 기온은 2016년 이전에도 ERA5 단독과 거의 전부 달랐다(1,461일 중 8일만 일치). 기본값의 기온은 전 기간 ERA5-Land 쪽으로 보인다(추정: 문서가 기본값에 ERA5-Land를 포함한다고 적은 것에 근거). 학습 기간 안에서 자료원이 바뀌는 것을 피하려면 models=era5 를 붙인다.
- 주의 2(보강): timezone=Asia/Seoul 을 빼면 하루 집계가 UTC 날짜(KST 09시~다음 날 09시) 기준이 되어, 해 뜬 뒤 09시 이전의 아침 일사가 전날 날짜로 넘어간다. 겨울에는 차이가 거의 없고(2013-01-01~05는 두 호출이 같은 값), 2019-06-01~05 시험에서는 일사량 합계가 최대 0.7 MJ/m², 구름양 평균이 최대 29%p 달랐다.
- 주의 3(고침): sunshine_duration 은 관측이 아니라 직달 법선 일사(DNI)가 120 W/m²를 넘는 시간을 계산한 값이다. models=era5 응답은 전 기간 평균 8.83시간/일, 3600초의 배수인 날 18.4%(0초인 날 5.0% 포함)다. 원 답의 8.64시간·19.9%는 models 를 뺀 기본값 응답의 수치였다. 기상청 일조계 관측값과 같은 것으로 쓰면 안 된다.
- 지연: ERA5 단독은 2026-10-06 호출 시 09-30까지(문서 표기는 5일 지연), 기본값은 당일(10-06)까지 값이 있었다.

② NASA POWER 일별 API
https://power.larc.nasa.gov/api/temporal/daily/point?parameters=ALLSKY_SFC_SW_DWN,CLRSKY_SFC_SW_DWN,ALLSKY_KT,CLOUD_AMT,T2M&community=RE&longitude=127.75&latitude=35.07&start=20130101&end=20260228&format=JSON&time-standard=LST
- 일사량(kWh/m²/일), 청천 일사량, 청명도(KT), 구름양(%), 기온(°C). 4,807일에 결측값(-999) 0개. 응답 약 0.4MB. API v2.10.0, 자료원 MERRA2·SYN1DEG·POWER.
- 일사는 1도 격자(CERES SYN1deg, 최근 구간은 FLASHFlux), 기상은 0.5×0.625도(MERRA-2). 응답 좌표의 표고가 218.15m여서 저지대인 실제 부지와 다르다.
- 일조 시간(보강): 일별 RE 커뮤니티 매개변수 목록(152개)에 일조 시간 항목은 없다. 비슷한 것으로 PSH(peak sun hour, 일사량 환산값)와 CLOUD_AMT_DAY(낮 구름양)가 있다.
- 최근 구간(보강): 2026-10-06 호출 시 일사량은 10-01까지, 기온은 10-03까지 값이 있었고, 청명도(KT)와 구름양(CLOUD_AMT)은 2026-06-29까지만 있고 그 뒤는 -999였다.
- time-standard=LST 는 KST가 아니라 경도 15도 띠 기준의 지방 태양시다(문서 정의).

③ Open-Meteo 위성 일사량 API(히마와리, 0.05도 약 5km)
https://satellite-api.open-meteo.com/v1/archive?latitude=35.07&longitude=127.75&daily=shortwave_radiation_sum&start_date=2015-07-03&end_date=2026-02-28&timezone=Asia%2FSeoul&models=satellite_radiation_seamless
- 하동은 2015-07-03부터 값이 있고 그 뒤 결측이 70일 있다(유효 3,824일, 발전량 0인 날을 빼면 3,800일). 2013년~2015년 6월은 없다.
- models 를 빼면 ①의 기본값(Best Match) 응답과 4,807일 전부 같은 값이 나오므로 반드시 지정한다.
- 자료원은 문서가 링크한 JAXA P-Tree의 히마와리 단파복사 산출물이다.

④ 그 밖의 후보
- PVGIS(EU JRC) API는 키 없이 호출되지만 한국은 PVGIS-ERA5 자료이고 2005~2023년까지만 있다(2024년 요청은 400 오류). 일 단위 시계열 전용 호출은 없고 시간별·월별이다.
- NOAA GSOD(진주 47192)는 키 없이 기온·이슬점·시정·강수·풍속을 주지만 일사량과 구름양이 없다.
- ERA5 원본(Copernicus CDS)은 가입이 필요함.
- Meteostat 대량 내려받기 주소 네 가지는 404여서 확인하지 못했다.

직접 계산(참고용, 발전량이 0보다 큰 4,783일, 같은 날끼리의 피어슨 상관): ERA5 일사량 +0.79, POWER 일사량 +0.78, POWER 청명도 +0.85, ERA5 일조 시간 +0.82, ERA5 구름양 -0.64, 기온 -0.03(ERA5)·-0.07(POWER). 히마와리 일사량은 +0.86(2015-07 이후 3,800일).

좌표: 발전소의 정확한 좌표는 이 항목에서 확인하지 못했고 주어진 근사 좌표를 썼다. 응답 격자점은 ERA5 35.0/127.75, IFS 35.04/127.79, JMA MSM 35.05/127.75, JMA GSM 35.0/128.0이다. GSM은 0.5도 격자라 격자점이 동쪽으로 약 23km 떨어져 있다.

호출 수: Open-Meteo는 2주를 넘는 기간 요청을 여러 번의 호출로 계산한다. 13년치 호출은 한 번만 하고 결과를 파일로 저장해 재사용하는 것이 안전하다((4)번 참고).
- 프로젝트에 주는 영향: 발전실적과 같은 4,807일의 날씨를 키 없이 한 번의 호출로 붙일 수 있어 학습 데이터 준비에 걸림돌이 없다. 다만 기본 모델 전환(2017년), 시간대 매개변수, 긴 기간 호출의 호출 수 계산을 놓치면 조용히 틀어지거나 한도에 걸린다.
- 검증자 메모: 직접 확인: ERA5·기본값·POWER·위성(모델 지정/미지정) 다섯 호출을 다시 받아 날짜 수, null 수, 격자점, 단위, 2017년 전환(1,461/1,461 일치, 21/3,346 일치, RMSE 1.68)을 재현했다. 발전량과의 상관 7개도 다시 계산해 같은 값을 얻었다. Open-Meteo 문서 3종, NASA POWER 문서 2종, PVGIS·GSOD 호출도 열어 대조했다.
고친 것: (1) 일조 시간 평균 8.64시간·19.9%는 ERA5 응답이 아니라 기본값 응답의 수치여서 ERA5 값(8.83시간, 18.4%)으로 바꿨다. (2) '기본값은 2016년까지 ERA5'는 일사량에만 맞는다. 기온은 2016년 이전에도 ERA5와 달랐고 문서도 기본값에 ERA5-Land가 들어간다고 적는다. (3) 기온 상관 -0.05는 ERA5 -0.03, POWER -0.07로 나눠 적었다. (4) 시간대 영향은 겨울에 거의 없고 여름에 크다는 것을 시험 호출로 확인해 구체화했다. (5) POWER에 일조 시간 변수가 없다는 것을 매개변수 목록으로 확인해 '확인하지 못함'을 해소했다. (6) JMA GSM 격자점(35.0/128.0)을 추가했다. (7) 위성 API에서 models 를 뺀 값은 ERA5 단독이 아니라 기본값과 같다.
임시 파일: (작업 폴더) (이하 생략, 전문은 JSON)
- 출처:
  - [Open-Meteo Historical Weather API 시험 호출 응답(ERA5): 4,807일, 4개 변수 null 0개, 격자점 35.0N 127.75E](https://archive-api.open-meteo.com/v1/archive?latitude=35.07&longitude=127.75&start_date=2013-01-01&end_date=2026-02-28&daily=shortwave_radiation_sum,sunshine_duration,cloud_cover_mean,temperature_2m_mean&timezone=Asia%2FSeoul&models=era5) (2026-10-06 재호출)
  - [같은 호출에서 models 를 뺀 응답(Best Match): 격자점 35.04N 127.79E, 일조 시간 평균 8.64시간·3600초 배수 19.9%는 이 응답의 값](https://archive-api.open-meteo.com/v1/archive?latitude=35.07&longitude=127.75&start_date=2013-01-01&end_date=2026-02-28&daily=shortwave_radiation_sum,sunshine_duration,cloud_cover_mean,temperature_2m_mean&timezone=Asia%2FSeoul) (2026-10-06 호출)
  - [Open-Meteo Historical Weather API 문서: ERA5 0.25도 1940년~, ERA5-Land 0.1도 1950년~, IFS 9km 2017년~, 기본값은 IFS·ERA5·ERA5-Land 결합, ERA5 5일 지연, 일조 시간은 DNI 120 W/m² 초과 시간](https://open-meteo.com/en/docs/historical-weather-api) (모름 (2026-10-06 열람))
  - [NASA POWER Daily API 시험 호출 응답(API v2.10.0): 4,807일, 5개 변수 -999 없음, 표고 218.15m](https://power.larc.nasa.gov/api/temporal/daily/point?parameters=ALLSKY_SFC_SW_DWN,CLRSKY_SFC_SW_DWN,ALLSKY_KT,CLOUD_AMT,T2M&community=RE&longitude=127.75&latitude=35.07&start=20130101&end=20260228&format=JSON&time-standard=LST) (2026-10-06 재호출)
  - [NASA POWER 일별 RE 커뮤니티 매개변수 목록(152개): 일조 시간 항목 없음, PSH·CLOUD_AMT_DAY 있음](https://power.larc.nasa.gov/api/system/manager/parameters?community=RE&temporal=daily) (2026-10-06 호출)
  - [NASA POWER Data Sources: CERES SYN1deg 1도(2001년~, 3~4개월 지연), FLASHFlux(5~7일 지연), MERRA-2 0.5×0.625도](https://power.larc.nasa.gov/docs/methodology/data/sources/) (모름 (2026-10-06 열람))
  - [NASA POWER Daily API 문서: 1981-01-01~준실시간, 단일 지점 변수 최대 20개, 기본 시간 기준 LST(경도 15도 띠 지방 태양시)](https://power.larc.nasa.gov/docs/services/api/temporal/daily/) (모름 (2026-10-06 열람))
  - [Open-Meteo Satellite Radiation API 시험 호출 응답: 첫 값 2015-07-03, 이후 결측 70일, 유효 3,824일](https://satellite-api.open-meteo.com/v1/archive?latitude=35.07&longitude=127.75&daily=shortwave_radiation_sum&start_date=2013-01-01&end_date=2026-02-28&timezone=Asia%2FSeoul&models=satellite_radiation_seamless) (2026-10-06 재호출)
  - [Open-Meteo Satellite Radiation API 문서: JMA JAXA Himawari-9, 0.05도, 10분 간격, 보관 2015년~, 자료원 링크는 JAXA P-Tree](https://open-meteo.com/en/docs/satellite-radiation-api) (모름 (2026-10-06 열람))
  - [PVGIS 5.3 API 시험 호출 응답: PVGIS-ERA5, 2005~2023년, 기울기 37도·방위 -2도, 연 1,468.87 kWh/kWp](https://re.jrc.ec.europa.eu/api/v5_3/PVcalc?lat=35.07&lon=127.75&peakpower=1&loss=14&outputformat=json&optimalangles=1) (2026-10-06 재호출)
  - [NOAA NCEI GSOD 시험 호출 응답(진주 47192): 일사량·구름양 항목 없음](https://www.ncei.noaa.gov/access/services/data/v1?dataset=global-summary-of-the-day&stations=47192099999&startDate=2013-01-01&endDate=2013-01-03&format=json) (2026-10-06 재호출)

## 2. (2) 과거 시점에 발표됐던 '예보'를 보관한 자료가 있는가. 어느 날짜부터이고 하루 전 예보를 어떻게 꺼내는가

- 상태: 확인함 / 검증 판정: 출처가 뒷받침함
- 답: 있다. Open-Meteo가 과거 자료를 네 가지로 나눠 제공하고, 하루 전 예보에 해당하는 것은 Previous Runs API다. 키와 가입이 필요 없다.

■ Previous Runs API (https://previous-runs-api.open-meteo.com/v1/forecast)
- 변수 이름 뒤에 _previous_day1 을 붙이면 유효 시각보다 24시간 전에 예측된 값, _previous_day2 는 48시간 전, 이런 식으로 7일 전까지 준다. 2024-04-19 공지 글에 따르면 각 모델 실행에서 24시간째 이후 구간을 잘라 이어 붙인 것이다(3시간마다 갱신되는 모델이면 24·25·26번째 시간 단계).
- 시간별만 된다. 일 집계 이름(shortwave_radiation_sum_previous_day1)은 400 오류였다. 시간별 값을 받아 KST 하루로 합산해야 한다.
- 문서에 적힌 보관 시작: 대부분 2024년 1월, GFS 2m 기온 2021년 3월, JMA GSM·MSM 2018년.
- API가 허용하는 start_date 하한은 2016-01-01이다(그 이전을 요청하면 400 오류).
- 하동 좌표로 직접 확인한 시작일(2026-10-06 호출):
  · JMA GSM(전 지구 0.5도, 격자점 35.0/128.0)의 구름양·기온 하루 전 예보: 2016-01-02 09시(KST)부터, 곧 API 하한에서 바로 시작한다. 2026-02-28까지 89,088시간 중 null 33개(모두 첫 값 이전), 하루가 온전한 날 3,710일. GSM은 일사량을 주지 않는다.
  · JMA MSM(일본·한국 영역 0.05도)의 일사량·구름양·기온 하루 전 예보: 2022-07-02 09시부터. 온전한 날 1,314일. 일사량은 2024-01-24~02-15 구간(534시간)이 비어 있다.
  · GFS, ICON의 일사량 하루 전 예보: 2024-01-19 21시(KST)부터. ECMWF IFS 0.25도는 일사량 2024-03-07, 구름양·기온 2024-02-04부터. ECMWF IFS 9km는 일사량 2025-10-01부터.
  · KMA 모델(kma_seamless): 일사량 2025-02-27, 구름양 2025-03-01부터. 다만 2026-06-01~07과 2026-09-25~10-05 구간은 전부 null이었고, 오늘 Forecast API의 kma_seamless 응답도 null이었다. 운영(서빙)에는 쓸 수 없다고 보아야 한다.
  · 문서의 'JMA는 2018년부터'와 실제 응답(GSM 2016-01, MSM 2022-07)이 다르다. 기획서에는 직접 확인한 날짜를 쓰고 근거를 호출 결과로 적는 것이 안전하다. 2016~2017년 값이 사후 복원된 것인지는 확인하지 못했다.
- 꺼내는 예
  · 구름양(2016년~): …/v1/forecast?latitude=35.07&longitude=127.75&hourly=cloud_cover_previous_day1&models=jma_gsm&start_date=2016-01-01&end_date=2026-02-28&timezone=Asia%2FSeoul
  · 일사량(2022-07~): …/v1/forecast?latitude=35.07&longitude=127.75&hourly=shortwave_radiation_previous_day1,cloud_cover_previous_day1&models=jma_seamless&start_date=2022-07-01&end_date=2026-02-28&timezone=Asia%2FSeoul
- 실제 예보인지 점검: 2016·2019·2022년 6월 한 달씩 JMA GSM 구름양을 최신값과 비교하니 평균 절대 차이가 하루 전 13~14%p, 이틀 전 18~21%p로 선행 시간이 길수록 커졌다(2017년 6월도 13.7/19.2). 최신값과 같은 시간은 10% 안팎뿐이어서 최신값을 복사한 것이 아니다.
- 누설 관점: 목표일 낮 시간(06~19시)의 previous_day1 값은 전날 같은 시각 이전에 초기화된 모델 실행에서 나온다. 전날 발전량이 확정된 뒤(자정 무렵) 예측하는 일 단위 모델에서는 누설이 아니다. 다만 모델 계산과 배포에 시간이 걸리고(문서: 전 지구 모델 4~6시간, 지역 모델 1~3시간), 전력거래소 제출 시각(전날 10시·17시)처럼 엄격히 맞추려면 previous_day2 를 쓰는 편이 안전하다. 제출 시각은 다른 조사 항목이 받아 둔 전력시장운영규칙 개정 자료(2025-02-11)와 대조했고 이 항목에서 URL로 다시 열지는 않았다.
- 학습과 운영의 차이(추가): 학습에 쓰는 previous_day1은 선행 24시간 이상인 값이고, 운영 때 Forecast API에서 받는 내일 값은 그보다 최신 실행이다. 운영 쪽 예보가 조금 더 정확한 방향의 차이다.

■ 하루 전 예보가 아닌 것(혼동 주의)
- Historical Forecast API (https://historical-forecast-api.open-meteo.com/v1/forecast): 각 모델 실행의 첫 몇 시간만 이어 붙인 시계열이라 실제 상황에 가까운 값이다. 목표일 값으로 넣으면 미래 정보를 본 것과 같다. 하동은 일사량이 2017-01-02부터, 구름양·기온이 2016-01-02부터 나왔다. 문서 본문은 2021~2022년부터라고 적지만 같은 문서의 모델 표에는 JMA GSM·MSM 2016-01-01, IFS HRES 2017-01-01로 적혀 있어 응답과 맞는다. Previous Runs API의 최신 실행값(day0)으로 계산한 발전량 상관(+0.84)이 하루 전 예보(+0.775)보다 높았다.
- Historical Weather API: 재분석이므로 실측 대용이다.

■ Single Runs API (https://single-runs-api.open-meteo.com/v1/forecast, run=초기화 시각 UTC)
- 특정 시각에 초기화된 예보 전체를 그대로 꺼낸다. 문서상 ECMWF IFS 9km는 2024-03-14부터, 나머지 모델은 2026-04-02부터.
- 시험: models=ecmwf_ifs 의 2024-06-01·2024-03-15 실행은 값이 왔고 2024-02-01 실행은 '없음' 오류였다. JMA MSM은 2025-06-01·2026-05-01 실행이 '없음', 2026-09-01 실행은 값이 왔다. daily 매개변수는 실행 시각이 요청 시간대의 0시일 때만 된다는 오류가 났다.

■ 운영 시점(서빙)
https://api.open-meteo.com/v1/forecast?latitude=35.07&longitude=127.75&daily=shortwave_radiation_sum,cloud_cover_mean&timezone=Asia%2FSeoul&forecast_days=3 로 내일 예보를 키 없이 받는다. 2026-10-06 호출에서 10-07 값은 일사량 18.87 MJ/m², 구름양 5%였고 models=jma_seamless 지정 호출과 같은 값이었다.

■ 확인하지 않은 것
NOAA GFS·ECMWF 원본 보관소는 GRIB 대용량이라 열지 않았다. 기상청 동네예보 과거 자료는 이 과제 범위(기상청 제외) 밖이다.
- 프로젝트에 주는 영향: 미래 정보를 보지 않는 날씨 입력을 구름양은 2016년부터, 일사량은 2022년 7월부터 만들 수 있다. 2013~2015년은 예보가 없어 예보를 쓰면 학습 기간이 줄어든다. 운영에는 JMA 계열만 현재 값이 나오므로 KMA 모델을 전제로 설계하면 안 된다.
- 검증자 메모: 직접 확인: 문서 4종과 블로그 글을 다시 열어 날짜와 문구를 대조했다. Previous Runs API를 모델 11종으로 다시 호출해 시작일을 구했고, 일 집계 이름 400 오류, start_date 하한, 2016·2017·2019·2022·2025년 6월의 하루 전·이틀 전 차이, Historical Forecast 시작일, Single Runs 5건, Forecast API 값(18.87 MJ/m², 5%)을 재현했다.
고친 것: (1) 'GFS·ECMWF·ICON은 2024년 1월에 없음'은 시험한 날짜에만 맞는다. GFS·ICON은 2024-01-19 21시부터, ECMWF IFS 0.25도 일사량은 2024-03-07부터로 구체화했다. (2) KMA는 2025-02-27부터 있지만 2026년 6월과 9~10월 구간은 null이고 오늘 예보도 null이라 운영에 쓸 수 없다는 점을 추가했다. 조사 결과의 leads에 있던 'KMA와 JMA 비교' 제안은 이 제약을 감안해야 한다. (3) Historical Forecast 문서가 2021~2022년이라고만 적었다는 서술을 고쳤다. 같은 문서의 모델 표는 2016-01-01·2017-01-01로 적고 있다. (4) GSM 시작일이 API의 start_date 하한(2016-01-01)과 일치한다는 점, MSM 일사량의 2024-01-24~02-15 공백, Single Runs (이하 생략, 전문은 JSON)
- 출처:
  - [Open-Meteo Previous Runs API 문서: _previous_day1 은 유효 시각 24시간 전 예측값(day7까지). 대부분 2024년 1월부터, GFS 2m 기온 2021년 3월, JMA GSM·MSM 2018년부터](https://open-meteo.com/en/docs/previous-runs-api) (모름 (2026-10-06 열람))
  - [Open-Meteo 블로그: Weather Forecasts From Previous Model Runs (Previous Day 1은 각 실행의 24·25·26번째 시간 단계를 이어 붙인 것, 저장은 2024년 1월 시작)](https://openmeteo.substack.com/p/weather-forecasts-from-previous-model-runs) (2024-04-19)
  - [Previous Runs API 시험 호출 응답(JMA GSM 구름양): 첫 값 2016-01-02T09:00, 89,088시간 중 null 33개, 격자점 35.0/128.0](https://previous-runs-api.open-meteo.com/v1/forecast?latitude=35.07&longitude=127.75&timezone=Asia%2FSeoul&hourly=cloud_cover_previous_day1&models=jma_gsm&start_date=2016-01-01&end_date=2026-02-28) (2026-10-06 호출(저장분 재분석) 및 구간별 재호출)
  - [Previous Runs API 시험 호출 응답(JMA MSM): previous_day1 세 변수 첫 값 2022-07-02T09:00, 최신 실행값 일사량은 2017-12-05T10:00부터](https://previous-runs-api.open-meteo.com/v1/forecast?latitude=35.07&longitude=127.75&timezone=Asia%2FSeoul&hourly=shortwave_radiation_previous_day1,cloud_cover_previous_day1,temperature_2m_previous_day1,shortwave_radiation,cloud_cover&models=jma_msm&start_date=2016-01-01&end_date=2022-07-10) (2026-10-06 재호출)
  - [Previous Runs API 시험 호출 응답(모델별 시작일 탐색: models 를 gfs_seamless, icon_seamless, ecmwf_ifs025, ecmwf_ifs, kma_seamless, jma_msm, jma_gsm 으로 바꿔 호출)](https://previous-runs-api.open-meteo.com/v1/forecast?latitude=35.07&longitude=127.75&timezone=Asia%2FSeoul&hourly=shortwave_radiation_previous_day1,cloud_cover_previous_day1,temperature_2m_previous_day1&models=kma_seamless&start_date=2023-10-01&end_date=2025-12-31) (2026-10-06 호출)
  - [Previous Runs API 오류 응답: start_date 허용 범위는 2016-01-01부터](https://previous-runs-api.open-meteo.com/v1/forecast?latitude=35.07&longitude=127.75&timezone=Asia%2FSeoul&hourly=cloud_cover_previous_day1&models=jma_gsm&start_date=2013-01-01&end_date=2016-01-10) (2026-10-06 호출)
  - [Open-Meteo Historical Forecast API 문서: 각 실행의 첫 몇 시간을 이어 붙인 시계열, 긴 시계열에는 부적합. 모델 표에 JMA GSM·MSM 2016-01-01, IFS HRES 2017-01-01. 네 가지 과거 자료의 차이 설명](https://open-meteo.com/en/docs/historical-forecast-api) (모름 (2026-10-06 열람))
  - [Historical Forecast API 시험 호출 응답: 일사량 첫 값 2017-01-02, 구름양·기온 첫 값 2016-01-02](https://historical-forecast-api.open-meteo.com/v1/forecast?latitude=35.07&longitude=127.75&timezone=Asia%2FSeoul&daily=shortwave_radiation_sum,cloud_cover_mean,temperature_2m_mean&start_date=2016-01-01&end_date=2018-01-31) (2026-10-06 호출)
  - [Open-Meteo Single Runs API 문서: run 은 초기화 시각(UTC)이고 공개 시각이 아님. 전 지구 모델 4~6시간, 지역 모델 1~3시간 뒤 배포. IFS HRES 2024-03-14부터, 그 외 2026-04-02부터](https://open-meteo.com/en/docs/single-runs-api) (모름 (2026-10-06 열람))
  - [Open-Meteo JMA API 문서: GSM 전 지구 0.5도·6시간 간격(1시간으로 보간)·일사량 없음, MSM 일본·한국 0.05도·3시간마다 갱신](https://open-meteo.com/en/docs/jma-api) (모름 (2026-10-06 열람))
  - [Open-Meteo Forecast API 시험 호출 응답: 2026-10-07 일사량 18.87 MJ/m², 구름양 5%. jma_seamless 지정 호출과 같은 값, kma_seamless 지정 호출은 null](https://api.open-meteo.com/v1/forecast?latitude=35.07&longitude=127.75&daily=shortwave_radiation_sum,cloud_cover_mean&timezone=Asia%2FSeoul&forecast_days=3) (2026-10-06 재호출)

## 3. (3) 재분석 자료의 일사량이 실제 관측과 얼마나 다른가. 알려진 한계

- 상태: 확인함 / 검증 판정: 출처가 뒷받침함
- 답: ■ 문헌에 보고된 한계
- ERA5: 일 단위 전천 일사량을 전 세계 BSRN 41개소와 유럽 294개소 관측, 위성 산출물 2종과 비교한 연구에서 전 세계 평균 +4.05 W/m², 유럽 +4.54 W/m²의 양의 편향이 나왔다. 구름 낀 날은 과대, 맑은 날은 약간 과소 추정하고, 구름 재현이 약해 절대 오차가 위성 기반 자료보다 크다. 격자가 31km여서 해안과 산지에서 나빠진다. 결론은 위성 자료가 있으면 위성을 쓰고 ERA5는 대체재로 쓰라는 것이다(Urraca 외 2018, Solar Energy 164).
- NASA POWER의 일사량(CERES SYN1deg): BSRN 대비 일별 전천 일사량 편향 0.3%, RMSE 13.5%(2000~2020년, 전 지점). 위도 60도 안쪽은 편향 0.2%, RMSE 12.1%. 월 단위는 RMSE 5.7%. 격자가 1도(약 100km)다. 검증 대상은 Ed4.1이고 현재 제공 자료는 Ed4.2로 적혀 있다.
- 히마와리 위성 산출물(AMATERASS): 일본 지상 관측(SKYNET 4개소, 2016년)과 비교해 평균 20~30 W/m² 과대, RMSE 약 70~80 W/m². 구름 변동이 가장 큰 불확실성 원인(Damiani 외 2018). 단, AMATERASS는 Open-Meteo가 제공하는 히마와리 값의 자료원(JAXA P-Tree 단파복사 산출물, 알고리즘 문헌 Frouin·Murakami 2007)과 다른 산출물이다. Open-Meteo 히마와리 값 자체의 지상 검증 수치는 확인하지 못함.
- 중국 96개 지점 22년 비교: 재분석과 위성 자료 모두 해 뜰 때와 질 때, 한랭기(10~3월)에 정확도가 떨어지고, 구름 많고 지형이 험한 남부에서 추세 일치도가 가장 낮다(Wang·Wang 2025).
- 격자 자료(위성·재분석)는 지상 관측보다 정확도가 낮아 검증이 필요하다는 것이 57개 BSRN 지점 27년(1992~2018) 검증 연구의 전제다(Yang·Bright 2020, 초록만 확인. 제품별 수치는 유료 본문이라 확인하지 못함).

■ 하동 좌표에서 자료원끼리 직접 비교한 값(2015-07-03~2026-02-28, 발전량이 0보다 큰 3,800일. 지상 관측과의 비교가 아니라 자료원 사이의 차이다)
- 일평균 일사량: 히마와리 16.58, ERA5 15.21, POWER 14.33 MJ/m². ERA5는 히마와리보다 8.2% 낮고 일별 RMSE 17.4%, POWER는 13.6% 낮고 RMSE 21.3%. 전 기간(2013~2026)으로 ERA5와 POWER를 비교하면 ERA5가 6.9% 높고 일별 RMSE 19.0%, 상관 0.926.
- 흐린 날(히마와리 기준 청명도 0.3 미만, 637일)에는 ERA5가 히마와리의 1.15배, 맑은 날(0.6 초과, 2,236일)에는 0.88배였다. 문헌의 '흐린 날 과대, 맑은 날 과소'와 방향이 같다.
- 일별 발전량과의 상관: 히마와리 0.855, ERA5 0.802, POWER 0.785. 청명도로 바꾸면 히마와리 0.91, POWER 0.86, ERA5 0.85(대기권 밖 일사량 계산식에 따라 셋째 자리가 달라진다).
- 사례: 2013-01-01 발전량은 131로 다음 날 234의 56%였다. ERA5 일사량은 10.04→10.80 MJ/m²로 거의 차이가 없었고, POWER는 1.18→2.89 kWh/m²로 낮은 날임을 잡았다. 다만 NOAA GSOD 진주 지점은 2013-01-01에 눈 표시가 있어, 구름 말고 적설의 영향일 가능성도 있다(추정).

■ 정리
재분석 일사량은 월·연 단위 수준은 쓸 만하지만 하루하루의 구름을 자주 놓친다. 세 자료원의 평균 수준이 8~14% 벌어지므로 '실측 일사량'의 절대값으로 쓰면 안 되고, 날씨 영향을 걷어 내는 상대 지표로 쓰는 것이 맞다. 2015년 7월 이후는 히마와리 위성값이 발전량을 가장 잘 따라간다.
- 프로젝트에 주는 영향: 재분석 일사량은 날씨 보정용 상대 지표로만 쓰고, 드리프트 판정 임계값을 정할 때 일사량 자료원 사이의 일별 차이(17~21%)를 감안해야 한다. 이 수치는 지상 관측 대비 오차가 아니라는 점을 기획서에 밝혀야 한다.
- 검증자 메모: 직접 확인: Urraca(+4.05, +4.54, 41개소·294개소, 31km), NASA POWER 검증 표(0.3/13.5, 0.2/12.1, 5.7), Damiani(20~30, 70~80 W/m²), Wang·Wang, Yang·Bright 초록을 각각 열어 수치와 고유명사를 대조했다. 하동 자료원 간 비교는 새로 받은 응답으로 다시 계산해 평균 16.58/15.21/14.33, -8.2%/17.4%, -13.6%/21.3%, +6.9%/19.0%/0.926, 흐린 날 1.15배, 맑은 날 0.88배, 상관 0.855/0.802/0.785, 2013-01-01 사례 값을 재현했다.
고친 것: (1) Damiani가 평가한 AMATERASS는 Open-Meteo 히마와리 값의 자료원(JAXA P-Tree 단파복사)과 다른 산출물이라는 점을 밝혔다. 수치 자체는 논문과 맞다. (2) 맑은 날 수 2,230일은 재계산에서 2,236일, 청명도 상관 0.904·0.847은 0.906·0.850으로 나와 반올림해 적었다. (3) 2013-01-01 사례에 적설 가능성(GSOD 눈 표시)을 추정으로 덧붙였다. (4) POWER 검증 수치가 Ed4.1 기준이라는 점을 추가했다.
- 출처:
  - [Urraca 외, Evaluation of global horizontal irradiance estimates from ERA5 and COSMO-REA6 reanalyses using ground and satellite-based data, Solar Energy 164, 339-354 (초록은 OpenAlex API https://api.openalex.org/works/doi:10.1016/j.solener.2018.02.059 로 확인)](https://doi.org/10.1016/j.solener.2018.02.059) (2018-03)
  - [JRC Publications Repository: 위 논문의 서지 정보(저자 Urraca, Huld, Gracia Amillo, Martinez-de-Pison, Kaspar, Sanz-Garcia)](https://publications.jrc.ec.europa.eu/repository/handle/JRC108636) (2018)
  - [NASA POWER Solar Flux Assessment: CERES SYN1deg(Ed4.1) 일별 전천 일사량 편향 0.3%·RMSE 13.5%, 위도 60도 이내 0.2%·12.1%, 월별 RMSE 5.7%](https://power.larc.nasa.gov/docs/methodology/energy-fluxes/solar-validation/) (모름 (2026-10-06 열람))
  - [Damiani 외, Evaluation of Himawari-8 surface downwelling solar radiation by ground-based measurements, Atmos. Meas. Tech. 11, 2501-2521 (AMATERASS 산출물 평가)](https://amt.copernicus.org/articles/11/2501/2018/) (2018-04-27)
  - [JAXA P-Tree User's Guide: Open-Meteo 위성 API가 자료원으로 링크한 히마와리 단파복사 산출물(5km, 10분), 알고리즘 문헌 Frouin·Murakami 2007](https://www.eorc.jaxa.jp/ptree/userguide.html) (모름 (2026-10-06 열람))
  - [Wang·Wang, Evaluation of the Accuracy and Trend Consistency of Hourly Surface Solar Radiation Datasets of ERA5, MERRA-2, SARAH-E, CERES, and Solcast over China, Remote Sensing 17(7):1317 (초록은 OpenAlex API로 확인)](https://doi.org/10.3390/rs17071317) (2025-04-07)
  - [Yang·Bright, Worldwide validation of 8 satellite-derived and reanalysis solar radiation products, Solar Energy 210, 3-19 (초록은 Semantic Scholar API로 확인)](https://doi.org/10.1016/j.solener.2020.04.016) (2020-04 온라인 공개, 2020-11 게재)
  - [하동 좌표 자료원 간 비교에 쓴 시험 호출(위성). 재분석과 POWER는 (1)번 항목의 호출과 같음. 발전량은 공공데이터포털 15043409 CSV](https://satellite-api.open-meteo.com/v1/archive?latitude=35.07&longitude=127.75&daily=shortwave_radiation_sum&start_date=2013-01-01&end_date=2026-02-28&timezone=Asia%2FSeoul&models=satellite_radiation_seamless) (2026-10-06 재호출·재계산)
  - [NOAA NCEI GSOD 진주 47192: 2013-01-01의 FRSHTT 값 001000(눈 표시)](https://www.ncei.noaa.gov/access/services/data/v1?dataset=global-summary-of-the-day&stations=47192099999&startDate=2013-01-01&endDate=2013-01-03&format=json) (2026-10-06 호출)

## 4. (3-보충) 하동이나 국내 지점에서 재분석·위성 일사량을 지상 실측과 비교한 검증 결과가 있는가

- 상태: 확인하지 못함 / 검증 판정: 출처가 뒷받침함
- 답: 재분석(ERA5, MERRA-2)과 Open-Meteo 히마와리 값에 대해서는 확인하지 못함. 국내 위성 기반 일사량 자료 한 가지의 검증은 찾았다.
- 찾아본 범위: 'ERA5 일사량 검증 한국 지상관측', 'ERA5 MERRA-2 surface solar radiation validation South Korea KMA pyranometer', '재분석자료 ERA5 일사량 검증 한국 ASOS 일사 관측 비교' 등으로 검색했다. 전 세계, 유럽, 중국, 일본, 동아시아(산란 일사) 대상 연구만 나왔고 국내 지점을 다룬 재분석 일사량 검증 논문은 나오지 않았다.
- 검증 단계에서 새로 찾은 것: 한국에너지기술연구원의 위성 기반 일사량 자료(UASIBS-KIER 모델, 1996~2019년)를 국내 18개 지상 지점과 비교한 연구에서 '일 합계 일사량의 월평균'의 정규화 평균 절대 오차가 9.4%였다(Kim 외 2021, Remote Sensing 13(17):3422, 초록 확인). 위성 기반이고 월평균 기준이며, 이 과제에서 쓰려는 ERA5·NASA POWER·히마와리(Open-Meteo)와는 다른 자료다.
- 키 없이 받을 수 있는 자료 가운데 하동 인근의 지상 일사 관측은 없었다(NOAA GSOD 진주 지점에는 일사 항목이 없다). 기상청 관측 자료는 다른 과제 범위다.
- 관련해서 확인한 예보 모델의 국내 검증: 기상청 UM-LDAPS의 시간별 일사량 예보를 37개 지상 지점(2013년 1~5월)과 비교한 연구에서 상대 편향 8.2%, 상대 MAE 21.2%, 상대 RMSE 29.6%였다(Kim 외 2019). 후속 연구(4개 지점, 2018년)에서는 15분 순간 일사량의 상대 RMSE가 18 UTC 초기화 18.4%, 00 UTC 초기화 19.6%였다(Kim 외 2020).
- 추정: 하동은 지리산 남쪽 기슭과 섬진강 하구 사이여서 ERA5가 약하다고 보고된 해안·산지 조건에 가깝다. NASA POWER 응답의 표고가 218m로 나온 것도 격자 안에 산지가 많다는 뜻이다. 따라서 전 세계 평균 오차보다 클 가능성이 있으나 수치로 확인한 것은 아니다.
- 프로젝트에 주는 영향: 하동에서의 일사량 자료 오차를 숫자로 제시할 수 없으므로, 기획서에는 '자료원 간 차이'와 해외 검증 수치, 국내 위성 자료의 월평균 검증 수치를 구분해 적어야 한다.
- 검증자 메모: 직접 확인: KoreaScience 두 논문의 초록을 열어 지점 수, 기간, 8.2%·21.2%·29.6%, 18.4%·19.6%를 대조했다. 후속 연구가 4개 지점·2018년이라는 점을 덧붙였다.
반박 시도: 영어와 한국어로 세 번 검색했으나 국내 지점의 ERA5·MERRA-2 일사량 검증 논문은 찾지 못했다. 대신 국내 위성 기반 일사량 자료(KIER)의 지상 검증 논문 한 편을 찾아 초록으로 확인하고 추가했다. 질문의 '위성' 부분은 이 논문으로 일부 답이 되지만, 과제에서 쓰는 자료원에 대한 검증은 아니므로 status 는 '확인하지 못함'으로 둔다.
- 출처:
  - [Kim 외, 태양광 발전 예보를 위한 UM-LDAPS 예보 모형 성능평가, 한국태양에너지학회 논문집 39(2), 71-80 (37개 지점, 2013년 1~5월, rMBE 8.2%·rMAE 21.2%·rRMSE 29.6%)](https://koreascience.kr/article/JAKO201914456458235.do) (2019-04-30)
  - [Kim 외, 고해상도 일사량 관측 자료를 이용한 UM-LDAPS 예보 모형 성능평가, 한국태양에너지학회 논문집 40(5), 13-22 (4개 지점, 2018년, rRMSE 18.4%·19.6%)](https://koreascience.kr/article/JAKO202032961435455.do) (2020-10-30)
  - [Kim 외, Solar Resource Potentials and Annual Capacity Factor Based on the Korean Solar Irradiance Datasets Derived by the Satellite Imagery from 1996 to 2019, Remote Sensing 13(17):3422 (초록은 OpenAlex API https://api.openalex.org/works/doi:10.3390/rs13173422 로 확인. 18개 지점, 월평균 정규화 MAE 9.4%)](https://doi.org/10.3390/rs13173422) (2021-08-28)

## 5. (4) 이용 조건과 출처 표기

- 상태: 확인함 / 검증 판정: 출처가 뒷받침함
- 답: ■ Open-Meteo
- 자료 라이선스는 CC BY 4.0. 무료 API는 비상업 용도에 한하고 하루 10,000회, 시간당 5,000회, 분당 600회 미만이어야 한다. 요금 페이지에는 월 300,000회 한도도 적혀 있다. 가입과 키가 없다.
- 호출 수 계산(추가): 요금 페이지에 따르면 한 지점에 대해 변수 10개를 넘거나 기간이 2주를 넘는 요청은 여러 번의 호출로 계산한다(예: 4주치는 3.0회). 13년치를 한 번에 받는 호출은 수백 회 단위로 계산될 수 있다(추정: 페이지의 예시에 근거, 정확한 환산식은 확인하지 못함). 한 번 받아 파일로 저장해 두고 반복 호출하지 않는 것이 안전하다.
- 약관이 비상업 예로 든 것에 교육 콘텐츠에 넣는 경우와 공공 기관의 공개 연구가 들어 있다. 구독·광고가 있는 서비스, 상업 제품에 넣는 경우는 상업 이용이다. 교육 과정의 조별 프로젝트는 비상업에 해당한다고 본다(추정: 약관의 예시에 근거).
- 표기: 자료를 보여 주는 곳 옆에 'Weather data by Open-Meteo.com' 링크를 둔다. 대시보드 화면과 발표 자료에 넣으면 된다.
- 인용: Zippenfenig, P. (2023). Open-Meteo.com Weather API [Computer software]. Zenodo. https://doi.org/10.5281/ZENODO.7970649
- 재분석을 쓰면 원자료 인용을 함께 적는다: Hersbach 외 (2023). ERA5 hourly data on single levels from 1940 to present. https://doi.org/10.24381/cds.adbb2d47, 그리고 Copernicus Climate Change Service 정보를 써서 만들었다는 문구.
- 예보 모델(JMA 등)은 Open-Meteo 라이선스 페이지에 원 제공 기관으로 올라 있다.
- 히마와리(보강): Open-Meteo 문서에는 별도 표기 요건이 없다. 다만 문서가 자료원으로 링크한 JAXA P-Tree 이용 안내는 연구 산출물을 논문·보고서에 쓸 때 'P-Tree System, JAXA가 제공했다'는 취지의 문장을 넣으라고 요구한다. 히마와리 값을 발표 자료에 쓰면 Open-Meteo 링크와 함께 이 문구를 넣는 것이 안전하다. Open-Meteo를 거쳐 받은 경우에도 이 요구가 적용되는지는 확인하지 못함.

■ NASA POWER
- 키와 가입 없이 호출된다. 일별 단일 지점 요청은 변수 최대 20개.
- 요청하는 문구 두 가지: (가) 자료를 NASA Langley Research Center의 POWER 프로젝트(NASA Earth Science Division 지원)에서 얻었다는 문장, (나) POWER 프로젝트의 어느 서비스·버전에서 어느 날짜에 받았는지 적은 문장. 이번 호출은 Daily API v2.10.0, 날짜는 2026-10-06이다.
- 같은 페이지는 자료를 쓴 논문·발표를 프로젝트 메일로 알려 달라는 것과, 자료를 다른 연구자에게 넘길 때 알려 달라는 것도 요청한다(의무가 아닌 요청 형식).
- 해당 페이지에 별도의 라이선스 조항은 없었다.

■ ERA5 원본(Copernicus CDS)
- 2025-07-02부터 기존 Copernicus 제품 이용 라이선스가 CC-BY 4.0으로 바뀌었다(2025-06-13 공지).
- 내려받으려면 계정 등록, 개인 접근 토큰, 데이터셋별 이용 약관 동의가 필요하다. 가입이 필요함. Open-Meteo를 거치면 같은 ERA5 값을 가입 없이 받는다.

■ PVGIS, NOAA GSOD
키 없이 호출되는 것만 확인했고 이용 조건 문서는 열어 보지 않았다.
- 프로젝트에 주는 영향: 교육용 프로젝트는 무료 한도 안에서 쓸 수 있고, 대시보드와 발표 자료에 Open-Meteo 링크와 ERA5·NASA POWER 출처 문구를 넣으면 된다. 히마와리 값을 쓰면 JAXA 제공 문구를 추가하고, 장기간 호출은 한 번만 해서 저장해 두어야 한도에 걸리지 않는다.
- 검증자 메모: 직접 확인: Open-Meteo 약관·라이선스·과거 날씨 문서의 인용 문단, NASA POWER Referencing, ECMWF 포럼 공지(2025-06-13 작성, 2025-07-02 시행), CDS 설정 안내를 열어 한도 수치, 예시, 인용 문헌, 날짜를 대조했고 모두 원 답과 맞았다.
보강한 것: (1) 요금 페이지의 호출 수 정의와 월 한도. 13년치 한 번 호출이 여러 회로 계산된다는 점은 원 답에 없던 운영상 주의다. (2) 히마와리의 원 자료원인 JAXA P-Tree 안내에 표기 요구가 있다는 것을 찾아 '확인하지 못했다'를 일부 해소했다. (3) NASA POWER의 발표·재배포 통지 요청을 추가했다. 제도 변경 시점 문제: Copernicus 라이선스 변경(2025-07)은 현재 규칙으로 올바르게 적혀 있다.
- 출처:
  - [Open-Meteo Terms & Privacy: 무료 API 하루 10,000회·시간당 5,000회·분당 600회 미만, 비상업 용도, CC-BY 4.0 수락. 비상업·상업 예시](https://open-meteo.com/en/terms) (모름 (2026-10-06 열람))
  - [Open-Meteo Pricing: 무료 한도(월 300,000회 포함)와 호출 수 정의(변수 10개 초과 또는 2주 초과 요청은 여러 호출로 계산)](https://open-meteo.com/en/pricing) (모름 (2026-10-06 열람))
  - [Open-Meteo Licence: CC BY 4.0, 자료 표시 위치 옆에 Open-Meteo 링크, 원 제공 기관 목록(JMA, ECMWF, Copernicus 등), 인용 Zippenfenig (2023)](https://open-meteo.com/en/licence) (모름 (2026-10-06 열람))
  - [Open-Meteo Historical Weather API 문서의 Citation & Acknowledgement: Zippenfenig (2023), Hersbach 외 (2023) ERA5, Muñoz Sabater (2019) ERA5-Land, Copernicus Climate Change Service 문구](https://open-meteo.com/en/docs/historical-weather-api) (모름 (2026-10-06 열람))
  - [JAXA P-Tree User's Guide의 Reporting requirement: 연구 산출물을 쓴 논문·보고서에 P-Tree System, JAXA 제공 문장 표기 요구](https://www.eorc.jaxa.jp/ptree/userguide.html) (모름 (2026-10-06 열람))
  - [NASA POWER Referencing Guide: 출처 문장과 서비스·버전·접속 날짜 문장, 발표·재배포 통지 요청](https://power.larc.nasa.gov/docs/referencing/) (모름 (2026-10-06 열람))
  - [ECMWF 포럼 공지: CC-BY licence to replace Licence to use Copernicus Products on 02 July 2025](https://forum.ecmwf.int/t/cc-by-licence-to-replace-licence-to-use-copernicus-products-on-02-july-2025/13464) (2025-06-13)
  - [Copernicus CDS API 설정 안내: 계정 등록, 개인 접근 토큰, 데이터셋별 이용 약관 동의 필요](https://cds.climate.copernicus.eu/how-to-api) (모름 (2026-10-06 열람))

## 6. (5) 입력을 두 개로 제한할 때 발전량과 함께 쓰기 가장 좋은 날씨 값은 무엇인가. 다음 날의 실제 관측값을 쓰지 않는 조건에서

- 상태: 추정 / 검증 판정: 출처가 뒷받침함
- 답: 추천(추정: 아래 문헌과 직접 계산에 근거한 판단이다)
두 번째 입력은 '목표일(다음 날)에 대한 하루 전 예보값'으로 한다. 1순위는 예보 일사량의 하루 합계, 2013년에 가까운 긴 기간이 필요하면 예보 구름양의 낮 시간 평균이다. 전날까지의 실측 날씨는 추가 정보가 적다.

■ 문헌 근거(확인함)
- 2시간 이내 예측에는 과거 발전량 관측이, 그보다 긴 예측에는 수치예보가 가장 중요한 입력이다(Bacher 외 2009, 덴마크 지붕형 21개소, 36시간까지).
- 0~6시간은 관측 기반 방법이, 6시간에서 며칠 앞은 수치예보 모델이 더 정확하다. 태양광 출력 예보의 정확도는 주로 수평면 일사량 예보의 정확도가 좌우하고, 0~48시간 시간별 예보의 RMSE는 정격 용량의 6.4~9.2%였다. 일사량을 경사면으로 바꾸는 모델의 선택은 영향이 작았다(Pelland 외 2011, 캐나다).
- 일사량 예보가 태양광 출력 예측의 기반이다. 독일 단일 지점의 하루 전 일사량 예보는 상대 RMSE 36%, 독일 전체 평균으로는 13%(Lorenz 외 2009).
- 국내 사례(영암 태양광, 2013~2015, 36시간 앞 예측): 과거 관측 날씨만 쓴 모형의 평가 구간 R²는 최고 65.9%, 기상청 예보(습도·강수확률·강수형태·하늘상태·기온·풍향·풍속 7개 변수, 일사량 예보는 없음)만 쓴 모형은 79.1%, 둘을 합치면 80.4%(Carrera·Kim 2020). 관측에 일사량과 일조 시간이 들어 있었는데도 목표 시점의 예보가 더 나았다.
- 국내 수치예보(UM-LDAPS)의 시간별 일사량 예보 오차는 상대 MAE 21.2%, 상대 RMSE 29.6%(Kim 외 2019). 예보 일사량도 이 정도 오차를 안고 있다.

■ 하동 자료로 직접 계산한 값(참고용. 발전량 0인 날 제외, 피어슨 상관)
- 전날까지의 값과 다음 날 발전량: 어제 발전량 +0.33, 어제 일사량 +0.27~+0.30(POWER·ERA5), 어제 구름양 -0.25.
- 하루 전 예보와 목표일 발전량: JMA MSM 예보 일사량 하루 합계 +0.775(2022-07-03~2026-02-28, 1,314일), 이틀 전 예보 +0.737, JMA GSM 예보 구름양 07~18시 평균 -0.678(2016-01-03~2026-02-28, 3,686일, 연도별 -0.60~-0.75).
- 비교용 상한(같은 날 실측에 가까운 값이라 입력으로는 쓸 수 없다): ERA5 일사량 +0.79, POWER 청명도 +0.87(MSM과 같은 기간).
- 계절 신호는 약하다: 목표일 낮 길이 +0.09, 기온 -0.03~-0.07.
- 예보 일사량을 대기권 밖 일사량으로 나눈 청명도로 바꿔도 상관은 0.77로 비슷했다.
- 선형회귀 시험(LSTM이 아니다. 오차는 Σ|오차|÷Σ실제):
  · 2022-07~2024-12 학습, 2025-01~2026-02 평가(424일): 어제 값 그대로 34.4%, 7일 평균 31.3%, 7일 평균+예보 일사량 21.2%, 7일 평균+예보 청명도 약 20%, 7일 평균+예보 구름양 22.4%.
  · 같은 구간에서 이틀 전 예보 일사량을 쓰면 22.7%였다(검증 단계에서 추가 계산). 제출 시각을 엄격히 맞춰도 이득 대부분이 남는다.
  · 같은 구간에서 7일 평균에 어제 일사량이나 어제 구름양을 더하면 31.6~31.7%, 달력으로 계산되는 대기권 밖 일사량을 더하면 32.1%로 7일 평균만 쓴 회귀(32.0%)와 차이가 없었다(검증 단계에서 추가 계산). 목표일의 ERA5 일사량을 넣은 상한은 20.9%였다.
  · 2016~2021 학습, 2022년 평가(365일): 어제 값 그대로 29.7%, 7일 평균 회귀 27.2%, 7일 평균+예보 구름양 21.0%.

■ 넣는 방법(코드 구조는 그대로)
데이터 준비 단계에서 t일 행의 두 번째 값에 't일에 나온 t+1일 예보'를 넣는다. 20일 창의 마지막 행이 목표일 예보를 담게 된다. 운영 때는 Open-Meteo Forecast API에서 내일 값을 받아 같은 자리에 넣는다.

■ 선택지
(가) 예보 일사량 하루 합계(JMA MSM, Previous Runs API): 문헌상 최선이고 상관도 가장 높다. 2022-07-02 이후만 있어 학습 기간이 약 3.7년이고 성능 저하 이전 구간이 없다. 2024-01-24~02-15의 23일이 비어 있어 20일 창 1,318개 가운데 1,276개만 온전하다.
(나) 예보 구름양 낮 평균(JMA GSM): 2016-01-02 이후 10년, 빈 날이 없다. 2018년 7월 정지와 성능 저하 구간을 포함한다. 드리프트 시연을 2021~2022년으로 잡으면 이쪽이 현실적이다. 2013~2015년은 버려야 한다. 격자점이 동쪽 약 23km(0.5도 격자)다.
(다) 예보를 쓰지 않는 경우: 날씨 값은 전날까지의 실측뿐인데 회귀 시험에서 오차를 거의 줄이지 못했다. 이때는 발전량에서 뽑은 값과 비교해 정하는 것이 낫다.

■ 쓰면 안 되는 것
목표일의 재분석·위성 일사량, Historical Forecast API 값(실황에 가깝다), 목표일 실측 구름양.

■ 주의
- 예보 모델은 10년 사이 판이 바뀐다. 입력 분포가 변해 발전소와 무관한 드리프트 경보가 날 수 있다(Open-Meteo 문서도 긴 시계열에 맞지 않는다고 적는다). JMA 모델 개정 이력은 확인하지 못했다.
- 전력거래소 제출 시각까지 엄격히 맞추려면 이틀 전 예보(previous_day2, 상관 +0.737)를 써야 한다.
- 학습용 previous_day1 은 선행 24시간 이상인 값이고 운영 때 받는 내일 예보는 더 최신 실행이라 둘이 완전히 같은 조건은 아니다.
- KMA 모델은 Open-Meteo에서 2026년 6월과 9~10월 구간이 null이어서 대안으로 삼기 어렵다((2)번 참고).
- 2015-04-23~05-05처럼 발전량이 0은 아니지만 사실상 정지인 날이 있어, '0인 날 제외'만으로는 걸러지지 않는다(보충 항목 참고).
- 프로젝트에 주는 영향: 코드 구조를 바꾸지 않고 예보 한 열만 정렬해 넣으면 단순 예측 대비 오차를 3분의 1가량 줄일 여지가 있다(선형회귀 시험 기준, LSTM으로 확인한 값은 아니다). 어느 예보를 쓰느냐가 학습 기간과 드리프트 시연 구간을 결정한다.
- 검증자 메모: 직접 확인: Bacher(DTU 초록), Pelland(PDF 본문의 0~6시간/6시간~며칠, 6.4~9.2%, 경사면 변환 모델 영향 작음), Lorenz(36%·13%), Carrera·Kim(Europe PMC 본문의 65.9·79.1·80.4%, 예보 변수 7개, 관측 변수에 일사량·일조 시간 포함), Kim 외 2019를 열어 대조했고 모두 맞았다. 상관(0.33, 0.775, 0.737, -0.678, 연도별 범위)과 회귀 시험(34.4, 31.3, 21.2, 22.4, 29.7, 27.2, 21.0)을 다시 계산해 재현했다.
고친 것: (1) 어제 일사량 +0.28, 어제 구름양 -0.26은 자료원에 따라 +0.27~+0.30, -0.25로 나와 범위로 적었다. 청명도 회귀 20.1%는 19.9%로 나와 '약 20%'로 적었다. (2) '2022년 급락' 표현은 보충 항목의 월별 분석 결과에 맞춰 '성능 저하 구간'으로 바꿨다. (3) 이틀 전 예보 회귀(22.7%), 전날 실측 날씨·달력 값의 효과 없음, MSM 23일 공백과 온전한 창 수, KMA 불가, 사실상 정지일 주의를 추가했다.
남는 한계: 추천 자체는 선형회귀와 문헌에 근거한 판단이라 status 는 '추정'으로 둔다. 실습 LSTM으로 같은 이득이 나는지는 확인하지 않았다.
- 출처:
  - [Bacher·Madsen·Nielsen, Online short-term solar power forecasting, Solar Energy 83(10), 1772-1783](https://orbit.dtu.dk/en/publications/59bb32ea-4f59-491a-b5ce-2227fe099c86) (2009)
  - [Pelland·Galanis·Kallos, Solar and photovoltaic forecasting through post-processing of the Global Environmental Multiscale numerical weather prediction model, Prog. Photovolt.](https://www.nrcan.gc.ca/sites/www.nrcan.gc.ca/files/canmetenergy/files/pubs/2011-062.pdf) (2011)
  - [Lorenz 외, Irradiance Forecasting for the Power Prediction of Grid-Connected Photovoltaic Systems, IEEE JSTARS 2(1), 2-10 (초록은 OpenAlex API로 확인)](https://doi.org/10.1109/JSTARS.2009.2020300) (2009-03)
  - [Carrera·Kim, Comparison Analysis of Machine Learning Techniques for Photovoltaic Prediction Using Weather Sensor Data, Sensors 20(11):3129 (본문은 Europe PMC API로 확인. DOI 10.3390/s20113129)](https://www.ebi.ac.uk/europepmc/webservices/rest/PMC7308868/fullTextXML) (2020-06-01)
  - [Kim 외, 태양광 발전 예보를 위한 UM-LDAPS 예보 모형 성능평가, 한국태양에너지학회 논문집 39(2)](https://koreascience.kr/article/JAKO201914456458235.do) (2019-04-30)
  - [직접 계산에 쓴 하루 전 예보 시험 호출(JMA 일사량). 구름양은 (2)번 항목의 JMA GSM 호출, 발전량은 공공데이터포털 15043409 CSV](https://previous-runs-api.open-meteo.com/v1/forecast?latitude=35.07&longitude=127.75&timezone=Asia%2FSeoul&hourly=shortwave_radiation,shortwave_radiation_previous_day1,shortwave_radiation_previous_day2,cloud_cover_previous_day1&models=jma_seamless&start_date=2022-07-01&end_date=2026-02-28) (2026-10-06 호출(저장분으로 재계산, 구간별 재호출로 대조))
  - [Open-Meteo Historical Forecast API 문서: 모델 판이 시간에 따라 바뀌므로 긴 시계열에는 맞지 않는다고 안내](https://open-meteo.com/en/docs/historical-forecast-api) (모름 (2026-10-06 열람))

## 7. (보충) 날씨 자료로 '2022년 급락, 2024년 가을부터 회복'을 독립적으로 확인할 수 있는가

- 상태: 추정 / 검증 판정: 일부만 뒷받침함
- 답: 방향(2021년 이후 낮아졌다가 최근 일부 회복)은 세 자료원에서 같게 나온다. 다만 급락 시점이 2022년이라는 것과 회복이 2024년 가을부터라는 것은 날씨 자료로 그대로 확인되지 않는다.

■ 연 단위 지수(직접 계산, 재현함). 연간 발전량 합계를 같은 날들의 일사량 합계로 나눈 값(발전량 0인 날 제외), 2013년=100
- ERA5 기준: 2014년 100, 2015년 92, 2016년 98, 2017년 102, 2018년 97, 2019년 98, 2020년 100, 2021년 95, 2022년 91, 2023년 90, 2024년 92, 2025년 93.
- NASA POWER 기준: 2014년 98, 2015년 88, 2016년 93, 2017년 97, 2018년 92, 2019년 94, 2020년 94, 2021년 90, 2022년 86, 2023년 84, 2024년 87, 2025년 89.
- 히마와리 위성 기준(일사량 1 MJ/m²당 발전량, 2016년부터): 2020년 12.64, 2021년 11.79, 2022년 11.39, 2023년 11.32, 2024년 11.37, 2025년 11.71.
세 자료원 모두 2021~2023년에 내려가고 2025년에 일부 회복한다. 연 단위 회복 폭은 1~4% 수준이어서 해마다의 흔들림(예: 2018년 97, 2019년 98)과 크기가 비슷하다.

■ 월 단위로 보면(검증 단계에서 추가 계산, 추정)
- 같은 달의 2016~2020년 평균을 100으로 둔 히마와리 기준 월별 지수는 2021년 5월 97에서 6월 89로 내려간 뒤 2023년까지 85~94에 머문다. ERA5·POWER 기준도 2021년 6월에 89~90으로 내려간다. 월별 최대 출력(일 최대값의 95백분위)도 2021년 5월 44.4에서 6월 35.6으로 내려가 2019·2020년 6월(39.2, 37.7)보다 낮고, 그 뒤 같은 달 대비 6~10% 낮게 유지된다. 하락은 2022년이 아니라 2021년 6월 무렵에 시작된 것으로 보인다.
- 회복은 히마와리 기준 2024년 5~9월(93~97)과 2025년(87~98)에서 보이고, 월별 최대 출력도 2024년 6~8월이 38~39로 2023년 같은 달(34~35)보다 높다. 2024년 가을이 아니라 2024년 봄·여름부터일 수 있다.
- 원인은 날씨 자료로 알 수 없다.

■ 2015년이 낮은 이유(원 답의 '원인 확인하지 못함'을 해소)
2015-04-23~05-05의 13일 동안 하루 발전량이 0.05~3.5로 사실상 정지였다. 같은 기간 ERA5 일사량은 4~28 MJ/m², POWER 청명도는 0.15~0.77로 맑은 날이 많았다. 시간대별 값이 밤에도 0.006~0.012로 찍혀 있어 정확히 0이 아니었을 뿐이다. 이 구간과 2018년 7월 초의 비슷한 날을 빼면 2015년 지수는 ERA5 기준 97, POWER 기준 93으로 주변 해와 같아진다.

■ 단순 예측 오차의 정의
이미 확인된 36.7%(어제 값)와 34.3%(7일 평균)는 Σ|오차|÷Σ실제 정의로 계산하면 그대로 재현된다. 날짜별 비율의 평균으로 계산하면 약 203%가 되므로(중앙값은 27%) 기획서에 정의를 명시해야 한다.
- 프로젝트에 주는 영향: 발전량÷일사량 비율을 모니터링 지표로 두면 날씨 탓인 오차와 설비 성능 저하를 구분하는 드리프트 대응 정책의 근거가 된다. 드리프트 시연 구간은 2022년이 아니라 2021년 6월 전후로 잡는 편이 자료와 맞을 수 있고, 2015년 4~5월의 사실상 정지 구간은 학습 전에 따로 처리해야 한다.
- 이미 확인된 사실과 어긋나는 점: 이미 확인된 사실과 어긋나거나 보완이 필요한 점 두 가지.
(1) '발전량 0인 날 24일: 2016-12-22~26, 2018-07-13~31'은 정확히 0인 날만 센 것이다. 2015-04-23~05-05의 13일은 하루 합계가 0.05~3.5로 사실상 정지인데 이 목록에 없다. 2018-07-04, 07-07, 07-12도 합계가 1 미만이어서 2018년 정지는 07-13보다 앞서 시작된 것으로 보인다. 2020-09-08(6.7)도 맑은 날의 이상 저값이다.
(2) '2022년에 급락했고 2024년 가을부터 회복'은 봄철 맑은 날 최대 출력으로 본 서술이다. 월별 일사량 대비 발전량 지수와 월별 최대 출력으로는 2021년 6월 무렵부터 약 10% 낮아지고 2024년 5~6월 무렵부터 회복이 보인다. 2021년 봄은 하락 이전, 2022년 봄은 하락 이후여서 봄만 보면 2022년 급락으로 보였을 수 있다. 지표 정의가 달라 생긴 차이일 수 있으므로 기획서에 시점을 적기 전에 다시 확인해야 한다.
- 검증자 메모: 직접 확인: ERA5·POWER·히마와리 연 단위 지수와 단순 예측 오차 36.7%·34.3%를 다시 계산해 원 답의 숫자를 모두 재현했다(날짜별 비율 평균은 202.8%로 나와 '약 203%'로 적었다).
고친 것: 원 답은 '확인된다'고 했지만 재현된 것은 방향뿐이다. 월별 지수와 월별 최대 출력을 새로 계산하니 하락은 2021년 6월 무렵, 회복은 2024년 봄·여름부터로 보여 '2022년 급락, 2024년 가을 회복'의 시점은 뒷받침되지 않는다. 그래서 status 를 '추정'으로 낮추고 conflict 에 적었다. 재분석·위성 일사량 자체에 일별 17~21%의 자료원 간 차이가 있어 월별 지수에도 흔들림이 있다는 점은 감안해야 한다.
새로 찾은 것: 2015년 지수가 낮은 원인은 2015-04-23~05-05의 사실상 정지 구간이다. CSV 원본의 시간대별 값을 직접 읽어 확인했다. 이는 이미 확인된 '0인 날 24일' 목록을 보완해야 하는 내용이다.
임시 파일과 계산 스크립트: (작업 폴더)/solar/verify3b_r2 (v1.py, a3~a7.py, v7.py). 저장소 파일은 건드리지 않았다.
- 출처:
  - [Open-Meteo ERA5 일별 일사량 시험 호출 + 발전실적 CSV(공공데이터포털 15043409)로 계산](https://archive-api.open-meteo.com/v1/archive?latitude=35.07&longitude=127.75&start_date=2013-01-01&end_date=2026-02-28&daily=shortwave_radiation_sum,sunshine_duration,cloud_cover_mean,temperature_2m_mean&timezone=Asia%2FSeoul&models=era5) (2026-10-06 재호출·재계산)
  - [NASA POWER 일별 일사량·청명도 시험 호출 + 같은 CSV로 계산](https://power.larc.nasa.gov/api/temporal/daily/point?parameters=ALLSKY_SFC_SW_DWN,CLRSKY_SFC_SW_DWN,ALLSKY_KT,CLOUD_AMT,T2M&community=RE&longitude=127.75&latitude=35.07&start=20130101&end=20260228&format=JSON&time-standard=LST) (2026-10-06 재호출·재계산)
  - [Open-Meteo 히마와리 일별 일사량 시험 호출 + 같은 CSV로 계산(월별 지수)](https://satellite-api.open-meteo.com/v1/archive?latitude=35.07&longitude=127.75&daily=shortwave_radiation_sum&start_date=2013-01-01&end_date=2026-02-28&timezone=Asia%2FSeoul&models=satellite_radiation_seamless) (2026-10-06 재호출·재계산)
  - [공공데이터포털 한국남부발전(주)_하동하수처리장 태양광발전실적_20260228 (2015-04-23~05-05 시간대별 값 확인에 사용. 스크래치 폴더의 저장본을 읽음)](https://www.data.go.kr/data/15043409/fileData.do) (2026-02-28 기준 자료)

## 더 파 볼 단서(확인되지 않음)

- 발전소의 정확한 주소와 좌표는 찾지 못했다(OpenStreetMap 지오코딩에 '하동하수처리장', '하동공공하수처리시설' 등으로 조회했으나 결과 없음). 격자 자료에는 영향이 없지만 기획서에 적을 값은 다른 조사 항목에서 확정해야 한다.
- Open-Meteo 문서는 JMA 하루 전 예보 보관을 '2018년부터'라고 적는데 실제 응답은 GSM 2016-01-02, MSM 2022-07-02부터였다. 2016~2017년 값이 사후에 복원된 것인지, MSM의 2018~2022년 6월분이 왜 비어 있는지는 확인하지 못했다. Open-Meteo GitHub 이슈나 문의로 확인할 만하다.
- JMA GSM·MSM의 2016~2026년 모델 개정 이력을 확인하지 못했다. 개정 시점에 예보 구름양의 분포가 바뀌면 입력 드리프트로 잡힐 수 있으므로, 연도별 예보 구름양 평균을 먼저 그려 보는 것이 좋다.
- PVGIS 호출 결과 하동의 연간 발전량은 최적 기울기 37도, 손실 14% 가정에서 1,468.87 kWh/kWp였다(ERA5 2005~2023 기준). 발전실적의 2013년 연 합계 80,886을 kWh로 보면 약 55 kWp에 해당하고 시간대별 최대값 52.8과도 비슷한 크기다. 설비 용량을 정할 때 교차 확인용으로 쓸 수 있는 추정이며 실제 용량 자료로 확인해야 한다.
- 2015년의 일사량 대비 발전량 지수가 ERA5 기준 92, POWER 기준 88로 낮다. 2015년에 부분 정지나 출력 제한이 있었는지 확인하지 못했다. 발전량이 0은 아니지만 비정상적으로 낮은 날이 몰린 구간이 있는지 일별로 살펴볼 만하다.
- 하동 인근 기상청 지점(진주, 순천, 광양 등)에 일사 관측이 있는지, 있다면 ERA5·히마와리와 직접 비교하는 일은 기상청 자료가 필요해 하지 못했다. 재분석 오차를 하동 기준 숫자로 제시하려면 필요하다.
- Yang 외(2020) 'Verification of deterministic solar forecasts'(Solar Energy, DOI 10.1016/j.solener.2020.04.019)의 초록은 기후값과 지속 예측을 최적 결합한 기준 대비 RMSE 스킬 점수를 권고한다. 배포 게이트의 기준 모형 정의에 참고할 만하다. 본문은 열지 못했다.
- Antonanzas 외(2016), Das 외(2018), Ahmed 외(2020), Yang·Bright(2020) 등 리뷰·검증 논문의 본문은 유료이거나 접근이 막혀 제품별 오차 수치를 확인하지 못했다. MDPI 본문(Kim·Jung·Sim 2019, Wang·Wang 2025)도 403으로 열리지 않아 초록만 확인했다.
- Open-Meteo Previous Runs API에는 KMA 모델(kma_seamless)의 하루 전 예보가 2025년 무렵부터 있다. 최근 구간에서 JMA와 KMA 예보 가운데 어느 쪽이 하동 발전량을 더 잘 설명하는지 비교해 볼 수 있다.
- Open-Meteo 전체 자료는 AWS 공개 버킷(s3://openmeteo, CC-BY 4.0, 계정 불필요)으로도 제공된다. 어떤 모델이 언제부터 들어 있는지는 확인하지 않았다.
- 시험 호출 응답과 계산에 쓴 임시 파일은 (작업 폴더)/solar/q3 에 있다(om_era5.json, om_full.json, power_full.json, sat_himawari_daily.json, pr_jma_seamless.json, pr_jma_gsm_cloud.json). 저장소 파일은 건드리지 않았다.
