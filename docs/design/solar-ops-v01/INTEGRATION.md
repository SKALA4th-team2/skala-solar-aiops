# 시간별 프론트 연결

현재 실행 스크립트는 hourly-ui.js다. index.html/styles.css 디자인을 유지하고 시간별 API에 연결했다. app.js,operations.js,server-dashboard.js,dashboard-core.js는 이전 일별 구현 이력이며 현재 HTML에서 로드하지 않는다.

project/에서 `node ../tools/design/publish-runtime.mjs`를 실행하면 독립 HTML을 빌드하고 FastAPI static에 반영한다. 직접 생성물만 고치지 않는다. 실제 화면은 http://127.0.0.1:8077/ 에서 API·작업자와 함께 실행한다. 독립 프록시는 `node ../tools/design/serve-preview.mjs`이며 SOLAR_API_BASE_URL에 백엔드 origin을 설정한다.

GET /plants→승인목록, /ui/energy→시간별차트·24시간예측표, /ui/sample→실제요청예시. POST /predict, /predict/batch-test, /data/upload로 실제작업을 수행한다. /preview-api/operations와 dashboard/*는 현재모델·작업·로그·이력을 조회한다. 자세한 계약은 [운영안내](../../backend-runbook.md).

24/72/168시간 조회. 차트 RMSE는 현재모델 과거재생, 운영모델의2025독립검증 RMSE는별도다. 화면날짜는자료의실제날짜이며 오늘의실시간예보라고표시하지않는다. API오류를 예시숫자로대체하지않는다.
