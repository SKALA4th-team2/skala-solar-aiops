> **현행: 시간별31개소 UI.** 실행코드는 hourly-ui.js이며 [현재 연결](INTEGRATION.md), [새 검증 증빙](../../proposal/evidence/hourly_20261007/README.md)을 따른다. 아래는 이전 일별 디자인/시험 이력이다.

---
name: Solar Field Journal
description: 발전소 운전일지와 기상 관측표를 바탕으로 한 Solar Ops의 시각 언어
colors:
  primary: "#283E4C"
  secondary: "#568BA7"
  tertiary: "#B87643"
  surface: "#FFFFFF"
  sky-surface: "#EFF5F8"
  outlook-surface: "#FCF3EA"
  outlook-ink: "#89572F"
  muted: "#5D6E79"
typography:
  measurement:
    fontFamily: Pretendard, Apple SD Gothic Neo, sans-serif
    fontSize: 84px
    fontWeight: 550
    lineHeight: 1.05
    letterSpacing: -4px
  heading:
    fontFamily: Pretendard, Apple SD Gothic Neo, sans-serif
    fontSize: 32px
    fontWeight: 650
    lineHeight: 1.3
  body:
    fontFamily: Pretendard, Apple SD Gothic Neo, sans-serif
    fontSize: 14px
    lineHeight: 1.5
  metadata:
    fontFamily: ui-monospace, monospace
    fontSize: 12px
rounded:
  control: 3px
  panel: 0px
spacing:
  small: 8px
  medium: 16px
  large: 24px
  gutter: 36px
components:
  workspace:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.primary}"
  navigation:
    backgroundColor: "{colors.sky-surface}"
    textColor: "{colors.primary}"
  outlook:
    backgroundColor: "{colors.outlook-surface}"
    textColor: "{colors.outlook-ink}"
  caption:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.muted}"
---

## Overview

하동 공공시설의 태양광 발전 담당자가 읽는 운전일지다. 확정된 발전량을 먼저 읽고, 그 값이 최근 추세 속에서 어디에 놓이는지 확인한 다음, 다음 날 예보를 읽는다. 기상 관측표처럼 숫자·날짜·단위의 위치가 안정적이어야 한다.

이 방향은 Google Labs의 DESIGN.md 형식과 철학을 참고해 Solar Ops에 맞게 정한 것이다. 특정 예제의 색이나 컴포넌트를 복제하지 않는다.
출처: https://github.com/google-labs-code/design.md/blob/main/PHILOSOPHY.md
형식: https://github.com/google-labs-code/design.md/blob/main/docs/spec.md

## Colors

하늘색은 관측된 발전량과 현재 선택 위치를 뜻한다. 주황은 아직 확정되지 않은 전망과 주의해서 읽을 예시를 뜻한다. 흰 배경과 청회색 글자를 기본으로 사용한다. 강조색을 카드마다 번갈아 칠하지 않는다.

실측은 #568BA7 실선, 예측은 #B87643 점선이다. 같은 의미는 범례·툴팁·곡선에서 같은 색을 쓴다. 차트의 색과 선 형태를 함께 구분한다.

## Typography

확정 발전량 한 곳에만 최대 84px의 숫자를 쓴다. 단위는 숫자보다 작고 날짜는 별도 줄에 둔다. 평균과 오차는 30px 안팎의 보조 측정값이다. 예측값은 주황 전망 영역에서 42~68px로 표시한다. 고정폭 숫자를 사용하고 외부 폰트 다운로드에 의존하지 않는다.

## Layout

데스크톱의 왼쪽 200px는 업무 메뉴다. 본문은 넓은 실적·추이 영역과 좁은 전망 영역으로 나눈다. 실적 영역 위에는 큰 확정값 하나와 세로로 쌓인 보조값 두 개, 아래에는 넓은 추이 그래프가 놓인다. 전망 영역은 이 두 행에 걸쳐 하나의 여백으로 이어진다.

1000px 이하에서는 전망을 추이 아래로 옮긴다. 700px 이하에서는 기존 76px 업무 메뉴를 유지하고 확정값 → 보조값 → 추이 → 전망 순서로 읽는다. 긴 내용은 본문 내부에서 스크롤한다.

## Elevation & Depth

그림자와 겹겹의 상자를 쓰지 않는다. 얇은 구분선, 글자 크기, 여백으로 영역을 나눈다. 예보 영역의 옅은 주황 면만 큰 색면으로 사용한다.

## Shapes

내용 영역은 직각이다. 버튼과 선택 표시는 3px의 작은 반경을 쓴다. 태양광 일러스트의 도형과 비율은 기존 자산을 그대로 보존한다. 원은 태양과 알림 표식처럼 의미가 있을 때 쓴다.

## Components

기간 선택은 그래프 머리의 밑줄 탭이다. 일별 기록은 접힌 표로 제공한다. 서비스 화면은 현재 조회 지표와 예시 재학습 흐름을 구분한다. 이력 화면은 현재 모델 행과 시간 순 알림의 대응을 쉽게 읽도록 한다.

운영 API가 연결되지 않으면 미연결로 표시한다. 과거 자료의 규칙 예측을 실제 LSTM 모델 성능으로 표현하지 않는다. CSV 업로드는 별도 대화상자에서 파일과 형식을 확인한 후 전송한다. 기간·발전소·키보드 툴팁 기능은 유지한다.

## Do's and Don'ts

- 확정값·추이·전망의 읽는 순서를 유지한다.
- 색 없이도 선 형태와 라벨로 구분할 수 있게 한다.
- 동일 크기의 KPI 카드 줄, 장식용 게이지, 의미 없는 변화율을 추가하지 않는다.
- 그라데이션·유리 효과·과도한 그림자를 사용하지 않는다.
- 실제 조회, 과거 자료 재생, 디자인 예시의 경계를 보존한다.

본문과 주요 설명은 16px, 작은 표지·날짜·상태 배지는 최소 15px로 한다. 지표 제목은 18px/700, 섹션 제목은 24px/750, 핵심 수치는 750 굵기를 사용한다. 설명과 단위는 보통 굵기로 유지해 중요도를 구분한다. 전망 패널은 콘텐츠 높이를 따르고 태양광 그림은 고정 여백을 사용해 일별 기록 확장의 영향을 받지 않는다.

화면 높이에 따라 글씨 대신 여백과 차트·삽화의 높이를 조절한다. 데스크톱은 1440×900의 기본 접힘 상태를 한 화면에 담고, 낮은 화면과 모바일에서는 콘텐츠 높이를 보존하며 세로 스크롤을 허용한다. 스크롤바를 숨기지 않는다. 일별 기록을 열거나 브라우저를 확대했을 때 정보를 감추거나 전체 화면을 축소하지 않는다.

운영 조작은 서비스 운영 상단(CSV, 드리프트)에 모은다. 단건 예측과 상세 조회는 접이식 영역에 배치한다. 모델/알림 제목은 고정하고 각 목록에 독립 스크롤을 적용한다. 설명은 짧은 항목형 표기를 사용하며 실제 데이터 출처와 예시 여부는 유지한다.
