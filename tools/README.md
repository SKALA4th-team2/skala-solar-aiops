> 현재 시간별 도구: hourly/prepare.py → train.py → finalize.py. 검증 hourly/verify.py. 기준 등록부 hourly/candidates.json. 실행은 project/에서 한다. 상세는 [운영 안내](../docs/backend-runbook.md). 아래 일별 도구는 이전 계약이다.

# 도구

서빙 앱 밖에서 쓰는 도구를 둔다. `project/` 안에는 두지 않는다.

## 데이터를 만든 스크립트

`datasets/` 의 파일이 어떻게 만들어졌는지 확인하기 위한 **참고용**이다. 조사할 때 쓰던 폴더의 절대 경로가 들어 있어서 그대로는 실행되지 않는다. 다시 만들려면 스크립트 맨 위의 경로를 고친다.

| 폴더 | 파일 | 하는 일 |
| --- | --- | --- |
| [`build_asos_upload/`](build_asos_upload/) | `hd_01_build.py` | 발전 실적과 기상청 ASOS 연도별 일자료를 합쳐 `hadong_daily_full.csv`, `hadong_upload.csv`, `hadong_upload_forecast_proxy.csv`, 일조 시간 판 2종을 만든다. ASOS 연도별 원본(1995 ~ 2025)이 따로 있어야 한다 |
| | `hd_02_verify.py` | 만든 파일의 행 수, 날짜 이어짐, 원본 대조, 날짜 밀림을 점검한다 |
| | `hd_03_loadrows_check.py` | 실습 코드의 읽기와 창 만들기로 파일을 읽어, 대상일의 값이 입력에 들어가지 않는지 확인한다 |
| | `pi_expected_model.json` | 성능 지표의 기대 발전량을 계산하는 선형식의 계수. 2013 ~ 2014 자료로 맞춘 값이다 |
| [`build_forecast_upload/`](build_forecast_upload/) | `00_fetch_weather.py` | Open-Meteo 에서 재분석과 예보 기록을 받아 `raw/wx_archive_daily.csv`, `raw/wx_prevruns_daily.csv` 를 만든다. 키와 로그인이 필요 없다 |
| | `20_build_upload.py` | 발전 실적과 하루 전 일사량 예보를 합쳐 `hadong_upload_forecast_jma.csv` 를 만든다 |
| | `r01_file_check.py` | 검토자가 따로 써서 위 파일을 원본과 전 행 대조한 스크립트 |

## 적량면 관측 자료 검토

[`jeokryang/`](jeokryang/)에 있다. 경로가 저장소 기준이라 저장소 루트에서 그대로 실행된다. 결과와 해석은 [`../docs/research/jeokryang-sensor.md`](../docs/research/jeokryang-sensor.md)에 있다.

| 파일 | 하는 일 | 필요한 것 |
| --- | --- | --- |
| `01_build_daily.py` | 적량면 시간 자료(누적 일사량)를 하루 값으로 바꿔 `datasets/jeokryang_daily.csv` 를 만든다 | 원본 시간 자료(저장소에 없음). 경로를 인자로 준다 |
| `02_compare_with_gwangyang.py` | 광양 관측, 재분석 자료와 견줘 유효 일수, 빈 구간, 센서 수준이 바뀐 날짜를 찾는다 | pandas |
| `03_validity_for_generation.py` | 적량 일사량이 하동 발전량을 얼마나 설명하는지 광양과 같은 날들에서 견준다 | pandas |
| `04_lstm_sensor_step.py` | 2024년 2월의 센서 계단을 실습 LSTM 과 같은 구조로 재현하고, 실습 방식의 재학습 전후를 견준다 | tensorflow. 몇 분 걸린다 |
| `common.py` | 위 스크립트가 함께 쓰는 자료 읽기와 지표 함수 | |
| `out/` | 2026-10-07 에 돌린 출력, 씨앗별 결과, 인위 계단 확인 결과 | |

## 여러 발전소 자료의 준비 도구

[`multi_plant/`](multi_plant/)에 있다. 경로가 인자라 저장소 루트에서 그대로 실행된다. `single_pc_probe.py` 를 뺀 나머지는 표준 라이브러리만 쓴다. 자세한 쓰는 법은 [`multi_plant/README.md`](multi_plant/README.md)에, 계약은 [`../docs/proposal/multi-plant-data-contract.md`](../docs/proposal/multi-plant-data-contract.md)에, 돌린 기록은 [`../docs/proposal/evidence/multi-plant/validation.md`](../docs/proposal/evidence/multi-plant/validation.md)에 있다.

| 파일 | 하는 일 | 쓰는 법 |
| --- | --- | --- |
| `convert_kospo_raw.py` | 한국남부발전 「태양광발전실적」 원자료를 정규화 실적(하루, 시간대별)과 계보 기록으로 바꾼다. 빈 칸을 0 으로 채우지 않는다 | `python tools/multi_plant/convert_kospo_raw.py --raw <원자료> --plant-id <plant_id> --out-root <자료 폴더>` |
| `validate.py` | 발전소 등록부, 포트폴리오 구성, 발전소별 실적이 계약을 지키는지 본다. 중복 등록, 단위, 날짜의 빠짐과 중복, 결측, 다른 발전소의 행 | `python tools/multi_plant/validate.py --data-root <자료 폴더>` |
| `portfolio_capacity.py` | 포트폴리오의 설비 용량 합계(kW, MW)를 중복 없이 낸다. 용량을 모르는 발전소는 빼고 알린다 | `python tools/multi_plant/portfolio_capacity.py --data-root <자료 폴더> --portfolio <portfolio_id> [--date YYYY-MM-DD]` |
| `coverage.py` | 발전소별 기간과 창의 수, 포트폴리오의 공통 평가 기간과 커버리지를 낸다. 창에 발전소가 섞이지 않는지 본다 | `python tools/multi_plant/coverage.py --data-root <자료 폴더> [--portfolio <portfolio_id>]` |
| `evaluate.py` | 발전소별 오차와 포트폴리오 합계의 오차를 같은 대상일에서 낸다. 전일값, 7일 평균과 견주고 모델의 예측 파일도 함께 견줄 수 있다 | `python tools/multi_plant/evaluate.py --data-root <자료 폴더> --portfolio <portfolio_id> --start <날짜> --end <날짜> [--predictions <CSV>] [--hourly]` |
| `bundle_check.py` | 모델, 스케일러, 피처의 뜻이 서로 짝이 맞는지 본다 | `python tools/multi_plant/bundle_check.py write ...`, `check ...` |
| `selftest.py` | 합성 자료로 실패 사례 21건을 돌려 위 도구가 잘못된 자료를 실제로 잡는지 본다 | `python tools/multi_plant/selftest.py [--out <폴더>]` |
| `single_pc_probe.py` | 한 PC 의 학습 시간, 메모리, 학습 중의 예측 시간을 잰다. 검증용 사본에서만 돌린다. tensorflow 와 mlflow 가 필요하다 | `python tools/multi_plant/single_pc_probe.py --project <사본>/project --out <폴더>` |
| `common.py` | 계약의 열과 단위, 읽기와 검증 함수 | |

- 자료 폴더는 저장소 안에서는 `datasets/plants` 다. 다른 발전소의 자료가 저장소 밖에 있으면 그 폴더를 `--data-root` 로 준다.
- `evaluate.py --hourly` 의 값은 제도의 식을 단순 기준 예측에 적용한 참고값이다. 우리 모델의 값도 정산 성능도 아니다.
- 합성 자료의 수치를 성능이나 제도 요건의 근거로 쓰지 않는다.

## 기획서의 검증 도구와 조사의 재현 도구

- [`proposal/`](proposal/): 기획서 ①~⑥ 의 검증과 그림을 만드는 도구. 문서를 고친 뒤 `python tools/proposal/check_docs.py`, `python tools/proposal/check_mermaid.py` 로 점검한다. 설명은 [`proposal/README.md`](proposal/README.md)에 있다.
- [`verify/`](verify/): 조사 판정의 재현과 FastAPI 계약의 테스트. 설명은 [`verify/README.md`](verify/README.md)에 있다.

## 여러 발전소 데이터 확장

[`build_multi_plant/`](build_multi_plant/README.md)는 현재 저장소에서 재실행할 수 있는 수집·ASOS 대조·호기별 결합·검증 도구다. 위 조사용 스크립트와 달리 개인 절대 경로가 없으며 ASOS 원본 위치만 명령행으로 받는다. 결과는 `datasets/multi_plant/`에 저장한다.

## 입력 변수 비교 실험

[`feature_ablation/`](feature_ablation/README.md)은 하동 LSTM 3시드와 추가 32개 호기의 XGBoost로 과거 날씨·계절·사전 예보 입력을 비교한다. 결과·날짜별 예측·누수 검증은 `docs/proposal/evidence/feature_ablation_20261007/`에 저장한다. 서버 모델을 변경하지 않는다.

## 앞으로 추가할 항목

지역별 과거 예보 수집과 원본 재집계 검증은 [`build_plant_forecasts/`](build_plant_forecasts/README.md)에서 실행한다. Open-Meteo JMA MSM의 24/48시간 선행 예보를 캐시하고 발전소별 대상 날짜 테이블로 연결한다. 실제 발표 시각을 제공하는 자료는 아니다.

모델 학습·검증 도구는 [`model_benchmark/`](model_benchmark/README.txt)(기존 하동 예보 입력 비교)와 [`multi_plant_models/`](multi_plant_models/README.md)(추가 호기별 관측 입력 비교·모델 저장·MLflow 후보 등록)에 있다. 두 실험은 날씨 입력의 의미가 다르므로 점수를 직접 비교하지 않는다. 명령은 `project/`에서 실행한다.

새 지역별 JMA MSM 예보로 다시 학습하는 도구는 [`forecast_models/`](forecast_models/README.md)에 있다. 최신 GitHub API의 20일×2입력 계약에 맞춘 LSTM·XGBoost·Prophet, 앙상블과 개소별 모델/스케일러 묶음을 만든다. 연결 방법은 [모델 인수인계](../docs/forecast-model-handoff.md)에 있다.

- `/predict` 와 `/predict/batch-test` 에 보낼 요청 본문 예시
- 응답 시간을 재는 스크립트
- 실제 발전 실적에서 시연용 41일 배치를 잘라 내는 스크립트

## 2026-10-07 백엔드 통합

tools/aiops/에 초기 MLflow 등록, 포트폴리오 품질 평가, 모델 seed 내보내기, 실제 자료 재생, API·정책·재학습 검증을 추가했다. 사용법은 aiops/README.md와 ../docs/backend-runbook.md를 따른다.
