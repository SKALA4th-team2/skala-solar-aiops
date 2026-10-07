# 0008: 재학습과 버전 교체

- 상태: 제안
- 날짜: 2026-10-07
- 정한 사람: (아직 없다. 팀이 확정할 때 적는다)

## 배경

HAIC 스켈레톤의 재학습 경로는 이렇다. 드리프트로 판정되면 `check_and_trigger` 가 가장 최근에 올린 파일의 마지막 행들을 읽어 `fine_tune` 에 넘긴다. `fine_tune` 은 지금의 Production 모델을 불러 낮은 학습률(1e-4)로 10 epoch 이어서 학습하고, 게이트를 통과하면 MLflow 에 새 버전으로 등록해 Production 으로 올린다. 스케일러는 다시 맞추지 않는다.

코드를 읽고 돌려 보니 정해야 할 것이 다섯 가지 나왔다.

1. **재학습에 쓰는 자료와 거는 때.** 받은 배치가 아니라 "가장 최근에 올린 파일"의 끝을 읽는다. 시연하는 배치의 날짜와 파일의 끝 날짜가 다르면 엉뚱한 구간으로 재학습한다. 그리고 드리프트로 판정되면 곧바로 재학습한다. 수준이 막 바뀐 때에는 그 41행에 바뀌기 전의 날이 섞여 있다.
2. **겹쳐 도는 재학습.** 재학습은 `POST /predict/batch-test` 의 응답 안에서 돈다. 같은 요청이 두 번 오면 두 번 재학습한다. 막는 장치가 없다.
3. **승격한 뒤의 서빙 모델.** 서버는 한 번 불러온 모델을 메모리에 들고 있다(`model_loader._model_cache`). 승격한 뒤 이 값을 바꾸는 코드가 어디에도 없다. 서버를 다시 띄워도 `MODEL_SOURCE` 의 기본값이 `local` 이라 MLflow 의 새 버전을 읽지 않는다.
4. **버전을 알 방법.** `/predict` 의 `model_version` 은 `"v1-local"` 이나 `"production"` 이라는 고정된 글자다. 버전이 바뀌어도 응답이 같다.
5. **되돌리기.** 게이트에서 막혀 "올리지 않는 것"은 있지만, 이미 올린 버전을 "이전 버전으로 되돌리는 것"은 없다.

## 검토한 선택지

재학습에 쓰는 자료

| 선택지 | 얻는 것 | 잃는 것 |
| --- | --- | --- |
| (가) 지금 구조를 둔다. 가장 최근에 올린 파일의 마지막 41행을 쓴다. 시연에서는 배치의 끝 날짜에서 자른 파일을 올려 맞춘다 | 코드를 고치지 않는다 | 파일과 배치를 사람이 맞춰야 한다. 어긋나도 오류가 나지 않는다 |
| (나) 판정에 쓴 배치를 그대로 재학습에 넘긴다 | 판정한 자료와 학습한 자료가 늘 같다 | `check_and_trigger` 와 `batch_test` 가 주고받는 모양을 고쳐야 한다 |

재학습을 거는 때

| 선택지 | 얻는 것 | 잃는 것 |
| --- | --- | --- |
| (가) 판정되면 곧바로(현재 코드) | 빨리 대응한다 | 41행에 수준이 바뀌기 전의 날이 섞인다. 그런 자료로 재학습한 결과는 아무도 재지 않았다 |
| (나) 배치 41행의 앞 20일과 뒤 21일의 성능 지표가 함께 임계값 아래일 때 | 조사가 재학습의 효과를 잰 조건(내려간 뒤의 행만으로 된 41행)에 가깝다. 기억할 상태가 없어 배치 하나만 보고 정할 수 있다 | 수준이 바뀐 뒤 한 달쯤은 알림만 나가고 이전 모델이 예측한다 |
| (다) 첫 경고로부터 41일 뒤 | 41행이 모두 경고 뒤의 날이다 | 첫 경고의 날짜를 서버가 기억해야 한다. 더 늦다 |

승격한 뒤의 서빙 모델

| 선택지 | 얻는 것 | 잃는 것 |
| --- | --- | --- |
| (가) 승격에 성공하면 새 모델을 먼저 불러오고, 불러오는 데 성공했을 때만 메모리의 모델을 바꾼다 | 서버를 내리지 않고 바뀐다. 불러오다 실패해도 이전 모델로 계속 응답한다 | 코드를 더해야 한다 |
| (나) 승격한 뒤 서버를 사람이 다시 띄운다 | 코드를 고치지 않는다 | 다시 띄우는 동안 응답하지 못한다. 잊으면 이전 모델이 계속 나간다 |
| (다) 요청마다 레지스트리를 확인한다 | 늘 최신이다 | 요청마다 느려진다 |

되돌리기

| 선택지 | 얻는 것 | 잃는 것 |
| --- | --- | --- |
| (가) 손으로 하는 절차를 문서로 둔다. 새 버전을 Archived 로 내리고 서빙 모델을 다시 불러온다 | 레지스트리 수준에서 동작을 확인했다 | 사람이 해야 한다 |
| (나) 승격 뒤 일정 기간의 오차가 나쁘면 자동으로 되돌린다 | 사람이 없어도 된다 | 판단 기준과 구현이 크다. 발표까지 만들 수 없다 |

## 결정

다음을 제안한다.

**재학습에 쓰는 자료와 방법**

- 가장 최근에 올린 파일의 마지막 **41행**(입력 20일 + 판정 21일)을 쓴다. 표본 21개가 나오고 앞 16개로 학습해 뒤 5개로 게이트를 잰다.
- 이어서 학습한다(warm start). 지금의 Production 가중치에서 시작해 학습률 1e-4, 10 epoch 이다. 코드의 값을 그대로 둔다.
- 스케일러는 다시 맞추지 않는다. 업로드 파일의 종류를 바꿀 때만 스케일러와 모델을 함께 다시 만든다.
- 발표까지는 (가)로 한다. 시연용으로 배치의 끝 날짜에서 자른 사본을 올려 날짜를 맞춘다. (나)는 그 뒤의 과제로 둔다.
- 41행 안에 정지나 보류인 날이 있으면 재학습하지 않는다([0007](0007-facility-vs-model-branch-and-alerts.md)).
- **거는 때는 (나)** 로 한다. 뒤 21일의 편차만 임계값([0006](0006-monitoring-metric-and-thresholds.md)) 아래이면 알리기만 하고, 앞 20일의 편차도 아래일 때 재학습한다.

**겹쳐 도는 재학습을 막는다**

- 재학습이 도는 동안에는 새 재학습을 시작하지 않는다(서버 안의 잠금 하나).
- 재학습에 쓴 자료의 끝 날짜를 기억해 두고, 같은 끝 날짜로는 다시 재학습하지 않는다.
- 재학습을 마치면 쌓아 둔 최근 예측 기록(`recent_predictions`)을 비운다. 비우지 않으면 다음 요청이 같은 21건으로 또 판정한다.

**승격과 서빙 모델**

- 운영은 `MODEL_SOURCE=mlflow` 로 띄운다.
- 승격할 때 이전 Production 버전을 Archived 로 내린다. 지금 코드는 내리지 않아 두 버전이 함께 Production 에 남는다.
- 승격에 성공하면 (가)처럼 새 모델을 먼저 불러온 뒤 메모리의 모델을 바꾼다. 불러오지 못하면 이전 모델을 그대로 쓰고 로그에 남긴다.
- `model_version` 에 레지스트리의 버전 번호를 싣는다(예: `"v2"`). `/health` 에도 지금 올라와 있는 버전을 싣는다.
- "버전이 바뀌었다"는 응답의 글자가 아니라 **레지스트리의 Production 버전과 서버가 불러온 버전이 같은지**로 확인한다.

**게이트 실패와 되돌리기는 다른 일이다**

- 게이트 실패: 새 모델을 등록하지 않는다. 운영 버전은 그대로다. 현재 코드에 있는 동작이다.
- 되돌리기: 이미 올린 버전을 내리고 이전 버전으로 돌아간다. 현재 코드에 없다. 발표까지는 (가)의 손 절차로 둔다.

## 근거

| 수치 | 조건 (기간, 분할, 시드 수) | 출처 |
| --- | --- | --- |
| 메모리의 모델(`_model_cache`)을 바꾸는 줄은 `model_loader.py` 안에만 있다. 재학습과 승격 경로에는 0줄이다 | 커밋 `58d6ff8` 의 코드를 읽어 센 값이다. 서버에서 실행해 확인한 것은 아니다(빈칸 때문에 재학습 경로가 돌지 않는다) | 코드 확인. [`static_scan.txt`](../proposal/evidence/static_scan.txt) 4 |
| `model_version` 이 되는 값은 `"v1-local"` 과 `"production"` 두 가지 고정 글자다 | `model_loader.py` 99행, 126행 | 코드 확인. [`static_scan.txt`](../proposal/evidence/static_scan.txt) 5 |
| 앱의 승격과 같은 두 호출을 하면 버전 1 과 2 가 **함께 Production** 이 되고 `models:/HAIC_Predictor/Production` 은 버전 2 를 가리킨다. 버전 2 를 Archived 로 내리면 다시 버전 1 을 가리킨다 | MLflow 3.16.0, 검증용 사본의 레지스트리. `train_and_register.py` 61 ~ 62행과 같은 인자로 직접 불렀다. 앱의 재학습을 돌린 결과가 아니다. "가리키는 버전"은 MLflow 가 이 주소를 풀 때 쓰는 조회(`get_latest_versions`)로 본 것이고, 주소로 모델을 불러와 확인한 것은 아니다 | 직접 실행. [`registry_semantics.json`](../proposal/evidence/registry/registry_semantics.json) |
| 재학습의 조건(앞 20일과 뒤 21일이 함께 임계값 아래)이 처음 채워지는 날: 변화가 없으면 37개 시작일 가운데 0개. 14% 를 낮추면 32개(가운데 26일째, 7 ~ 35일째). 8.5% 를 낮추면 28개(가운데 31일째, 9 ~ 39일째) | 2025년에 인위로 낮춘 값. 기준선은 2025-02-28 에 고정. 날마다 최근 41일을 본다. 내려간 날을 1일째로 세고 46일째까지 봤다. 표본 안의 계산이다 | 직접 계산. [`threshold_sweep.txt`](../proposal/evidence/threshold_sweep.txt) |
| 시연 배치(2025-06-21 ~ 07-31)는 그대로면 앞 20일 −2.8%, 뒤 21일 −2.2%. 발전량에 0.86 을 곱하면 −16.3%, −15.6% | 같은 기준선 | 직접 계산. [`threshold_sweep.txt`](../proposal/evidence/threshold_sweep.txt) |
| 조사가 재학습의 효과를 잰 배치는 "주입 뒤 행만으로 된 배치"다 | 2025년 구간, 주 단위 시작일 | [T5](../research/merged/T5-drift-demo.md) |
| 게이트에서 막힌 학습 뒤 레지스트리에는 새 버전이 없고 버전 1 이 Production 으로 남았다 | 예보 업로드 파일로 `train_and_register.py` 를 돌린 결과(`rmse=41.59 > 4.0`) | 직접 실행. [`registry_3-after-hadong-train.json`](../proposal/evidence/registry/registry_3-after-hadong-train.json) |
| 스케일러 파일이 Production 모델과 다른 자료의 것으로 바뀌었다. 종가 105.61 ~ 195.17 에서 발전량 5.886 ~ 338.832 로 | HAIC 예시 파일로 버전 1 을 올린 뒤, 예보 업로드 파일로 `train_baseline_v1.py` 를 돌렸다. 스크립트는 빈칸에서 멈췄지만 스케일러는 그 앞에서 이미 덮어썼다. Production 은 버전 1 그대로다 | 직접 실행. [`registry_1-after-haic-train.json`](../proposal/evidence/registry/registry_1-after-haic-train.json), [`registry_2-after-hadong-baseline.json`](../proposal/evidence/registry/registry_2-after-hadong-baseline.json) |
| `MODEL_SOURCE=mlflow` 에 eager 로 띄우면 서버가 뜨지 못한다(종료 코드 3). lazy 로 띄우면 `/predict` 가 500 이다 | `model_loader.py` 125행과 167행의 빈칸 | 직접 실행. [`07_server_mlflow_eager.log`](../proposal/evidence/logs/07_server_mlflow_eager.log), [`08_server_mlflow_lazy.log`](../proposal/evidence/logs/08_server_mlflow_lazy.log) |
| 학습률과 epoch 를 키운 재학습(1e-3, 50 epoch)은 변화가 없는 구간에서 RMSE 를 40.3kWh 에서 48.8kWh 로 올렸다. 실습 설정(1e-4, 10 epoch)에서는 40.3kWh 대 40.7kWh 였다 | 예보를 넣은 실습 LSTM(학습 2023-11-07 ~ 2025-02-28), 시드 3개 × 시작일 43개. 저장된 결과의 재집계다 | [T5](../research/merged/T5-drift-demo.md) |
| 모델을 불러오는 데 0.89초가 걸렸다 | 같은 PC, 한 번. 승격 뒤 새 모델을 불러오는 동안 이전 모델로 응답하면 이 시간이 사용자에게 보이지 않는다 | 직접 실행. [`latency_model.json`](../proposal/evidence/latency_model.json) |

스케일러 항목은 따로 적어 둘 만하다. 스케일러는 파일 하나(`serving_app/models/scaler.pkl`)이고 모델 버전과 짝이 지어져 있지 않다. baseline 스크립트를 다시 돌리면 게이트의 결과와 상관없이 덮어쓴다. 그 뒤의 학습이 게이트에서 막히면 "이전 모델에 새 스케일러"가 되고, 오류 없이 예측만 틀어진다. 발표까지는 절차로 막는다(파일 종류를 바꿀 때만 baseline 을 돌리고, 그때는 모델도 반드시 새로 올린다). 그 뒤에는 스케일러를 모델과 함께 MLflow 에 기록해 버전과 짝을 짓는 것을 과제로 둔다.

## 함께 고칠 곳

- `docs/proposal/3-operations-design.md`, `docs/proposal/4-architecture.md`, `docs/proposal/5-api-spec.md`(응답의 `model_version`, `/health`)
- `project/serving_app/model_loader.py`: 승격 뒤 다시 불러오는 함수, `LoadedModel.version` 에 실제 버전 번호
- `project/serving_app/train_and_register.py` 의 `_register_if_gate_passed`: 이전 버전을 Archived 로
- `project/serving_app/monitoring/retrain_trigger.py` 의 `check_and_trigger`: 앞 20일의 편차를 보는 조건, 잠금, 끝 날짜 기억, 승격 뒤 다시 불러오기 호출
- `project/serving_app/routers/predict.py` 의 `recent_predictions`: 재학습 뒤 비우기
- `project/serving_app/routers/health.py`: 지금 올라와 있는 버전
- `project/serving_app/Dockerfile`: 이미 `MODEL_SOURCE=mlflow`, `LOADING_MODE=eager` 다. 값은 그대로 둔다

## 다시 볼 조건

- 빈칸을 채운 뒤 승격 전후의 서빙 버전을 실제로 확인했을 때. 코드를 읽어 얻은 결론과 다르면 이 기록을 고친다
- 재학습을 요청의 응답 안이 아니라 따로 도는 작업으로 옮기기로 할 때
- 자동으로 되돌리는 기능이 필요하다고 판단될 때
- 스케일러를 모델과 함께 버전으로 관리하기로 할 때
