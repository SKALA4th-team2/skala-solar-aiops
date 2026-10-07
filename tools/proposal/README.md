# 기획서의 검증과 그림을 만드는 도구

[`docs/proposal/`](../../docs/proposal/)의 기획서가 "실행해 확인했다"고 적은 내용을 다시 만들 수 있게 하는 스크립트다. 결과는 [`docs/proposal/evidence/`](../../docs/proposal/evidence/)와 [`docs/proposal/assets/`](../../docs/proposal/assets/)에 쓴다. 건별 기록은 [`validation.md`](../../docs/proposal/evidence/validation.md)에 있다.

지키는 것은 다음과 같다.

- `project/` 의 코드를 고치지 않는다. 빈칸도 채우지 않는다. 지금의 코드가 내는 결과를 그대로 남긴다.
- `datasets/` 의 파일을 바꾸지 않는다. 틀린 파일을 시험할 때는 메모리에서만 만들어 보낸다.
- `docs/research/` 와 `tools/verify/` 의 보관 결과를 덮어쓰지 않는다.
- 비밀값을 쓰지 않는다. 로그인이나 키가 필요한 자료를 받지 않는다.

## 어디서 돌리는가

서빙과 학습을 돌리면 모델 파일, MLflow 기록, 업로드 파일, 로그가 생긴다. `.gitignore` 가 막고 있지만, 검증할 때는 저장소 밖의 **검증용 사본**에서 돌렸다.

```bash
# 저장소 루트에서. 커밋된 project/ 를 그대로 임시 폴더에 푼다
mkdir -p /tmp/verify_run && git archive HEAD project | tar -x -C /tmp/verify_run
cd /tmp/verify_run/project
```

- 그 사본의 `project/` 를 작업 디렉터리로 두고 서버와 학습 스크립트를 돌린다. 다른 폴더에서 돌리면 import 경로가 어긋난다.
- 사본을 둔 폴더의 이름을 `verify_run` 으로 하면 `sanitize_logs.py` 가 로그 안의 그 경로를 알아서 짧게 바꾼다. 다른 이름이면 `--copy-root` 로 알려 준다.
- 팀이 `project/.venv` 를 만든 뒤에는 저장소의 `project/` 에서 바로 돌려도 된다.

## 스크립트

실행 위치가 "저장소 루트"인 것은 그 줄에 적힌 패키지만 있으면 어느 파이썬에서 돌려도 된다. "project/"인 것은 서빙 앱의 패키지(`requirements.txt`)가 설치된 파이썬으로, 검증용 사본의 `project/` 에서 돌린다.

| 스크립트 | 하는 일 | 실행 위치 | 필요한 것 | 결과 |
| --- | --- | --- | --- | --- |
| [`record_environment.py`](record_environment.py) | 커밋, 운영체제, 파이썬과 패키지 버전(`requirements.txt` 와 대조), 컨테이너 도구, 빌드 뒤 이미지가 남았는지를 적는다. `--compose-dir` 을 주면 그 폴더에서 `docker compose config` 도 돌린다 | 저장소 루트. 서빙에 쓴 파이썬으로 | 표준 라이브러리, git. 컨테이너 항목은 docker | `evidence/environment.txt` |
| [`static_scan.py`](static_scan.py) | 코드에 남은 빈칸, 정책 상수, 주가 표현, 모델을 바꾸는 코드를 읽어 센다 | 저장소 루트 | 표준 라이브러리, git | `evidence/static_scan.*` |
| [`http_checks.py`](http_checks.py) | 떠 있는 서버에 요청을 보내고 요청과 응답을 건마다 파일로 남긴다. `--phase` 는 `pre`, `upload-haic`, `upload-errors`, `upload-hadong`, `post`, `latency`, `upload-gaps`, `mlflow-lazy` 가운데 하나다 | 저장소 루트 | requests. 서버가 떠 있어야 한다 | `--out` 으로 준 폴더(`evidence/http/`, `evidence/http_mlflow_lazy/`), `evidence/openapi.json`, `evidence/latency_http.json` |
| [`registry_dump.py`](registry_dump.py) | MLflow 의 실행 기록, 모델 버전과 단계, 스케일러의 값, 업로드 폴더의 파일 이름을 적는다. 읽기만 한다 | project/ | mlflow | `evidence/registry/registry_<이름>.json` |
| [`registry_semantics.py`](registry_semantics.py) | 승격과 되돌리기가 레지스트리에서 어떻게 동작하는지 본다. **새 버전을 하나 등록했다가 Archived 로 내린다.** 검증용 사본에서만 돌린다 | project/ | mlflow | `evidence/registry/registry_semantics.json` |
| [`model_timing.py`](model_timing.py) | 레지스트리의 Production 모델을 불러오는 시간과 무작위 입력 한 건의 계산 시간을 잰다. 엔드포인트의 응답 시간이 아니다 | project/ | mlflow, tensorflow | `evidence/latency_model.json` |
| [`offline_model_eval.py`](offline_model_eval.py) | `train_and_register.py` 가 학습해 MLflow 에 남긴 모델을 서버 없이 다시 평가한다 | project/ | mlflow, tensorflow, pandas | `evidence/offline_model_eval.*` |
| [`data_checks.py`](data_checks.py) | 업로드 파일의 모양과 날짜 정렬, 창과 분할, 기준 예측, 성능 지표, 주입 장면, 값의 범위를 계산한다 | 저장소 루트 | pandas, numpy | `evidence/data_checks.*` |
| [`threshold_sweep.py`](threshold_sweep.py) | 임계값별 오경보와 감지, 날마다 판정할 때 알아채는 데 걸리는 날, 재학습의 조건이 채워지는 날을 센다 | 저장소 루트 | pandas, numpy | `evidence/threshold_sweep.*` |
| [`make_figures.py`](make_figures.py) | 기획서의 그래프 여섯 장을 그린다 | 저장소 루트 | pandas, numpy, matplotlib. 한글 글꼴은 Apple SD Gothic Neo 로 정해 두었다 | `assets/*.png`, `evidence/figures_data.json` |
| [`capture_screens.py`](capture_screens.py) | 떠 있는 서버의 대시보드와 API 문서를 헤드리스 Chrome 으로 열고, 단추가 부르는 함수를 브라우저 안에서 실행한 뒤의 화면 일곱 장을 저장한다. `--upload` 를 주면 그 파일을 실제로 올린다 | 저장소 루트 | Chrome, websockets. 서버가 떠 있어야 한다 | `evidence/screens/*.png` |
| [`sanitize_logs.py`](sanitize_logs.py) | 받아 둔 원본 로그를 증빙으로 둘 수 있게 정리한다. `--src` 는 서버와 학습의 로그를, `--docker` 는 이미지 빌드의 로그를, `--registry` 는 레지스트리 기록 안의 경로를 다룬다 | 저장소 루트 | 표준 라이브러리 | `evidence/logs/*.log` |
| [`rerun_existing_checks.py`](rerun_existing_checks.py) | `tools/verify/` 의 스크립트 셋을 다시 돌려 보관된 결과와 견준다 | 저장소 루트 | pandas, numpy | `evidence/existing_checks_rerun.txt` |
| [`check_mermaid.py`](check_mermaid.py) | 문서의 Mermaid 그림을 헤드리스 Chrome 에서 해석하고 그려 본다. `--png-dir` 을 주면 그린 결과를 그림 파일로 저장한다 | 저장소 루트 | Chrome, websockets, 인터넷 | `evidence/mermaid_check.txt`, `evidence/mermaid/*.png` |
| [`check_docs.py`](check_docs.py) | 문서의 링크와 위치, 표의 칸 수, JSON 예시, 검증 번호, 보관 문서의 변경을 점검한다 | 저장소 루트 | 표준 라이브러리, git | `evidence/docs_check.txt` |
| [`common.py`](common.py) | 위 스크립트가 함께 쓰는 자료 읽기와 계산 함수 | | | |

## 2026-10-07 에 돌린 순서

커밋 `58d6ff8` 의 검증용 사본에서 다음 순서로 돌렸다. `<저장소>` 는 이 저장소의 경로, `<사본>` 은 검증용 사본의 `project/` 다. 서버와 학습 스크립트의 표준 출력은 파일로 받아 두었다.

```bash
# 1. 서버를 띄운다 (<사본> 에서)
uvicorn serving_app.main:app --host 127.0.0.1 --port 8077

# 2. 다른 터미널, <저장소> 에서. 올리기 전의 호출
python tools/proposal/http_checks.py --base http://127.0.0.1:8077 --out docs/proposal/evidence/http --phase pre

# 3. 주가 예시 파일을 올리고 학습 (학습과 registry_dump 는 <사본> 에서)
python tools/proposal/http_checks.py --base http://127.0.0.1:8077 --out docs/proposal/evidence/http --phase upload-haic
python scripts/train_baseline_v1.py
python serving_app/train_and_register.py
python <저장소>/tools/proposal/registry_dump.py --label 1-after-haic-train --out <저장소>/docs/proposal/evidence/registry

# 4. 틀린 파일과 태양광 파일을 올리고 학습
python tools/proposal/http_checks.py --base http://127.0.0.1:8077 --out docs/proposal/evidence/http --phase upload-errors
python tools/proposal/http_checks.py --base http://127.0.0.1:8077 --out docs/proposal/evidence/http --phase upload-hadong
python scripts/train_baseline_v1.py
python <저장소>/tools/proposal/registry_dump.py --label 2-after-hadong-baseline --out <저장소>/docs/proposal/evidence/registry
python serving_app/train_and_register.py
python <저장소>/tools/proposal/registry_dump.py --label 3-after-hadong-train --out <저장소>/docs/proposal/evidence/registry

# 5. 학습 뒤의 호출, 응답 시간, 시뮬레이션
python tools/proposal/http_checks.py --base http://127.0.0.1:8077 --out docs/proposal/evidence/http --phase post
python tools/proposal/http_checks.py --base http://127.0.0.1:8077 --out docs/proposal/evidence/http --phase latency
python scripts/simulate_drift.py

# 6. MLflow 의 모델로 서빙 (서버를 내리고 다시 띄운다. 둘째가 떠 있는 동안 mlflow-lazy 단계를 보낸다)
MODEL_SOURCE=mlflow LOADING_MODE=eager uvicorn serving_app.main:app --host 127.0.0.1 --port 8077
MODEL_SOURCE=mlflow uvicorn serving_app.main:app --host 127.0.0.1 --port 8077
python tools/proposal/http_checks.py --base http://127.0.0.1:8077 --out docs/proposal/evidence/http_mlflow_lazy --phase mlflow-lazy

# 7. 컨테이너 (<사본> 에서)
docker compose -f serving_app/docker-compose.yml config
docker build --progress=plain -f serving_app/Dockerfile -t solar-aiops-verify:58d6ff8 .

# 8. 기본 설정으로 서버를 다시 띄우고: 내용이 틀린 업로드, 레지스트리의 동작, 모델 시간, 화면, 오프라인 평가
python tools/proposal/http_checks.py --base http://127.0.0.1:8077 --out docs/proposal/evidence/http --phase upload-gaps
python <저장소>/tools/proposal/registry_semantics.py --out <저장소>/docs/proposal/evidence/registry/registry_semantics.json
python <저장소>/tools/proposal/model_timing.py --out <저장소>/docs/proposal/evidence/latency_model.json
python tools/proposal/capture_screens.py --base http://127.0.0.1:8077 --out docs/proposal/evidence/screens --upload datasets/hadong_upload_forecast_jma.csv
python <저장소>/tools/proposal/offline_model_eval.py --out <저장소>/docs/proposal/evidence

# 9. 받아 둔 로그를 정리한다 (<저장소> 에서)
python tools/proposal/sanitize_logs.py --src <로그를 받아 둔 폴더> --out docs/proposal/evidence/logs
python tools/proposal/sanitize_logs.py --docker <빌드 로그> --out docs/proposal/evidence/logs
python tools/proposal/sanitize_logs.py --registry docs/proposal/evidence/registry

# 10. 서버 없이 돌리는 것 (<저장소> 에서)
python tools/proposal/record_environment.py --compose-dir <사본>
python tools/proposal/static_scan.py
python tools/proposal/data_checks.py
python tools/proposal/threshold_sweep.py
python tools/proposal/make_figures.py
python tools/proposal/rerun_existing_checks.py
python tools/proposal/check_mermaid.py --png-dir docs/proposal/evidence/mermaid
python tools/proposal/check_docs.py
```

숨기지 않고 적어 둘 것이 있다.

- **도구를 증빙보다 나중에 고친 곳이 있다.** `http_checks.py` 의 `upload-gaps` 와 `mlflow-lazy` 단계, `sanitize_logs.py` 의 `--docker` 와 `--copy-root`, `record_environment.py` 는 앞 단계의 증빙을 만든 뒤에 보탰다. 앞 단계가 보내는 요청은 바꾸지 않았다.
- **MLflow 서빙의 요청과 응답은 두 번 남겼다.** 15:25 에 처음 띄웠을 때의 서버 로그가 `logs/07`, `logs/08` 이고, 요청과 응답은 16:58 에 `mlflow-lazy` 단계로 다시 보내 `http_mlflow_lazy/` 에 남겼다(`logs/12`). 결과는 같다.
- **환경 기록도 두 번 만들었다.** 15:46 에 손으로 모아 적은 것을 16:59 에 `record_environment.py` 로 다시 만들었다.
- **레지스트리 기록 셋(`registry_1` ~ `registry_3`)은 만든 뒤에 `--registry` 로 `tracking_uri` 의 절대 경로를 가렸다.** 지금의 `registry_dump.py` 는 처음부터 `(project)` 로 적는다. 표기가 다른 것은 그 때문이다.
- **정리한 로그의 이름은 `sanitize_logs.py` 의 `NAMES` 에 묶여 있다.** 받아 둔 파일의 이름이 다르면 그 표를 고친다. 원본 로그는 저장소에 넣지 않았다.
- **첫 baseline 로그(`logs/02`)의 종료 코드가 비어 있다.** 받아 적을 때 값을 놓쳤다. 실패는 로그의 오류 문장으로 확인된다.

## 빈칸을 채운 뒤 다시 돌릴 때

지금의 결과는 빈칸이 남은 코드의 것이다. 코드를 고친 뒤에는 2번부터 같은 명령을 다시 돌리면 `evidence/` 의 파일이 새 결과로 바뀐다. 그 뒤에 할 일은 다음과 같다.

1. `validation.md` 의 "실제"와 "판정"을 새 결과로 고친다.
2. 기획서 ⑤ 의 응답 예시와 ⑥ 의 "실제 결과"를 새 결과로 고친다. 조사의 수치를 결과 자리에 넣지 않는다.
3. 요청의 모양을 바꿨으면 `http_checks.py` 의 요청 본문도 함께 고친다. 지금은 `volume` 을 정수로 반올림해 보낸다.
4. `python tools/proposal/check_docs.py` 로 링크와 표를 다시 점검한다.

## 알아 둘 것

- `registry_semantics.py` 는 레지스트리에 버전을 하나 더 만든다. 시연에 쓸 레지스트리에서는 돌리지 않는다.
- `capture_screens.py` 는 `--upload` 를 주면 실제로 파일을 올린다. 그 서버의 "가장 최근 파일"이 바뀐다.
- `http_checks.py --phase upload-gaps` 는 틀린 파일을 다섯 번 올린 뒤 원래 파일을 다시 올려 되돌린다. 틀린 파일은 `data/uploads/` 에 남는다.
- `make_figures.py` 의 글꼴은 macOS 의 것이다. 다른 운영체제에서는 스크립트 위쪽의 글꼴 이름을 바꾼다.
- `check_mermaid.py` 는 Mermaid 를 CDN 에서 받는다. GitHub 가 쓰는 판과 다를 수 있다.
- 그림의 색을 검사한 스크립트(`evidence/palette_check.txt`)는 이 저장소에 없다. 그림을 만든 작업 도구에 들어 있던 것이다.
