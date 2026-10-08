# 입력 변수 추가 실험

기존 서버나 다른 실험 파일을 변경하지 않고 관측 날씨·계절·과거 예보의 입력 효과를 비교한다. 결과는 `docs/proposal/evidence/feature_ablation_20261007/REPORT.md`에 생성한다.

`project/`에서 다음 순서로 실행한다. 이 실행 환경은 기존 `.venv`의 TensorFlow·XGBoost·numpy·pandas를 사용하며 버전은 결과의 `environment.json`에 기록한다.

```powershell
.venv/Scripts/python -X utf8 -B ../tools/feature_ablation/experiment.py --stage prepare
.venv/Scripts/python -X utf8 -B ../tools/feature_ablation/experiment.py --stage trees
.venv/Scripts/python -X utf8 -B ../tools/feature_ablation/experiment.py --stage lstm
.venv/Scripts/python -X utf8 -B ../tools/feature_ablation/audit_inputs.py
.venv/Scripts/python -X utf8 -B ../tools/feature_ablation/experiment.py --stage report
```

`prepare`가 데이터·기간·변수·탐색 범위를 고정한 `protocol.json`을 먼저 저장한다. `trees`와 `lstm`은 독립 실행 가능하다. 완료 전 `report`를 실행하면 예상 학습 횟수 검증에서 실패한다. 동일 명령을 다시 실행하면 해당 실험 결과를 덮어쓰므로 새 실험은 코드의 OUT을 별도 디렉터리로 지정한다.

- 기존 하동: 모든 변수 조합이 2025년 같은 365일을 평가한다. 기온·일조시간을 추가할 때도 기준 모델의 평가일을 바꾸지 않는다.
- 추가 32개 호기: 연속 930일 이상인 가장 최근 구간 중 최대 1,825일을 사용한다. 마지막 365일 시험, 그 전 180일 검증, 나머지 학습. 호기별 시험 기간은 protocol에 남긴다.
- 관측 날씨: 행 d에는 d-1일 값을 사용한다. 입력 끝이 t-1이므로 최신 관측 날씨는 t-2다. 대상일 실제 날씨를 사용하지 않는다.
- 예보: 원본 Previous Runs의 `previous_day1`을 날짜로 연결하고 기존 하동 예보 업로드의 Volume과 대조한다. 기온 예보는 보유하지 않아 포함하지 않았다.
- LSTM: 기존과 같은 32→32→16 및 Dense16→1 구조에서 입력 변수 수만 변경한다. 고정 학습률·80 epoch·시드 3개. 검증 오차가 가장 낮은 epoch 가중치를 사용하고 시험 결과에 따라 설정을 바꾸지 않는다.
- XGBoost: 20일 창을 펼쳐 모든 변수 조합에 같은 설정과 검증 조기종료를 적용한다. 결측은 XGBoost가 처리하고 LSTM은 학습 구간 중앙값으로만 대체한다.
- 데이터 스케일러는 학습 구간에서만 맞춘다. 검증/시험으로 다시 맞추지 않는다. 최종 모델의 train+validation 재학습은 하지 않아 모든 조합의 학습 종료 시점이 같다.
- 음수 예측은 모든 학습기에서 0으로 제한한다. 시험일의 0 발전량이나 큰 오차를 사후 제거하지 않는다.

결과 파일에는 각 조합의 검증·시험 날짜별 예측, 시드별 학습곡선, RMSE·MAE(kWh/일), 변수 추가에 따른 호기별 개선율, 14일 블록 부트스트랩, 출처 해시 검사가 있다. 다지역 호기들이 서로 독립적인 표본이라고 가정하지 않는다. LSTM 3시드 평균 예측의 오차와 시드별 오차는 구별한다.

TensorFlow는 이 Windows 환경에서 numpy보다 먼저 import하고 `TF_ENABLE_ONEDNN_OPTS=0`으로 실행한다. 기존 benchmark에서 기록한 초기화 우회 방식이다. 모델 파일·MLflow·서버 상태를 변경하지 않는다.
