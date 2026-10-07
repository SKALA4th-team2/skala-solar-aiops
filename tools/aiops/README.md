# 백엔드 초기화와 검증

모든 명령은 `project/`에서 `.venv/Scripts/python.exe -X utf8`로 실행한다. 운영 안내는 [backend-runbook](../../docs/backend-runbook.md), 정책은 [0013](../../docs/decisions/0013-backend-aiops-implementation.md)이다.

| 스크립트 | 용도 |
| --- | --- |
| bootstrap.py | 기존 forecast_models 평가 모델과 실제 관측 자료에서 등록부·PI 기준선을 만들고 최초 게이트 통과 LSTM만 MLflow/운영 저장소에 등록 |
| portfolio_quality.py | 동일한 2025년 날짜에 예측 합계와 실제 합계로 품질 계산 |
| export_seed.py | 승인된 모델/스케일러/manifest를 다른 실행 환경으로 옮길 seed 생성 |
| replay.py | 실제 과거 41일 자료를 CSV, batch/predict 요청 JSON으로 생성 |
| test_policy.py | 판정 경계와 작업 중복 방지 검사 |
| verify_serving.py | 43개 API 응답, 원래 예측과 일치, MLflow 버전, 포트폴리오 완전/부분 합계 검사 |
| verify_lifecycle.py | 별도 runtime에서 실제 LSTM 재학습과 승격·거절·캐시·롤백·자동 감시 검사 |
| verify_recovery.py | 별도 runtime에서 중단 작업 복구, 프로세스 간 잠금, 사후 합계의 설비 이상 제외 검사 |

테스트 의존성은 `python -X utf8 -m pip install -r ../tools/verify/requirements-fastapi.txt`로 설치한다. 운영 의존성은 project/requirements.txt다. 모델·DB·로그는 Git에 넣지 않는다. verify_lifecycle의 합성 자료는 제어 흐름 검사용이며 예측 품질 근거로 쓰지 않는다.
