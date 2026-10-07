> **현행: 시간별31개소 UI.** 실행코드는 hourly-ui.js이며 [현재 연결](INTEGRATION.md), [새 검증 증빙](../../proposal/evidence/hourly_20261007/README.md)을 따른다. 아래는 이전 일별 디자인/시험 이력이다.

# SOLAR OPS — 태양광 운영 대시보드 초안

갱신일: 2026-10-07. 작업 모드: 일반 개발 모드(독립 HTML/CSS/JavaScript 시제품).

태양광 운영 담당자가 확정 발전량, 다음 날 전망과 예측 품질을 확인하고 서비스 운영 상태를 좌측 메뉴로 전환해 살펴보는 초안이다. `SOLAR OPS`, `SKALA 에너지`는 제안 명칭이다.

## 열기와 재생성

- [solar-ops-preview.html](solar-ops-preview.html): CSS·JavaScript를 포함한 단일 파일. 브라우저에서 직접 열 수 있다.
- [index.html](index.html): 수정 원본. 같은 폴더의 `styles.css`, `dashboard-core.js`, `app.js`, `operations.js`, `server-dashboard.js`가 필요하다.
- [데스크톱 캡처](desktop-preview.jpg), [모바일 캡처](mobile-preview.jpg).
- 운영 지표 연결 미리보기: <http://127.0.0.1:8767/solar-ops-preview.html>. 정적 미리보기(8766)는 운영 API 미연결 상태를 표시한다.

저장소의 `project/`에서 실행한다.

```sh
python3 -m http.server 8766 --bind 127.0.0.1 --directory ../docs/design/solar-ops-v01
```

데이터와 단일 HTML을 다시 만들 때:

```sh
node ../tools/design/generate-chart-data.mjs
node ../tools/design/generate-chart-data.mjs --check
node --test ../tools/design/chart-data.test.mjs
node ../tools/design/build-preview.mjs
```

운영 상태 조회를 연결하려면 환경변수에 지정한 서버의 origin을 넣고 다음 서버를 실행한다. 비공개 서버 주소는 소스에 저장하지 않는다.

```sh
SOLAR_API_BASE_URL="$SOLAR_API_ORIGIN" node ../tools/design/serve-preview.mjs
node --test ../tools/design/chart-data.test.mjs ../tools/design/dashboard.test.mjs
```

`SOLAR_API_ORIGIN`은 사용자가 지정한 API의 `http(s)://host:port`다. 8767 포트의 루프백 전용 서버는 `/health`, `/data/status`를 GET으로 조회하고, 사용자가 선택한 CSV는 `/data/upload`로 POST 전송한다. 타임아웃 5초, redirect 금지, 요청 URL로 목적지를 바꿀 수 없는 고정 프록시다. 기본 API 계약·CORS·운영 설정은 수정하지 않는다. 파일을 직접 열어도 차트는 동작하며 운영 상태는 미연결로 표시한다.

`?motion=off` 또는 `<html class="motion-off">`는 모든 animation·transition을 끈다. OS의 `prefers-reduced-motion`도 지원한다. 기간은 `?days=7|30|90`에 저장한다. 발전소는 `?plant=all|hadong`, 업무 화면은 `#energy`, `#service`, `#history`다. 뒤로 가기와 직접 링크를 지원하며 기존 `#forecast?days=30` 링크도 읽는다.

## 디자인 기준

[DESIGN.md](DESIGN.md)에 시각 언어와 배치 의도를 정의했다. Google Labs DESIGN.md의 철학과 형식을 참고해 확정 발전량 → 추이 → 다음 날 전망 순서로 읽는 발전소 운전일지 형태로 구성했다. 같은 크기의 KPI 카드 대신 큰 확정값 하나와 보조값 두 개, 넓은 그래프와 오른쪽 전망 영역을 사용한다.

- 좌측 고정 사이드바의 **발전 현황 / 서비스 운영 / 이력·알림** 3개 업무 화면으로 나눈다. 선택한 화면만 표시하며 모바일에서도 아이콘과 라벨이 있는 좁은 좌측 메뉴를 유지한다.
- 페이지와 본문의 세로 스크롤바는 표시하지 않는다. 작은 화면·펼친 표는 본문 영역의 휠·터치·키보드 스크롤로 접근 가능하다. 사이드바는 고정된다.
- 발전 현황: 발전소 선택 → KPI → 7/30/90일 차트·일별 표·내일 전망. 현재 실제 발전량 자료는 하동 1개소이므로 전체 합계와 개별 값이 같다는 안내를 제공한다. 적량면은 기상 관측소이므로 별도 발전소로 만들지 않는다.
- 합계는 같은 날짜의 발전량·예측을 더한 뒤 RMSE를 계산한다. 일사량은 합산하지 않고 선택 발전소 평균으로 취급한다. 자료 날짜가 어긋나면 일부 합계를 정상 합계로 만들지 않는다. 다중 발전소 계산은 테스트용 입력으로 검증했고 실제 자료는 추가하지 않았다.
- 서비스 운영: 연결 상태·마지막 조회 시각·갱신 주기(끄기/10초/30초/1분)·수동 새로고침. 기본 30초이며 화면을 떠나거나 브라우저 탭이 숨겨지면 조회를 중단한다. 요청은 중복 실행하지 않고 실패 시 이전 값과 마지막 반영 시각을 구분한다.
- 이력·알림: 모델 버전과 최근 알림. 현재 서버가 해당 계약을 제공하지 않아 예시 표기를 유지한다. `8099` 레퍼런스의 정보 범주를 참고했지만 브라우저의 배치 실행 수치를 서버 전체 트래픽으로 옮기지 않는다.
- 본문 14~16px, 보조 설명 12~13px, 제목 20~32px. 숫자는 고정폭 숫자 스타일을 사용한다. 차트의 날짜·축도 모바일에서 실제 12px를 유지한다.
- 흰색 표면과 중립 회색을 기본으로 사용한다. 흰색을 크림색으로 대체하지 않는다.
- 주황·하늘색 계열과 흰색·중립색으로 통일했다. 실측은 하늘색 `#568BA7`, 규칙 예측은 주황 `#B87643`이며 실선·점선도 함께 구분한다. 옅은 하늘색은 선택 메뉴·서버 지표, 옅은 주황은 내일 전망·예시 안내에 사용한다.
- 실측은 하늘색 실선 3px, 예측은 주황 점선 2.5px(6 4)다. 강조색 외에도 선 형태와 라벨로 구분한다.
- 카드마다 0.5초 진입, 60ms 간격, `backwards`. 차트는 1.1초 드러내기, 첫 로드 0.3초 지연·기간 변경 0초. 반복 애니메이션은 없다. 의미 없는 장식 막대·게이지는 통합 과정에서 제거했다.
- 태양광 일러스트의 SVG 도형·경로·viewBox 및 `.solar-art` 기본 치수 규칙은 보존하고 색상과 주변 여백을 최신 팔레트·배치에 맞췄다. SVG 자체에 고정 높이·잘림을 추가하지 않았다.
- 외부 폰트·이미지·JavaScript CDN 없이 동작한다. 계정 로그인, 알림 전송, 학습·배포 실행은 없다.

## 참고 자료와 적용 범위

| 자료 | 확인·반영한 부분 |
| --- | --- |
| 팀 운영 대시보드 저장본 | 실제 Chrome 화면의 요청 수, 응답시간, 성공률, 파이프라인, 모델·이력·알람 범주. 레퍼런스의 달러 수치와 모델 성능을 우리 결과로 옮기지 않음 |
| 팀 최초 레퍼런스 저장본 | 최초 초안에서 운영 흐름과 정보 범주 참고 |
| [Samsung Cloud Platform 콘솔 가이드](https://cloud.samsungsds.com/serviceportal/knowledge/tutorials_detail/common/scp_console.html) | 공개 가이드의 제목·본문 위계와 운영 정보 설명. 실제 고객 계정 콘솔에 로그인하지 않음 |
| [SAP Digital Typography](https://www.sap.com/design-system/digital/foundations/identity/typography/) | 공개 문서·화면의 고정 글자 계층, 가독성·명암 원칙. SAP 전용 폰트·브랜드는 복사하지 않음 |
| [IBM Carbon Typography](https://www.carbondesignsystem.com/building-blocks/foundations/typography/type-sets) | 기업용 제품의 본문 14px/표현용 16px, 보조 12px 기준 참고. 한국어 화면에 맞게 적용 |
| [Collect UI](https://collectui.com/) | 최초 탐색 구조 참고. 방문 당시 개별 갤러리 로딩은 미확인 |
| [WWIT 차트](https://wwit.design/component/chart) | 최초 한국어 지표·범례 위계 참고 |
| [Growth.Design 대시보드 사례](https://growth.design/case-studies/coronavirus-dashboard-ux) | 수치의 맥락·범위·단위·출처 표시 |
| [Animista](https://animista.net/), [Animate.css](https://animate.style/), [Hover.css](https://ianlunn.github.io/Hover/#effects) | 최초 타이밍·반복 지양·상호작용 피드백 참고. 라이브러리는 설치하지 않고 자체 CSS로 작성 |

## 근거와 데이터 경계

기준 문서: 저장소 `AGENTS.md`, `README.md`, `CONTRIBUTING.md`, `datasets/README.md`, `docs/proposal/domain-mapping.md`, `docs/proposal/3-operations-design.md`, `docs/decisions/README.md`, `docs/followups.md`.

- **실적·예보는 실제 값**이다. `datasets/hadong_upload_forecast_jma.csv`의 `Close`는 하루 발전량(kWh), D행의 `Volume`은 D+1의 일사량 예보(MJ/m²)다. 예보를 관측 일사량으로 표현하지 않는다.
- 재생일 **2025-06-04**, 최근 90일 **2025-03-07~06-04**. 최초 계산에 필요한 이력은 2025-02-27부터 읽는다. 기준일 이후 실적은 사용하지 않는다.
- **예측선은 LSTM 결과가 아닌 규칙 계산값**이다. `예보(D) = Volume(D-1)`, `pred(D) = Σ실적(D-7..D-1) / Σ예보(D-7..D-1) × 예보(D)`를 쓴다. 중간 계산은 반올림하지 않고 화면만 소수 첫째 자리로 표시한다.
- RMSE는 선택한 7/30/90일에 대해 **29.8 / 43.6 / 46.2 kWh/일**이다. 이는 규칙 기준선의 재생 오차이며 학습·홀드아웃 검증 성능이 아니다.
- 내일 06-05 예보 **27.7 MJ/m²**, 예측 **277.7 kWh**. 06-04 실적 **314.1**, 당일 예측 **276.9 kWh**. 최근 7일 실적 평균 **236.6 kWh/일**.
- 예보 출처는 Open-Meteo의 JMA 자료다. 차트 가까이에 [Weather data by Open-Meteo.com](https://open-meteo.com/) 링크를 둔다. 발전량 출처는 한국남부발전이다. 수집·가공·이용 조건은 `datasets/README.md`를 따른다.
- `tools/design/generate-chart-data.mjs`는 `app.js`의 `// BEGIN chart-data`~`// END chart-data`만 재생성한다. 원본 CSV는 읽기만 하고 생성값은 손으로 편집하지 않는다.
- CSV 업로드는 UTF-8, Date/Close/Volume 열, 최소 41행인 기존 서버 계약을 사용한다. 최대 10MB이며 업로드 후 과거 재생 차트를 임의로 바꾸지 않는다. 서버 미연결·거부·시간 초과는 화면에 안내한다.
- **서비스 상태·모델 로딩·상태 조회 응답시간·등록 데이터는 API 조회 값**이다. 응답시간은 프록시에서 `/health` 응답 본문을 읽기까지 걸린 시간으로, 예측 추론 지연이나 최근 24시간 평균이 아니다. `model_loaded=false`는 미로딩 상태이지 모델 부재의 증거가 아니다.
- 예측 요청 수·성공률·평균 추론시간은 현 API에 없으므로 기존 예시 숫자를 제거하고 미제공 안내를 둔다. 모델 버전 v1~v3 RMSE 35.6/29.1/24.8, 파이프라인·알림은 **예시**로 남긴다. 실제 반영 자동화가 연결됐다는 뜻이 아니다. 드리프트·배포 기준을 임의로 정하지 않았다.
- 서버 조회와 2025-06-04 발전량 재생은 서로 다른 시간축이다. API 조회가 성공해도 차트의 과거 재생일은 바뀌지 않는다. 발전소별 실시간 발전량·다중 발전소 실데이터 연동에는 추가 원천 자료와 API가 필요하다.
- `project/`, 모델·API·운영 설정과 `datasets/` 원본은 변경하지 않았다. 실제 서비스 증빙이 아니므로 디자인 폴더에 보관한다.

## 검증과 후속 범위

실행한 명령과 실제 브라우저 확인, 미검증 범위는 [verification.md](verification.md)에 기록한다. 최신 사용자 지시에 따라 기능 확장보다 디자인과 UI 흐름을 우선했다. 운영 환경 연결 시 실제 모델·로그·학습 이력을 계약에 맞춰 연동해야 한다.


## 서비스 운영 기능 (저장된 HAIC 화면 기준)

- CSV 업로드 및 드리프트 시뮬레이션은 서비스 운영 상단에 배치한다. 정상/드리프트 합성 배치는 기존 HAIC 설정(41개, 기준값 165, 변동성 0.012/0.036)을 사용한다. 태양광 저하 시뮬레이션으로 의미를 바꿔 표시하지 않는다.
- 단건 예측: 20개 close/volume JSON 편집, 예시 재생성, /predict 실행.
- 운영 지표: 5분/1시간/6시간/24시간 시계열, 요청 수/요청 가중 평균 응답시간/성공률, 성능 요약.
- 데이터셋, 시스템 설정, 현재 모델 조회 및 모델/알림 이력 새로고침. 이력과 알림은 각 목록에서 독립 스크롤한다.
- 서버 로그: 목록과 파일 내용 조회. 배치 응답으로 재학습 단계와 RMSE를 갱신한다.
- operations.js 및 server-dashboard.js를 수정한 경우 build-preview.mjs로 단일 HTML을 재생성한다.
- API 원점은 SOLAR_API_BASE_URL로 지정한다. 화면에는 임의 서버 주소 입력을 제공하지 않으며 프록시는 허용된 API 경로만 사용한다. API가 없는 기존 스켈레톤은 조회 불가로 표시한다. 정상/드리프트 배치 모두 재학습·승격을 유발할 수 있다.
- 기준 자료: 사용자가 저장한 ‘AIOps · HAIC 운영 대시보드.html’, ‘AIOps · HAIC 재학습 파이프라인.html’. 저장된 응답과 수치는 운영 데이터로 복사하지 않았다.
- Open-Meteo 예보를 실제 사용하므로 datasets/README.md의 출처 지침에 따라 링크를 유지한다.

백엔드 담당별 연결 지점과 미완료 항목: [INTEGRATION.md](INTEGRATION.md).
