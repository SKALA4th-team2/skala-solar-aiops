# 프론트엔드 레퍼런스 조사와 Solar Ops 적용 판단

작성일: 2026-10-08 · 작업 모드: 일반 개발 모드

## 조사 범위와 판단 기준

`ai-event-bridge`의 Vue 프론트엔드와 `ai-knowledge/frontend`, `skala-cbam-ct/frontend`의 토큰·CSS·컴포넌트·모션·출처 주석을 읽었다. 원본 프로젝트는 수정하지 않았다. 아래 경로는 각 저장소 루트 기준이다. 두 참고 프로젝트의 실제 브라우저 실행은 미검증이며, 코드 구현과 외부 사이트에서 확인한 사실을 구분한다.

Solar Ops의 기존 비대칭 배치, 주황/하늘색, 최소 15px 글자, 굵은 핵심 수치, 일별 기록과 전망의 독립 배치, 실제 API 상태를 유지한다. 새 기능이나 새 라이브러리 도입보다 현재 업무 흐름의 구분과 피드백을 개선한다.

## 1. ai-event-bridge

활성 스타일 진입점: `vue-frontend/src/main.js:5`. 아래 CSS 경로는 `vue-frontend/src/assets/styles/` 기준.

| 디자인 요소 | 코드 근거 | 판단과 이유 |
|---|---|---|
| 의미별 색상·표면·글꼴 토큰 | `tokens.css:7` | 구조 채택. Solar 색상 유지 |
| 사계절 팔레트와 배경 | `tokens.css:19` | 제외. 추가 색상과 테마 전환 불필요 |
| 굵은 수치와 단위 계층·고정 숫자 폭 | `app.css:392–400` | 채택. 수치 변경 때 정렬 유지 |
| 비대칭 그리드와 행동 목록 | `app.css:401–427` | 원칙 채택. 기존 Solar 그리드는 유지 |
| 알림·모달 내부 독립 스크롤 | `app.css:482,1100` | 기존 구현 유지 및 회귀 확인 |
| hover/focus/disabled | `app.css:30–40`, `base.css:14` | 채택. 이동 없이 색상·테두리로 피드백 |
| 100/160/240/420ms 모션 토큰 | `app.css:860–866` | 100/160ms 상호작용만 채택 |
| 클릭 축소·카드 확대 | `app.css:869–873` | 제외. 클릭 위치와 주변 배치 안정 우선 |
| 숫자 상승·순차 등장·저장 바운스 | `app.css:875–889` | 제외. 갱신 화면의 읽기 방해 |
| 반복 shimmer 로딩 | `app.css:891–903` | 제외. 기존 실제 대기/실행 상태 사용 |
| 업로드 hover·선택·오류 상태 | `app.css:906–929` | 원칙만 참고. 미구현 드래그 동작은 추가하지 않음 |
| 모션 감소 설정 | `base.css:15`, `app.css:960` | 채택. 애니메이션 제거 후 최종 화면 보장 |
| 포커스 가두기·복원 | `composables/useFocusTrap.js:20` | Solar native dialog 유지. 감시자 복사 없음 |
| 13px 하한·작은 배지 | `base.css:6`, `app.css:18` | 제외. 최소 15px 유지 |
| 전역 overflow:hidden | `base.css:4`, `app.css:14` | 제외. 화면 잘림 위험 |
| 지식 카드 5열·가로 파이프라인 | `ai-knowledge/frontend/src/components/knowledge/knowledge.css:2` | 그대로 이식하지 않음. 정보 밀도 과다 |
| 실제·예측 선 구분과 전망 구역 | `ai-knowledge/frontend/src/forecast-charts.css:6,30–38,49–58` | 기존 실선/점선 유지. 색만으로 의미 구분하지 않음 |
| 차트 최소 너비 900px·11~12px 라벨 | 같은 파일 `:22,48` | 제외. 모바일 잘림·작은 글씨 |
| 데모 성공 toast | `vue-frontend/src/views/console/DashboardView.vue:52,69` | 제외. 서버 성공을 대신할 수 없음 |

## 2. skala-cbam-ct

아래 경로는 `frontend/src/` 기준.

| 디자인 요소 | 코드 근거 | 판단과 이유 |
|---|---|---|
| 표면·텍스트·상태 토큰, 8/10/12px 반경 | `styles/tokens.css:1–24` | 구조 참고. 다색·검정 테마 제외 |
| IBM Plex Sans KR/Mono | `../index.html:8–10`, `styles/base.css:8` | 새 폰트 의존성 추가 안 함. 기존 한국어 폰트 유지 |
| 숫자 고정 폭 | `styles/base.css:688–689`, `components/CountUp.vue:19` | 채택 |
| 얇은 구분선 기반 지표 구획 | `styles/base.css:93–112` | 채택. 카드가 늘어나는 것 방지 |
| 조치 우선 요약과 행동 그룹 | `views/DashboardView.vue:60–73,130–153` | 원칙 채택. 긴 문장 대신 현재 짧은 제목 사용 |
| 검색·필터·결과 수 도구막대 | `components/DataToolbar.vue:19–59` | 기존 조회 컨트롤만 정렬. 신규 검색은 범위 밖 |
| 텍스트와 색을 함께 쓰는 상태 | `components/StatusChip.vue:1–5` | 기존 상태 문구 유지 |
| 동일 크기의 로딩 행·aria-busy | `components/SkeletonRows.vue:2–9`, `styles/base.css:811–815` | 향후 목록 로딩 때 참고. 이번에는 추가하지 않음 |
| 150ms hover와 focus 밑줄 | `styles/base.css:41,111–112,718–725` | 160ms 색 피드백, 출처 링크 상시 밑줄로 적용 |
| reduced motion 최종 상태 | `styles/base.css:728–736` | 채택. 차트 가림막도 최종 상태 유지 |
| 모달 Esc·포커스 복귀 | `components/ModalBox.vue:16,21–29`, `composables/focusTrap.js:11–37` | 기존 native dialog 유지 |
| FLIP 목록 재정렬 | `composables/useFlip.js:18–49` | 제외. 운영 목록 읽던 위치 보존 |
| 380~1100ms 숫자 count-up | `composables/motion.js:19–30` | 제외. Math.round가 소수 발전량 정확도를 깨뜨림 |
| 화면·어절 순차 등장 | `styles/base.css:52,683–695` | 제외. 핵심 정보 노출 지연 |
| 무한 경보 맥동 | `styles/base.css:697–703` | 제외. 시각 피로 |
| 5200점 회전 지구본 | `composables/globe.js:1–76` | 제외. 업무 연관성·상시 연산·라이선스 문제 |
| 라벨 없는 입력·클릭 i/label | `components/DataToolbar.vue:22,31–34,56` | 복사 금지. native controls와 접근 가능한 이름 유지 |
| live region 없는 toast | `components/ToastHost.vue:17` | 복사 금지. Solar 기존 role=status 유지 |

## 3. 레퍼런스 사이트와 출처의 확실성

| 출처 | 확인된 사실 | 사용 범위 |
|---|---|---|
| [OriginKit globe mesh](https://www.originkit.dev/components/globe-mesh?preset=base) | CBAM `composables/globe.js:1–4`에 직접 URL. 소스에 라이선스 미확인 명시. 이번 웹 열기 도구에서도 페이지 접근 실패 | 링크만 기록. 코드·이미지 복사 안 함 |
| bklit shimmering-text | CBAM `styles/base.css:708`에 이름만 있음 | 정확한 URL/라이선스 미확인, 효과 제외 |
| GSAP Flip | CBAM `composables/useFlip.js:6`에 이름만 있음 | 설치 의존성이 아닌 구현 참고 주석. 코드 이식 안 함 |
| DrawSVG | CBAM `styles/base.css:114` 주석 | 정확한 URL 미확인, 직접 출처로 주장하지 않음 |
| Figma 01 Foundation / 04 UI 프레임 | CBAM `styles/tokens.css:1`, `router/index.js:3` | 실제 Figma 링크 없음 |
| Google Fonts | CBAM `frontend/index.html:8–10`에서 실제 폰트 로드 | Solar에 추가 다운로드 없음 |
| home-v2.html | bridge `app.css:2`에서 원본 언급 | 해당 파일은 checkout에서 발견하지 못함 |
| 2026 motion guide | bridge `app.css:854`의 익명 주석 | 검증된 외부 가이드로 취급하지 않음 |
| Wikimedia 축제 사진 13개 | bridge `vue-frontend/public/festivals/CREDITS.md:10`, `src/constants/photoCredits.js:7`에 출처·라이선스 | 자산 출처로만 분류. 태양광 화면과 무관하여 제외 |

Dribbble·CodePen·Awwwards 등의 확인된 레퍼런스 모음은 조사 범위에서 발견하지 못했다. 추정 URL을 실제 참고 사이트처럼 추가하지 않았다.

## 4. 페르소나 교차 검토

두 독립 검토자가 각각 시각 디자인+유지보수, 운영 담당자+접근성 관점으로 조사했다. 이후 서로의 채택안을 포함한 공통 적용안을 검토하고 실제 변경 파일을 재검토했다. 두 검토자 모두 차단 문제 없음으로 승인했다. 정적 리뷰와 브라우저 검증은 구분한다. 아래는 역할별 통과 조건이다.

| 페르소나 | 핵심 질문 | 합의된 적용 |
|---|---|---|
| 발전소 운영 담당자 | 상태·수치·다음 행동을 바로 읽는가? | 숫자 즉시 표시, 조회 도구 그룹화, 목록 위치 유지 |
| 시각 디자이너 | 기존 정체성을 유지하면서 중요도가 드러나는가? | 주황 행동 버튼, 하늘색 펼친 도구, 얇은 구분선 |
| 접근성 검토자 | 키보드·모션 감소·작은 화면에서도 읽히는가? | 3px focus, 15px 이상, native details/dialog, 색+문구 |
| 프론트 유지보수 담당자 | API·빌드·기존 배치를 깨뜨리는가? | 별도 refinements.css, 빌더 포함, 새 의존성/JS 동작 변경 없음 |

**통과:** 숫자 정렬, 의미별 토큰, 얇은 구획, 짧은 색상 피드백, 펼침 상태, 키보드 포커스, 모션 감소.
**보류:** skeleton과 복잡한 필터 — 실제 필요가 생길 때 구현.
**제외:** 계절 팔레트·작은 글씨·반복/순차 등장·카운트업·지구본·가짜 성공 표시.

## 5. 적용 파일과 확인

- `refinements.css`: 숫자 폭 고정, 이동 없는 버튼 피드백, 입력 포커스, 조회 도구의 접힘/펼침 구분, 기존 입장·차트 가림 애니메이션 제거.
- `index.html`: 개선 CSS를 마지막에 한 번 로드.
- `tools/design/build-preview.mjs`: 단일 HTML에도 동일 CSS 포함.
- `tools/design/serve-preview.mjs`: 원본 페이지용 CSS 허용 목록 등록.
- `solar-ops-preview.html`: 빌더로 재생성. 직접 수정하지 않음.

검증: Node 기존 15개 테스트 통과, 차트 데이터 재생성 검사 통과. 분리된 Chrome에서 320/390/768/1024/1440px × 발전/서비스/이력 15개 조합의 최소 글자15px, 문서·main 가로 넘침 없음, JS 오류 없음 확인. 데스크톱에서 일별 기록 펼침 전후 태양광 그림 위치 유지 확인.

이번 작업은 프론트 디자인 변경이다. 실제 태양광 예측·재학습·승격 성공을 검증한 것은 아니다. 작은 화면과 펼친 상세 내용은 세로 스크롤을 유지한다. 내용을 숨기거나 글자를 줄여 한 화면에 억지로 맞추지 않는다.

추가 브라우저 검증: 키보드 Enter로 native details 펼침, textarea 3px focus, 업로드 dialog Escape 닫기와 호출 버튼 포커스 복귀, reduced-motion 차트·수치 최종 표시, 생성 HTML CSS 포함 확인. 로컬 연결 상태는 “연결됨 · 서버 조회 값”으로 표시됐다. 배치·재학습 등 변경 요청은 실행하지 않았다.
