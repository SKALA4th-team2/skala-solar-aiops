# 제출 검증 증빙

- local/: 실제 로컬 HTTP 예측, 422, 합성 드리프트, 재학습, 버전 전환, 롤백, 재시작 영속성.
- local/latency.json: 개선 전 순차 30회 p95 1.325초.
- local/latency-optimized.json: 추론 그래프 재사용 후 순차 30회 p95 0.557초. SQLite 저장을 포함하며 동시 부하 SLO는 아니다.
- local/graph-parity.json: 31개 모델의 eager/graph 출력 동등성 검증.
- local/bundle-install.json: 깨끗한 폴더 설치와 변조 ZIP 거절.
- docker-initial/: Linux 원본 재학습 및 Docker HTTP 검증. 33개 평가, 31개 승인.
- frontend-*.png: 합성 기능 검증임을 표시한 실제 프론트 화면.

합성 저하 자료는 기능 검증 전용이다. 예측 성능은 2025년 독립 평가 자료를 사용한다.

아키텍처는 Mermaid 11에서 실제 SVG 렌더링을 확인했다. [렌더링 화면](architecture.png), [검증 결과](local/mermaid.json), [최신 운영 화면](frontend-production.png), [운영 서버 검사](local/production-smoke.json).

최종 서빙 검증은 [docker-final/summary.json](docker-final/summary.json), [재시작](docker-final/restart-persistence.json), [전체 성공 CI](docker-final/ci-run.json)에 있다.
