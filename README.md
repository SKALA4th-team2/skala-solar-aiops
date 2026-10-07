# Solar AIOps — 시간별 태양광 예측

SKALA 모델 서빙·AIOps 미니 프로젝트. **31개 발전소별 LSTM이 1시간 발전량을 24시간 분량으로 예측**하며, FastAPI·MLflow·SQLite 작업자와 프론트를 PC 한 대에서 실행한다.

2026-10-07 최신 변경: 일별 예측을 시간별로 전환했다. 기존 33개소 모두 원본 시간별 자료를 확보했고, 시간별 독립 성능 검증을 통과한 31개만 운영한다. 신인천전망대·용수리 2개는 품질 미달로 제외했다. 하동 독립 평가 RMSE는 **4.45 kWh/시간**이다. 일별 XGBoost·Prophet·앙상블 비교는 과거 실험이며 이번 시간별 릴리스는 LSTM이다.

- 입력: 전날 실적 24시간 + 대상일 기상예보 24시간. 출력: 시간별 kWh 24개.
- 시간자료 결측·물리 상한·일합계 불일치·중복을 검사하며 결측을 0이나 일평균으로 채우지 않는다.
- 개소별 model.keras + scaler.pkl + manifest.json, MLflow 버전 등록과 로드 검증.
- 업로드 → 시간별 검사 → 조건부 재학습 큐 → 실제 LSTM 학습 → 성능 게이트 → 버전 교체·롤백.
- 프론트: 24/72/168시간 차트, 대상일 24시간 예측표, CSV 업로드·예측 테스트·AIOps·모델 이력.

모든 명령은 project/에서 실행한다. 기존 Python 3.11 가상환경이 준비되어 있다.

```powershell
cd project
.venv\Scripts\python -X utf8 scripts/run_backend.py
```

화면 http://127.0.0.1:8077/ , API http://127.0.0.1:8077/docs . 최초 설치와 다른 PC 이전은 [운영 안내](docs/backend-runbook.md)를 따른다. 모델·DB·업로드는 Git에 넣지 않으므로 다른 PC에서는 재생성 또는 hourly-seed 전달이 필요하다.

[채택 결정 0014](docs/decisions/0014-hourly-forecast-and-aiops.md) · [시간별 데이터](datasets/hourly/README.md) · [검증 결과](docs/proposal/evidence/hourly_20261007/README.md) · [API 명세](docs/proposal/5-api-spec.md) · [기획서](docs/proposal/README.md)

현재 화면은 보관 자료(2026-02-27까지)의 재생이다. 기상은 지역격자의 48시간 선행 JMA 예보이며 현장 관측이나 실시간 수집이 아니다. 당시 공개시각은 검증하지 못했다. 가상 31개소 설비용량 합계는 22.914065MW지만 제도 참여·시장 제출·정산 성능을 검증한 것은 아니다. 컨테이너 실제 실행은 Docker 미설치로 확인하지 못했다.

이전 일별 모델·실험은 별도 runtime과 증빙에 남기고 시간별 운영에 혼용하지 않는다. 연구 보관 자료는 docs/research/, 과거 결정은 docs/decisions/에 있다. 기여 규칙은 [CONTRIBUTING.md](CONTRIBUTING.md), 작업 규칙은 [AGENTS.md](AGENTS.md)를 따른다.
