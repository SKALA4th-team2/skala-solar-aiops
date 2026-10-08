# 0016 승인된 모델 seed의 Git 배포

2026-10-08 저장소 소유자가 팀원 합의에 따라 모델 파일을 GitHub에 포함하도록 명시적으로 요청했다. 이에 AGENTS.md, CLAUDE.md, CONTRIBUTING.md의 모델 일괄 제외 정책을 승인 seed에 한해 변경한다.

project/serving_app/models/hourly-seed/의 승인 모델 31개와 고정 스케일러, manifest, catalog, portfolio_quality, 재생용 history CSV를 함께 버전 관리한다. 이력은 최초 부팅과 화면 재생에 필요하다. 기존 검증된 seed를 사용하며 새 학습이나 가중치 변경은 하지 않는다.

재학습 산출물, runtime 디렉터리, MLflow DB/아티팩트, 로그, 사용자 업로드, 비밀값, 가상환경은 계속 제외한다. .gitignore 예외는 배포용 seed의 지정된 파일명으로 제한한다. 모델 단독 교체를 금지하고 manifest의 승인 여부와 모델/스케일러 SHA를 확인한다. 자동 재학습 결과를 Git에 자동 push하지 않는다.

새 PC에서는 clone → requirements 설치 → run_backend.py 실행으로 로컬 MLflow 등록과 서빙을 시작한다. 별도 ZIP은 선택적 오프라인 백업이다. Git에 모델을 넣는 것은 외부 서버 배포와 다르다.
