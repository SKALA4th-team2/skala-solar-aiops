# 반박 검증 재현

2026-10-07. 기존 대조 스크립트를 그대로 믿지 않고 저장소 원본을 읽는 별도 계산을 실행했다. 원본·`project/`·사전 조사 문서를 변경하지 않는다. LSTM 학습과 앱 실행은 검증 범위 밖이다.

`verify_t3t4.py`는 Python 표준 라이브러리만 사용한다. 다른 수치 계산은 numpy/pandas, T1의 Ridge는 scikit-learn이 필요하다. 이번 환경은 Python 3.11, numpy 2.4.6, pandas 2.3.3, scikit-learn 1.9.0이었다. 결과의 입력 해시와 조건을 함께 확인한다.

저장소 루트에서 실행한다. 출력 경로는 덮어쓰기를 피하려면 임시 폴더로 바꾼다. T5 두 스크립트는 스크립트와 같은 폴더의 결과 JSON을 갱신한다.

```sh
python tools/verify/verify_t1t2.py --repo . --output /tmp/t1t2-result.json
python tools/verify/verify_t3t4.py --root .
python tools/verify/t5_independent_audit.py .
python tools/verify/t5_ceiling_audit.py .
python tools/verify/t6t7_independent.py .
python tools/verify/validate_audit_artifacts.py --repo .
```

공식 설비·계약·이웃 발전소 CSV는 로그인이나 키 없이 새로 내려받았다. 공개 파일이 교체될 수 있으므로 `official-result.json`의 다운로드 URL·수정일·SHA-256과 비교한다. 다운로드 실패 시 확인한 것으로 처리하지 않는다.

```sh
python tools/verify/fetch_official_sources.py --output-dir /tmp/solar-official
python tools/verify/verify_official_neighbors.py --repo . --sources /tmp/solar-official --output /tmp/official-result.json
```

`t6t7_source_evidence.json`에는 새로 받은 전력시장 규칙·중개시장 규칙·2025년 시장통계의 URL, 해시, 페이지, 대조 범위를 보관했다. `t6t7_source_evidence.py`는 `--rule 규칙.pdf --broker 중개규칙.hwp --market 시장통계.pdf`를 받으며 pypdf와 olefile이 필요하다. PDF 표는 화면으로도 대조했다. 바이너리 원문은 이 폴더에 복제하지 않았다.

`hadong_daily_full.csv`의 ASOS 열은 정제된 결합 자료다. 원 ASOS 연도별 관측·위성 전기간 응답·일부 예보 모델 예측·정비 준공기록이 없으므로 모든 원 연구를 재현했다는 뜻은 아니다. 저장된 예측의 재집계와 새 모델 학습도 구분한다. 현행 제도 공지의 재조회는 접근 차단으로 확인하지 못했다.
