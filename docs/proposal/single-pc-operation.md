# 단일 PC 실행과 인수인계

project/에서 scripts/run_backend.py를 실행한다. 기본8077에서 FastAPI1프로세스와 SQLite 작업자1프로세스가함께동작한다. 재학습과배포는OS잠금으로직렬화하며API는기존모델을계속사용한다. current.json 변경을확인하면검증된새모델로교체한다.

운영state는data/runtime-hourly,제출기능시연은data/runtime-submission,컨테이너는/runtime을사용한다. API와작업자는같은state를공유해야하며각시연환경끼리는분리한다. SOLAR_LOG_DIR로로그위치를분리할수있다.

새PC에는코드와모델ZIP·manifest를전달한다. install_bundle.py가해시와경로를검사하고seed_runtime.py가새파일시스템의MLflow에등록한다. 기존절대경로를포함한DB를복사하지않는다. 정확한명령과검증은 [제출안내](../submission/README.md), [운영안내](../backend-runbook.md)를따른다.
