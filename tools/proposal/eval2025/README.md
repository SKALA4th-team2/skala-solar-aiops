# 2025년 평가 구간의 다시 계산

발표자료의 성과 수치와 예측 정산금 예상액을 만든 스크립트다. 팀의 최초 평가(`tools/hourly/train.py`)는 발전소별 RMSE 와 통과 여부를 남기지만, 제도 기준의 예측오차율과 정산 단가는 남기지 않는다. 그래서 같은 분할, 같은 시드, 같은 모델 구성으로 2025년의 시간별 예측을 다시 만들고 거기서 지표를 계산했다.

결과는 [`docs/proposal/evidence/eval2025-recompute-20261008/`](../../../docs/proposal/evidence/eval2025-recompute-20261008/README.md)에 있다. 2026-10-08 에 실행했다.

## 순서

`project/` 의 가상환경으로, 저장소 루트에서 실행한다.

```bash
project/.venv/bin/python tools/proposal/eval2025/run_eval.py     # 33곳의 2025년 시간별 예측 → out/<발전소>.csv
project/.venv/bin/python tools/proposal/eval2025/metrics.py      # 발전소별 지표 → metrics.json, portfolio.json
project/.venv/bin/python tools/proposal/eval2025/extra.py        # 묶음별 지표, 분할 일수 → bundles.json, splits.json
project/.venv/bin/python tools/proposal/eval2025/money.py        # 예측 정산금 예상액 → money.json
project/.venv/bin/python tools/proposal/eval2025/derived.py      # 달별 지표, 오차가 지워지는 정도 → monthly.json, cancel.json
project/.venv/bin/python tools/proposal/eval2025/candidates.py   # 발표에 쓸 후보 수치를 화면에 출력
```

| 파일 | 하는 일 |
| --- | --- |
| `run_eval.py` | `tools/hourly/train.py` 의 평가 부분만 따라 한다. 배포용 재학습과 MLflow 등록은 하지 않는다. 발전소마다 모델을 학습하므로 오래 걸린다 |
| `metrics.py` | 평가 대상 시간(실적 ÷ 설비 용량이 10% 이상)의 예측오차율과 구간 비율, 모의 단가 |
| `extra.py` | 31곳 전체와 지역 묶음의 지표, 학습·검증·평가의 일수 |
| `money.py` | 31곳을 하나의 집합전력자원으로 본 경우와 발전소별로 따진 경우의 예측 정산금 예상액 |
| `derived.py` | 달별 지표, 발전소를 모았을 때 오차가 서로 지워지는 비율과 오차의 상관 |

## 알아 둘 것

- `run_eval.py` 는 `datasets/hourly/plants/` 의 시간별 자료가 있어야 한다. 이 폴더는 커밋하지 않으므로 `tools/hourly/prepare.py` 로 먼저 만든다.
- `out/` 과 `state/` 는 커밋하지 않는다. 발전소별 예측 CSV 33개가 약 16MB 다.
- 2026-10-10 에 이 위치로 옮긴 뒤 `metrics.py`, `extra.py`, `money.py`, `derived.py` 를 2026-10-08 의 `out/` 으로 다시 돌려, 결과 JSON 7개가 그날의 값과 같은 것을 확인했다. `run_eval.py` 는 옮긴 뒤에 다시 돌리지 않았다.
- 단가는 2026-07-25 시행 규칙의 값(4% 이하 4원/kWh, 4% 초과 6% 이하 3원/kWh)이고 계수는 1.0 으로 뒀다. 제도의 기준은 [결정0015](../../../docs/decisions/0015-incentive-reference-metrics.md)와 같다.
