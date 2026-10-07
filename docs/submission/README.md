# 제출 및 다른 PC 실행

제출물은 final 브랜치 코드, 기획서6항목, 검증 증빙, 모델seed ZIP과manifest다. Git에는 모델·운영DB·가상환경·API키를 넣지 않는다. 이PC에서는 project/submission/solar-hourly-seed.zip을 전달한다. GitHub Actions의 solar-hourly-submission-* artifact에도 새 환경에서 재생성·검증한 모델ZIP과컨테이너 증빙이 포함된다.

## 모델 설치

코드를 받거나 final 브랜치를 checkout한 뒤 ZIP과 같은 이름의 .zip.manifest.json을 project/submission에 함께 놓는다. 모든 명령은 project/에서 실행한다.

```powershell
py -3.11 -m venv .venv
.venv\Scripts\python -X utf8 -m pip install -r requirements.txt
.venv\Scripts\python -X utf8 scripts/install_bundle.py submission/solar-hourly-seed.zip
.venv\Scripts\python -X utf8 scripts/run_backend.py
```

기존 가상환경은 다시 만들지 않아도 된다. install_bundle.py는 전체ZIP과개별파일SHA를 확인하고 승인된31개seed만 설치한다. 시작 시 새 state의MLflow에 다시 등록한다. 기본 화면8077,명세/docs. 외부API키는 필요하지 않다.

원본자료에서 다시 학습하려면 requirements-training.txt를 설치하고 tools/hourly/prepare.py→train.py→finalize.py→tools/submission/package_models.py를 실행한다. 이미 완료된평가결과를 재사용하지않는 새실험은 HOURLY_EVIDENCE_DIR를빈폴더로지정한다.

## 컨테이너 검증

이PC에는 Docker/WSL이없어 GitHub Actions의 Linux Docker에서실제빌드·실행검증을수행한다. 워크플로우는 .github/workflows/submission.yml이다. 원본시간자료를다시만들고학습한뒤컨테이너에서31개모델예측·자동재학습·버전변경·롤백·재시작영속성을확인한다. 성공여부는 Actions실행결과와artifact의 docker-evidence/summary.json,restart-persistence.json,compose-ps.json,container.log로판정한다. 실행이성공하기전에는 검증완료로표시하지않는다.

Docker가있는PC에서는 seed설치후다음과같이실행한다.

```powershell
docker compose -f serving_app/docker-compose.yml up --build -d
```

화면 http://127.0.0.1:8099/ . 상태는 /health의execution_unit=container와worker_alive=true로확인한다. 운영기본은SOLAR_DEMO_MODE=0이다. 합성시험시만1로설정하고별도volume에서실행한다.

## 발표 순서

① 이해관계자 불편 →② 시간별 LSTM과독립성능 →③ 품질게이트·보류·재학습정책 →④ 실제구조 →⑤ 입력검증·예측기록 →⑥ v1→v2→v1·Docker·재시작 증빙 순서로설명한다. 발표용 시나리오는 docs/proposal/6-demo.md에있다.

실시간자료수집,실제예보공개시각,현장관측기상검증,장기가용성99%,정산요건충족은실증한것이아니다. 합성드리프트기능시연의RMSE를 모델의독립예측성능으로발표하지않는다.
