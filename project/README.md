# 실행 디렉터리

현재 서비스는 31개소 **시간별 LSTM**이다. project/에서 `.venv\Scripts\python -X utf8 scripts/run_backend.py`로 API와 재학습 작업자를 함께 실행한다. http://127.0.0.1:8077/ 에 프론트가 연결된다.

설치, 시간별 JSON/CSV 계약, 모델 저장·재학습·롤백·다른 PC 이전은 [운영 안내](../docs/backend-runbook.md), 정책과 게이트는 [결정 0014](../docs/decisions/0014-hourly-forecast-and-aiops.md)를 따른다. `serving_app/hourly/`가 현재 구현이고 일별 스켈레톤 모듈은 과거 실습·검증용이다. 디렉터리 구조는 유지했다.
