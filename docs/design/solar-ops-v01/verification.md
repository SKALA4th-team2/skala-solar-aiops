# 디자인 초안 변경·검증 기록

작성일: 2026-10-07. 작업 모드: 일반 개발 모드. 화면 구조·차트·필터·반응형과 독립 미리보기 도구가 함께 바뀌어 선택했다. 최신 디자인은 아래 「DESIGN.md 반영 재설계」를 따른다. 이전 중립색 시안에서 주황·하늘색 운전일지 형태로 갱신했다.

## 목적과 최종 변경

- 기업 운영자가 발전 현황 → 서비스 운영 → 이력·알림을 좌측 고정 메뉴로 전환한다. 세로 스크롤바를 숨기고 본문 스크롤 접근은 유지한다.
- 전체 발전소 합계/개별 발전소와 7/30/90일을 함께 선택한다. KPI·차트·표·CSV에 동일 범위를 적용한다. 실제 발전량 자료는 하동 1개소이며 두 선택의 수치가 같은 이유를 안내한다.
- 실적·예보는 CSV 실제 자료, 예측은 과거 7일 비율 기준선이다. 데이터 블록은 스크립트로 재생성한다.
- 운영 상태는 별도 조회 시각과 갱신 주기를 표시한다. 기본 30초, 10초/1분/끄기와 수동 갱신을 지원한다. 실제 서버 조회와 디자인 예시를 구분한다.
- 최신 사용자 지시에 따라 기능 확장보다 디자인·조작 흐름을 우선했다. 다중 발전소 자료나 운영 지표를 임의로 만들지 않았다.

## 변경 파일

`docs/design/solar-ops-v01/`:
- `index.html`: 사이드바, 업무 화면, 발전소 필터, 운영 상태 도구 모음.
- `styles.css`: 팔레트, 비대칭 수치 배치, 반응형, 차트 상호작용과 모션. 최종 운전일지 배치를 반영.
- `app.js`: 실제 자료 재생, 필터·내비게이션·차트·CSV와 읽기 전용 갱신.
- `dashboard-core.js`: 날짜 정렬된 발전소 자료 선택·합계·RMSE 계산.
- `README.md`, `verification.md`: 근거, 데이터 경계, 실행과 검증 기록.
- `solar-ops-preview.html`: 빌더로 생성한 단일 HTML.
- `desktop-preview.jpg`, `mobile-preview.jpg`, `service-preview.jpg`, `history-preview.jpg`: 브라우저 캡처.

`tools/design/`:
- `generate-chart-data.mjs`, `chart-data.test.mjs`: 재현 가능한 기준선 생성과 데이터 검증.
- `build-preview.mjs`: 순수 계산 모듈도 단일 HTML에 포함.
- `serve-preview.mjs`, `dashboard.test.mjs`: 루프백 전용 미리보기와 고정 GET 조회, 집계·응답 계약 검증.

`project/`, `datasets/`, 기존 `reference/`는 수정하지 않았다.

## 참고 문서와 코드

- 루트 `AGENTS.md`와 제공된 전역 v3.1.1: 프로젝트 우선, 원본 보존, 결과·예시 구분, 검증 보고. 디자인 하위 별도 규칙 없음.
- `README.md`, `CONTRIBUTING.md`, `datasets/README.md`: 실행 방식과 자료 의미.
- `docs/proposal/domain-mapping.md`, `docs/proposal/3-operations-design.md`, `docs/decisions/README.md`, `docs/followups.md`: 설계 및 미확정 항목 경계.
- `project/serving_app/routers/health.py`, `routers/data.py`, `routers/logs.py`, `main.py`, `static/index.html`: 실제 읽기 API와 레퍼런스 동작 확인. 수정 없음.
- skill-router와 frontend-ui-engineering: 스킬 선택, 기업용 정보 위계·반응형·상태 구분 적용.
- Chrome으로 팀 8099 레퍼런스와 최종 미리보기 확인. 외부 디자인 참고 링크 및 적용 범위는 README에 기록.

## 실행한 명령과 결과

아래 Node 명령은 저장소 `project/`에서 실행했다.

```sh
node --check ../docs/design/solar-ops-v01/app.js
node --check ../docs/design/solar-ops-v01/dashboard-core.js
node --check ../tools/design/serve-preview.mjs
node --test ../tools/design/chart-data.test.mjs ../tools/design/dashboard.test.mjs
node ../tools/design/generate-chart-data.mjs
node ../tools/design/generate-chart-data.mjs --check
node ../tools/design/build-preview.mjs
```

- 문법 검사, 생성 확인, 빌드 성공. 테스트 **12개 통과**, 실패·skip 없음.
- 생성 스크립트 재실행 전후 `app.js` 바이트 동일 확인.
- RMSE 7/30/90일 29.8/43.6/46.2 kWh/일. 내일 예보 27.7 MJ/m²·예측 277.7 kWh. 06-04 실측 314.1·당일 예측 276.9 kWh, 최근 7일 평균 236.6 kWh/일 확인.
- 원본 CSV SHA-256 `8bd25f17c48befff4b17844109f7412c2e97af3b73cd01450349dcfce2855d64` 유지.
- 태양광 SVG는 색상을 제외한 도형·경로·viewBox가 이전 원본과 동일. 고정 높이와 잘림을 추가하지 않음.
- `git status --short`, `git branch --show-current`, `git diff --check`, `git diff --stat`, `git diff` 확인. 브랜치 main. 디자인과 도구는 미추적 경로이므로 Git diff에 표시되지 않아 파일 내용과 이전 디자인 스냅샷을 별도 검토했다. 커밋 없음.
- 루프백 서버는 샌드박스의 listen 제한으로 일반 실행이 실패해 승인된 확장 실행으로 시작했다. `SOLAR_API_BASE_URL`을 세션 환경변수로 지정했으며 비공개 주소는 소스에 넣지 않았다.

## 브라우저 확인

- 1440px 데스크톱, 390px 모바일에서 좌측 메뉴와 선택 화면 전환, `aria-current`, 발전소·기간 필터 확인.
- 320/768/1024/1440px에서 문서·본문 가로 넘침 없음. 차트 축 글자 12px 유지.
- 30일 표 30행·RMSE 43.6, 90일 표 90행·RMSE 46.2, 7일 복귀 확인.
- 날짜 칸 툴팁, 우측 날짜의 왼쪽 뒤집힘, Tab으로 다음 점 이동 시 동일 툴팁 표시 확인. 모바일 툴팁 폭 184px, 화면 안쪽 배치 확인.
- `?motion=off`에서 차트 덮개 scaleX(0), 차트 노출 유지. 진입 animation의 backwards·단일 실행과 기간 변경 시 wipe 재생은 앞선 동일 구현 검증에서 확인.
- 세로 바는 body overflow hidden, 본문 scrollbar-width none. 긴 모바일 내용은 내부 스크롤로 접근한다.
- 실제 서버 `/health` 조회 정상, 당시 모델은 미로딩. `/data/status`는 조회 실패하여 부분 실패 상태 표시. 10초 자동 갱신 후 마지막 조회 시간이 바뀌는 것 확인. 조회 응답시간은 예측 API 지연이 아니다.
- 최종 색상 되돌림 후 예측 카드 배경 `rgb(255,255,255)`, 주요 버튼 `rgb(41,41,41)` 확인하고 desktop/mobile 캡처를 갱신했다.
- 최종 확인 시 브라우저 console error/warn 없음.

## 미검증·남은 범위

- **미검증:** OS의 실제 prefers-reduced-motion 설정을 바꾼 런타임 검증. CSS 대응은 확인했고 URL 모션 끄기는 실검증했다.
- **미검증:** 복수 발전소 실데이터. 날짜 일치·합산·RMSE는 테스트 전용 가상 입력으로만 검증했다. 실제 자료 추가가 필요하다.
- **미검증:** 서버 전체 예측 요청 수·성공률·평균 추론시간·실제 모델 이력 자동 반영. 현재 읽기 API가 제공하지 않으므로 수치와 완료 상태를 만들지 않았다.
- 데이터 현황 API는 연결 서버에서 실패했다. 원인 진단·백엔드 변경은 최신 디자인 우선 범위 밖이다.
- API 실패와 부분 응답은 단위 검증 및 실제 부분 실패로 확인했다. 모든 네트워크 장애 조합을 브라우저에서 강제로 재현하지 않았다.
- 백엔드 Python 테스트·서비스 배포는 실행하지 않았다. 서비스 코드를 변경하지 않는 독립 디자인 작업이며 운영 배포를 완료했다는 의미가 아니다.
- 후속 작업: 실제 다중 발전소 자료와 필요한 운영 API가 제공되면 현재 필터·갱신 UI에 연결한다. 이번 작업에서 규칙 예외로 원본·보호 영역을 수정하지 않았다.


## DESIGN.md 반영 재설계 — 2026-10-07

- 작업 모드: 일반 개발 모드. 화면 배치·색상·반응형과 설계 문서를 함께 갱신했다.
- 사용자 제공 대시보드 이미지 5장과 Google Labs DESIGN.md의 PHILOSOPHY.md·docs/spec.md를 확인했다. Figma CDN 이미지 1장은 403으로 확인하지 못했다.
- DESIGN.md에 발전소 운전일지·기상 관측표라는 시각적 기준, 색상 역할, 숫자 크기, 화면별 배치와 피할 패턴을 명시했다.
- 확정 발전량은 큰 숫자로, 평균·오차는 보조값으로 나눴다. 아래에 추이, 오른쪽에 옅은 주황의 전망 영역을 배치했다. 동일한 KPI 카드 반복·그림자·그라데이션을 제거했다.
- 실측 하늘색 실선과 예측 주황 점선, 툴팁 색을 일치시켰다. 서비스·이력 화면도 같은 구분선·글자 체계로 갱신했다.
- 단일 HTML은 `node ../tools/design/build-preview.mjs`로 재생성했다. 원본 app.js·dashboard-core.js와 자료 계산은 수정하지 않았다.
- 기존 Node 테스트 12개 통과, generate-chart-data.mjs --check 통과. 1440·1024·768·390·320px에서 세 화면 전환, 기간 7/30/90일, 발전소 선택, CSV 다운로드, 일별 표와 가로 넘침을 확인했다. JavaScript 실행 오류 없음.
- 이번 미리보기는 운영 API를 연결하지 않은 localhost:8770에서 확인했다. 운영 서버 실시간 연결·학습·배포는 이번 디자인 검증 범위가 아니다.
- README·DESIGN.md·원본 CSS/HTML·생성 HTML·4개 미리보기 이미지를 갱신했다. 기존 스테이징 상태를 보존했으며 커밋·푸시하지 않았다.

- DESIGN.md는 설치된 PyYAML로 파싱하고 모든 토큰 참조가 정의된 값으로 연결되는지 확인했다. 공식 CLI lint는 실행하지 않았다.


## 가독성·업로드·전망 정렬 수정 (2026-10-07)

- 본문/버튼 16px, 보조 설명 14px, 표지 13px로 확대. 기존 검증 기록의 다운로드 기능은 CSV 업로드로 교체했다.
- 업로드 대화상자에서 파일을 선택하고 고정 프록시를 통해 기존 /data/upload API에 전송한다. 서버 미연결, 형식 거부, 연결 오류, 시간 초과, 성공 상태를 표시한다.
- 전망 패널의 stretch 및 그림의 auto 여백을 제거했다. 1440/1024px에서 일별 기록 확장 전후 그림 y 위치가 동일했다.
- node --test ../tools/design/chart-data.test.mjs ../tools/design/dashboard.test.mjs: 13개 통과. 업로드 테스트는 임시 로컬 서버로 multipart 전달, 오류 처리 및 외부 origin 차단을 검증했다.
- node --check (app.js 및 serve-preview.mjs), generate-chart-data.mjs --check, build-preview.mjs, git diff --check 완료.
- 분리 Chrome에서 1440/1024/768/390/320px 가로 넘침 없음, JS 오류 없음. 대화상자 미연결 안내 및 모의 성공 확인.
- 미검증: 실제 운영 API의 파일 저장. 검증 과정에서 운영 데이터는 업로드하지 않았다.


## 중요도와 작은 글씨 보완 (2026-10-07)

- 경량 수정 모드: styles.css의 글자 크기·굵기·줄바꿈을 조정하고 build-preview.mjs로 독립 HTML을 재생성했다.
- 기존 반응형 규칙에 남은 9~14px 선언을 최소 15px로 올렸다. 주요 설명 16px, 지표 제목 18px/700, 섹션 제목 24px/750, 핵심 수치 750을 적용했다.
- 분리 Chrome에서 발전/서비스/이력 3화면 × 320/390/768/1024/1440px를 확인했다. 표시된 텍스트의 계산된 글자 크기는 모두 15px 이상, 문서/본문 가로 넘침과 JS 오류는 없었다.
- 1024/1440px 일별 기록 확장 전후 태양광 그림 위치 동일. 최신 데스크톱·모바일·서비스·이력 캡처 교체.
- node --test ../tools/design/chart-data.test.mjs ../tools/design/dashboard.test.mjs: 13개 통과. build-preview.mjs 및 git diff --check 완료.
- 참고: 기존 index.html/styles.css, DESIGN.md, 저장소 AGENTS.md, frontend-ui-engineering 스킬. 실제 운영 API 저장은 이번 스타일 수정의 검증 대상이 아니다.


## 화면 높이 대응 (2026-10-07)

- 경량 수정 모드: 글자 크기·굵기·색상은 유지하고 데스크톱 여백과 차트·삽화 높이에 반응형 규칙을 추가했다. 숨긴 스크롤바를 다시 표시하고 패널 제목/전망 날씨의 줄바꿈을 허용했다.
- 1440×900 기본 접힘 상태: 본문 높이 842px에 발전/서비스/이력 모두 들어옴. 발전 콘텐츠 1095→842px, 서비스 1056→842px. 실제 API 미연결 상태 기준이다.
- 1440×768 발전 1095→796px, 서비스 1056→820px. 낮은 화면·모바일 및 펼친 기록은 세로 스크롤을 유지한다.
- 320/390/768/1024/1440px × 3화면에서 최소 글씨 15px, 문서/본문 가로 넘침 없음, JS 오류 없음. 1024/1440px 기록 확장 전후 전망 그림 위치 동일.
- build-preview.mjs 재생성, 분리 Chrome에서 6개 화면 크기 높이 측정 및 데스크톱 캡처 육안 검토. git diff --check 완료. 이번 변경은 CSS와 생성 HTML/문서/캡처에 한정되며 운영 API 저장은 검증 대상이 아니다.


## 서비스 기능 비교 및 통합 (2026-10-07)

- 일반 개발 모드: 두 저장 HTML의 호출 경로와 조작 기능을 비교해 UI/프록시/검증을 추가했다. 사용자가 지정한 내부 서버 직접 접속은 연결 시간 초과였다. HTML은 참고 자료로만 읽었으며 내장 스크립트는 실행하지 않았다.
- 이동/정리: CSV는 서비스 운영에만 표시. 시뮬레이션 버튼 추가. 좌하단 미리보기/설명, 우상단 재생 배지와 긴 예시 안내 제거. 항목별 짧은 예시 표기는 유지. 실제 사용/출처 지침이 확인된 Open-Meteo 링크 유지.
- 추가: 정상/드리프트 배치, RMSE/응답, 파이프라인 상태, 로그 목록/본문, 단건 예측/JSON 예시 생성, 기간별 요청 지표, 성능 요약, 데이터셋, 시스템 설정, 현재 모델, 서버 모델 이력/알림 조회. 자동 갱신은 기존 주기 선택(5초 추가)을 사용한다.
- node --test ../tools/design/chart-data.test.mjs ../tools/design/dashboard.test.mjs: 15개 통과. 신규 프록시 경로, 입력 거부, 외부 origin 거부, 업로드·배치·단건 예측·로그 전달은 로컬 모의 서버로 검증했다.
- 분리 Chrome에서 3화면×5폭(320/390/768/1024/1440) 가로 넘침 없음, JS 오류 없음. 예시 항목 35개를 추가해 모델/알림 각 패널의 독립 세로 스크롤 확인. 미연결 안내, 정상/드리프트 모의 응답, 편집 JSON 오류, 단건 예측, 요청 가중 평균(18ms)/성공률(80%), 서버 이력 교체와 HTML 문자열의 안전한 텍스트 표시를 검증했다.
- 미검증: 실제 내부 서버 API 가용성, 실데이터 업로드 저장, 모델 추론·재학습·승격. 서버 코드의 빈칸이나 미제공 경로를 UI에서 구현 완료로 주장하지 않는다. 저장본의 주식 데이터 계약은 태양광 API 계약으로 자동 변경하지 않았다.
- 변경 파일: index.html/styles.css/app.js, operations.js/server-dashboard.js, serve-preview.mjs/operation-routes.mjs/dashboard-routes.mjs/build-preview.mjs/dashboard.test.mjs 및 생성 HTML/캡처/문서.


## PR 자체 리뷰 (2026-10-07)

- P2 수정: history/alerts가 null 항목을 반환하면 DOM 렌더링이 멈추고 새로고침 버튼이 잠기는 문제. 항목 검증과 finally 복구, 실패 상태 표시 추가. 브라우저에서 [null] → 정상 응답 재시도 성공.
- P2 수정: null 예측/배치 본문이 502로 분류되던 문제. 입력 검증 단계에서 400으로 반환. 단건 예측 회귀 assertion 추가.
- P2 수정: error_rate 범위를 검증하지 않아 잘못된 성공률이 나오는 문제. 0~1 범위 및 요청 수/응답시간 검증. 브라우저에서 error_rate=2 응답 거부 확인.
- Node 테스트 15개 통과, 브라우저 예외 없음. 모바일 캡처를 최신 버튼 배치로 갱신.
- 남은 범위: 실제 API 통합, 태양광 입력/배치 계약, 장기 재학습 실행 상태 API, 발전량 조회 API. CSS의 누적 규칙 정리는 후속 리팩터링 권장. 이번 PR은 프론트 시제품/개발 어댑터이며 운영 출시 승인이 아니다.
