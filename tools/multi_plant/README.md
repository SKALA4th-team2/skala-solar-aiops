# 여러 발전소 자료의 준비 도구

발전소가 여럿이 될 때의 자료 계약([`docs/proposal/multi-plant-data-contract.md`](../../docs/proposal/multi-plant-data-contract.md))을 기계로 확인하고, 발전소별·포트폴리오별 기간과 오차를 내는 도구다. 설계와 배경은 [`docs/proposal/multi-plant-extension.md`](../../docs/proposal/multi-plant-extension.md)에, 직접 돌린 기록은 [`docs/proposal/evidence/multi-plant/validation.md`](../../docs/proposal/evidence/multi-plant/validation.md)에 있다.

지키는 것은 다음과 같다.

- `project/` 의 코드를 고치지 않는다. 지금의 코드가 내는 문제는 그대로 불러 재현만 한다.
- `datasets/` 의 원자료를 고치지 않는다. 변환한 결과는 자료 폴더의 `generation/` 에 쓰고 커밋하지 않는다.
- 없는 값을 채우지 않는다. 결측은 빈 값으로, 모르는 용량과 좌표는 빈 칸으로 둔다.
- 합성 자료의 수치를 성능이나 제도 요건의 근거로 쓰지 않는다.
- 자료의 위치는 `--data-root` 로 준다. 다른 발전소의 원자료가 저장소 밖(백엔드를 돌릴 PC 의 다른 폴더)에 있어도 그대로 돈다.

## 어디서 돌리는가

`single_pc_probe.py` 를 뺀 나머지는 표준 라이브러리만 쓴다. `project/.venv` 의 파이썬이면 되고 저장소 루트에서 돌린다. Windows 에서는 `python` 대신 `project\.venv\Scripts\python` 으로 부른다. 출력은 UTF-8 로 고정했고 경로의 구분자에 기대지 않게 했다. **다만 Windows 에서 직접 돌려 확인하지는 못했다.** 검증은 macOS 에서 했다. `selftest.py` 는 지금의 서빙 코드를 불러 보는 항목이 있어 `project/data/` 를 읽는다(TensorFlow 는 필요 없다).

## 스크립트

| 스크립트 | 하는 일 | 결과 |
| --- | --- | --- |
| [`convert_kospo_raw.py`](convert_kospo_raw.py) | 한국남부발전 「태양광발전실적」 원자료를 정규화 실적(하루, 시간대별)과 계보 기록으로 바꾼다. 빈 칸을 0 으로 채우지 않고, 빠진 날을 값이 빈 행으로 채운다 | `<자료 폴더>/generation/<plant_id>/` |
| [`validate.py`](validate.py) | 등록부, 포트폴리오 구성, 발전소별 실적이 계약을 지키는지 본다. 오류가 있으면 종료 코드 1 | 화면, `--json` |
| [`portfolio_capacity.py`](portfolio_capacity.py) | 그 날짜에 적용되는 구성의 설비 용량 합계(kW, MW)를 낸다. 같은 원자료의 발전소는 한 번만 세고, 용량을 모르는 발전소는 빼고 알린다. 20MW 와 견준 값은 참고다 | 화면, `--json` |
| [`coverage.py`](coverage.py) | 발전소별 기간과 창의 수, 포트폴리오의 공통 대상일과 커버리지를 낸다. 창에 발전소가 섞이지 않는지 본다 | 화면, `--json` |
| [`evaluate.py`](evaluate.py) | 발전소별 오차와 포트폴리오 합계의 오차를 같은 대상일에서 낸다. 전일값, 7일 평균과 견주고 `--predictions` 로 모델의 예측도 함께 견준다. `--hourly` 는 제도의 식을 단순 기준 예측에 적용한 참고값이다 | 화면, `--json` |
| [`bundle_check.py`](bundle_check.py) | 모델, 스케일러, 피처의 뜻이 서로 짝이 맞는지 본다. `write` 로 묶음 기록을 만들고 `check` 로 견준다 | 묶음 기록(JSON), 종료 코드 |
| [`selftest.py`](selftest.py) | 합성 자료로 실패 사례 21건을 돌려 도구가 잘못된 자료를 실제로 잡는지 본다 | `--out` 폴더의 `selftest.txt`, `selftest.json` |
| [`single_pc_probe.py`](single_pc_probe.py) | 한 PC 의 학습 시간, 메모리, 모델 하나의 메모리, 학습 중의 예측 시간, 동시 기록을 잰다. **검증용 사본에서만 돌린다.** 서빙 앱의 패키지가 필요하다 | `--out` 폴더의 `single_pc_probe.json` |
| [`common.py`](common.py) | 계약의 열과 단위, 읽기와 검증 함수, 창 만들기, 발전소별 업로드 선택의 참고 구현 | |

## 새 발전소의 자료를 넣을 때

단계와 통과 조건은 [자료 계약의 6절](../../docs/proposal/multi-plant-data-contract.md#6-새-자료를-넣는-절차)에 있다. 명령만 모으면 다음과 같다. `<자료 폴더>` 는 저장소 안에서는 `datasets/plants` 다.

```bash
# 1. 등록부(plants.csv)에 한 줄을 더한다. 용량의 단위와 근거를 적고, 모르는 칸은 비운다.
# 2. 원자료를 정규화 실적으로 바꾼다
python tools/multi_plant/convert_kospo_raw.py --raw <원자료.csv> --plant-id <plant_id> --out-root <자료 폴더>
# 3. 계약을 지키는지 본다. 오류가 0건이어야 다음으로 간다
python tools/multi_plant/validate.py --data-root <자료 폴더>
# 4. 포트폴리오 구성(portfolio_members.csv)에 넣고 용량 합계와 공통 기간을 본다
python tools/multi_plant/portfolio_capacity.py --data-root <자료 폴더> --portfolio <portfolio_id>
python tools/multi_plant/coverage.py --data-root <자료 폴더> --portfolio <portfolio_id>
# 5. 기준 예측으로 발전소별과 합계의 오차를 본다. 모델의 예측 파일이 있으면 --predictions 로 함께 견준다
python tools/multi_plant/evaluate.py --data-root <자료 폴더> --portfolio <portfolio_id> --start 2025-06-09 --end 2026-02-27
```

모델의 예측 파일은 `plant_id, target_date, predicted_kwh` 세 열의 CSV 다. 학습 스크립트가 시험 구간의 예측을 이 모양으로 내보내면 된다.

## 백엔드를 돌릴 PC 에서 다시 잴 때

```bash
# 저장소 루트에서. --prepare 가 커밋된 project/ 를 빈 폴더에 풀고 하동의 업로드 파일을 넣는다 (운영체제 공통)
python tools/multi_plant/single_pc_probe.py --prepare <사본 폴더>
python tools/multi_plant/single_pc_probe.py --project <사본 폴더>/project --out <결과를 둘 폴더>
```

`<사본 폴더>` 는 저장소 밖의 빈 폴더다. Windows 라면 예를 들어 `C:\temp\pc_probe` 다.

- **Windows 에서의 차이.** 메모리는 프로세스의 작업 집합(Working Set)으로 읽는다. macOS 와 리눅스에서 읽는 값과 재는 방법이 달라, 이 문서의 macOS 값과 그대로 견주지 않는다. CPU 시간은 재지 않는다. 읽지 못한 값은 `null` 로 남긴다.
- **Windows 쪽 코드는 Windows 에서 돌려 보지 못했다.** macOS 에서 "유닉스 전용 모듈이 없는 조건"을 흉내 내어 멈추지 않고 `null` 을 남기는 것까지만 확인했다. 처음 돌릴 때는 `--steps env,baseline` 처럼 앞의 단계부터 돌려 본다.

몇 분 걸린다. `finetune` 단계는 시간을 재려고 **측정 프로세스 안에서만** 게이트 값을 연다. 코드의 값은 바꾸지 않고, 그 통과는 품질의 근거가 아니다. 결과의 숫자로 [`single-pc-operation.md`](../../docs/proposal/single-pc-operation.md)의 3절과 4절을 고친다.

## 2026-10-07 에 돌린 것

| 무엇 | 입력 | 기록 |
| --- | --- | --- |
| 합성 자료 점검 21건 | 도구가 만드는 합성 자료 | M02 |
| 저장소의 현재 자료 | `datasets/raw/data_15043409.csv`, `datasets/plants/` 의 등록부 | M03 |
| 하동 5곳의 실제 자료 | 하수처리장은 저장소의 원자료, 이웃 4곳은 이전 조사 때 받아 둔 공식 파일의 사본(저장소에 넣지 않았다) | M01, M04, M05, M06 |
| 지금 코드의 문제 재현 | 지금의 `project/` 코드 | M07 |
| 한 PC 측정 | 커밋 `9ad93b1` 의 사본과 하동의 업로드 파일 | M09 |
