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

`t6t7_source_evidence.json`은 2026-10-07에 수동으로 대조한 전력시장 규칙·중개시장 규칙·2025년 시장통계의 URL, SHA-256, 페이지와 검토 내용을 보관한 기록이다. PDF 표는 당시 화면으로도 대조했다. 바이너리 원문은 이 폴더에 복제하지 않았다.

`t6t7_source_evidence.py`는 새 입력의 세 SHA-256이 이 기록과 모두 일치하는지만 확인한다. 하나라도 다르거나 파일을 읽지 못하면 실패하며 성공 JSON을 출력하지 않는다. 개정 문서의 내용이나 제도의 현재 상태를 새로 확인하는 도구가 아니다. 일치한 경우에만 `file_identity_check`에 이번 파일 대조 시각을, `recorded_manual_review`에 과거 검토 날짜·페이지·시각 확인 여부를 그대로 담는다. 두 결과를 구분해서 인용한다. 원문이 바뀌었으면 별도로 수동 검토해야 하며, 기존 기록의 해시만 바꿔 통과시키지 않는다.

Python 표준 라이브러리만 필요하다. 기존 `--broker-text` 옵션은 호환 목적으로 받지만 무시하며, HWP 원본의 해시 검사를 대신할 수 없다. 출력은 임시 파일로 저장하고 수동 검토 기록 JSON을 덮어쓰지 않는다.

```sh
python tools/verify/t6t7_source_evidence.py --rule RULE.pdf --broker BROKER.hwp --market MARKET.pdf > /tmp/t6t7-source-match.json
python -B -m unittest discover -s tools/verify -p 'test_t6t7_source_evidence.py' -v
```

`hadong_daily_full.csv`의 ASOS 열은 정제된 결합 자료다. 원 ASOS 연도별 관측·위성 전기간 응답·일부 예보 모델 예측·정비 준공기록이 없으므로 모든 원 연구를 재현했다는 뜻은 아니다. 저장된 예측의 재집계와 새 모델 학습도 구분한다. 현행 제도 공지의 재조회는 접근 차단으로 확인하지 못했다.
