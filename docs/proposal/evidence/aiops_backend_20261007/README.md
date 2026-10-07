# 2026-10-07 백엔드 통합 검증

- `summary.json`: 최종 집계. 43개 등록, 33개 LSTM 서빙, 10개 보류.
- `held-plants.json`: 보류 개소와 실제 게이트 결과. 기존 모델 파일은 보존.
- `serving.json`: 43개 응답·MLflow Production 버전·원래 예측 일치·포트폴리오 누락 처리.
- `portfolio_quality.json`: 2025년 공통 날짜에서 실제 합계와 예측 합계의 오차.
- `lifecycle.json`: 별도 runtime에서 실제 LSTM 학습, 승격/실패, 중복 방지, 다른 개소 격리, 스케일러 보존, 캐시 전환, 롤백, 손상 파일 거절, 자동 업로드 감시.
- `recovery.json`: 중단 작업 복구, 재시도 상한, 프로세스 간 잠금, 합계 PI의 정지·보류 제외.
- `latest-upload.json`: 업로드에서 다음 날 예측까지 실제 모델 호출.
- `http.json`: localhost:8077의 실제 HTTP 예측과 일꾼 상태.

lifecycle과 recovery의 합성 자료는 제어 흐름 검증 전용이다. 실제 예측 품질은 원래 forecast_models_20261007의 2025년 평가와 포트폴리오 평가를 사용한다. 최초 게이트 또한 2025년 시험 결과로 결정했으므로 과거 재생은 당시 운영 결정을 재현한 검증이 아니다. Docker 미설치로 컨테이너 실행은 미검증이다.

실행 방법은 [백엔드 안내](../../../backend-runbook.md), 정책은 [0013](../../../decisions/0013-backend-aiops-implementation.md)에 있다. 모델·SQLite·대용량 로그는 Git에서 제외한다.


2026-10-08 후속 검증: Linux Docker에서 원본 재학습, 31개 승인 모델의 예측·자동 재학습·롤백·재시작 영속성을 확인했다. 실행 근거: https://github.com/SangMyeong5426/skala-solar-aiops/actions/runs/37643858606 . 위 Docker 미검증 표기는 10월 7일 당시의 기록이다.
