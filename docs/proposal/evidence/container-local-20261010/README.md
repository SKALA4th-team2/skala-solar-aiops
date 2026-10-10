# 컨테이너 실행 화면과 짧은 구간의 가용성 측정

2026-10-10 에 팀원 PC(macOS, Docker 29.6.2, linux/arm64)에서 `main`(커밋 `7c643a0`)의 코드로 이미지를 빌드해 띄운 컨테이너의 기록이다. GitHub Actions 의 실행 로그(`evidence/submission_20261008/`)와 달리 실제 화면이다.

| 파일 | 내용 |
| --- | --- |
| `container-service.png` | 컨테이너(8099)가 내보내는 서비스 운영 화면 |
| `container-swagger-health.png` | Swagger 에서 `GET /health` 를 실행한 화면. 응답의 `execution_unit` 이 `container` 다 |
| `compose-ps.txt`, `docker-version.txt`, `health.json` | `docker compose ps`, Docker 버전, `/health` 응답 |
| `availability-10min.json` | 10분 동안 1초 간격으로 `POST /predict` 600번을 보낸 결과 |

## 가용성 측정의 범위

600번 가운데 600번이 성공했다. 응답 시간은 중앙값 0.016초, 95번째 백분위 0.019초, 최대 0.217초다. 같은 동안 `/health` 를 60번 확인했고 모두 작업자가 살아 있었다.

이 값은 컨테이너 하나, 클라이언트 하나, 10분의 값이다. 기획서 ② 의 가용성 목표(99%)는 한 달 단위의 목표이고, 이 측정으로 달성했다고 쓰지 않는다. 재시작, 동시 요청, 재학습이 도는 동안의 응답은 이 측정에 들어 있지 않다. 측정 스크립트는 [`tools/proposal/availability_soak.py`](../../../../tools/proposal/availability_soak.py)다.
