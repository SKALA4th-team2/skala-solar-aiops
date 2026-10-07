# 프론트·백엔드 연동 인계

2026-10-07 기준. 아래 담당 구분은 제안이며, API 스키마의 최종 기준은 [기존 API 명세](../../proposal/5-api-spec.md)와 FastAPI OpenAPI다.

## 지금 사용할 수 있는 것

- 프론트 원본은 이 폴더의 index.html, styles.css, app.js, dashboard-core.js, operations.js, server-dashboard.js다. solar-ops-preview.html은 생성 파일이므로 직접 수정하지 않는다.
- 운영 요청은 /preview-api/* → tools/design의 고정 프록시 → FastAPI로 전달한다. 개발할 때 백엔드 주소를 SOLAR_API_BASE_URL로 지정하면 CORS 설정을 따로 바꾸지 않아도 된다.
- 기존 Node 테스트 15개와 모의 API를 이용한 브라우저 검증을 통과했다. 실제 서버의 추론·재학습·승격 성공을 검증한 상태는 아니다.
- 발전 차트/내일 전망은 빌드 시 포함된 과거 자료와 규칙 기준선이다. CSV 업로드나 모델 학습으로 자동 갱신되지 않는다.

## 권장 담당 분리

세 서버를 각각 만들 필요는 없다. FastAPI 앱 하나에 담당 라우터와 서비스 모듈을 나누면 프론트는 주소 하나만 연결한다.

| 담당 | 권장 책임 | 프론트가 호출할 API | 현재 저장소 상태 |
| --- | --- | --- | --- |
| FastAPI | 입력 검증, 업로드/조회, 예측 요청 중계, 오류 응답, 시스템/데이터셋 정보 | /health, /data/upload, /data/status, /predict, /system/info, /system/dataset | 앞의 4개 경로 존재. 시스템 경로 추가 필요. 예측 구현 빈칸 확인 필요 |
| AIOps | 요청 지표 수집, 드리프트 판단, 실행 이벤트/알림, 로그 | /predict/batch-test, /metrics/summary, /system/timeseries, /system/alerts, /logs, /logs/{filename} | 배치/로그 경로 존재. 지표/알림 경로 추가 필요. 배치 구현 빈칸 확인 필요 |
| MLOps | 모델 로딩, 학습·검증, Registry 등록, 승격, 모델 이력 | /models/current, /models/history 및 내부 학습/로딩 서비스 | 모델 조회 경로 추가 필요. 기존 학습/로딩 구현 확인 필요 |

배치 라우터는 AIOps 담당이 소유하고 MLOps 학습 서비스를 호출하도록 합의한다. 같은 파일을 세 사람이 함께 수정하지 않는다. 이 구분은 역할 제안이지 현재 구현 완료 보고가 아니다.

## 구현 전에 합의할 5가지

1. 태양광 입력: close=하루 발전량(kWh), volume=다음 날 일사량 예보(MJ/m²), 최근 20일. 현재 API와 프론트 검증은 volume을 정수로 제한한다. 예보 소수를 받으려면 schemas.py와 프론트/프록시 검증을 같은 변경에서 고친다. 0 발전량 허용과 날짜 정렬/누락 검증도 합의한다.
2. 시뮬레이션: 현재 UI는 저장된 HAIC 화면의 합성 주가 배치(기준 165, 거래량 규모)를 재현한다. 태양광 출력 저하 시나리오로 사용하기 전에 배치 입력과 서버 SIMULATED_VOLUME을 함께 바꾼다. 기준값만 태양광 숫자로 바꾸면 안 된다.
3. 실행 계약: 배치 응답은 predictions 21개와 drift_check.status/promoted/rmse를 사용한다. 현재 동기 호출 제한은 서버 프록시 120초다. 더 오래 걸리는 재학습은 실행 ID/상태 조회 방식으로 API와 UI를 함께 변경한다.
4. 공통 타입: 단위, Unix timestamp의 초/밀리초, 모델 버전 식별자, 빈 데이터/오류 응답을 OpenAPI에 고정한다. 특히 created_at/ts는 현재 프론트가 초 단위로 읽는다.
5. 발전 화면: 실적·예보·실제 모델 예측을 공급할 조회 API를 추가 합의한다. 현재 과거 재생 그래프를 실시간 모델 결과로 표시하지 않는다.

## 현재 프론트 어댑터

| 파일 | 수정 책임 |
| --- | --- |
| app.js | 발전 차트/화면 전환, 상태 조회, CSV 업로드 |
| operations.js | 정상·드리프트 배치, 실행 결과/파이프라인, 로그 |
| server-dashboard.js | 단건 예측, 지표/설정 조회, 모델/알림 이력 |
| tools/design/serve-preview.mjs | 개발 서버, 상태/CSV 프록시 |
| tools/design/operation-routes.mjs | 배치/로그 고정 프록시 |
| tools/design/dashboard-routes.mjs | 저장본에서 확인한 추가 API 고정 프록시 |

프록시는 개발용이다. 배포 시에는 같은 출처에서 FastAPI 정적 파일을 제공하거나 별도 웹 프록시를 사용하도록 정하고, /preview-api 경로를 계속 쓸지 함께 정한다. 개발 서버를 운영 배포 서버로 간주하지 않는다.

## 연결 순서와 완료 기준

1. OpenAPI 요청/응답 확정 → 프론트 모의 응답과 같은 형태인지 확인.
2. 헬스/업로드/등록 정보 → 업로드 후 서버 행 수·기간 일치.
3. 단건 예측 → 20일 입력, 숫자 예측값, 실제 모델 버전 반환.
4. 정상/드리프트 → 정상 판정과 재학습/승격·미승격 각각 확인.
5. 이력/알림/지표 → 실제 실행 결과와 화면 일치, 빈 데이터와 오류 상태 확인.
6. 발전 차트 실제 API 연결 → 대상 날짜/단위와 모델 결과 일치.

명령은 저장소 project/에서 실행한다.

```sh
SOLAR_API_BASE_URL=http://127.0.0.1:8077 node ../tools/design/serve-preview.mjs
node --test ../tools/design/chart-data.test.mjs ../tools/design/dashboard.test.mjs
node ../tools/design/generate-chart-data.mjs --check
node ../tools/design/build-preview.mjs
```

외부 원본 HTML, .env, 업로드 데이터, 학습 모델, 로그는 이번 프론트 커밋에 포함하지 않는다.
