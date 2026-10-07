# 여러 발전소 데이터 만들기

저장소의 `project/`에서 실행한다. Python 3.11, numpy, pandas를 사용하며 TensorFlow·API 키는 필요 없다. 기존 앱의 로더와 시퀀스 함수는 마지막 검증에서 직접 import한다.

```powershell
python ../tools/build_multi_plant/fetch_sources.py
python ../tools/build_multi_plant/prepare_weather.py --asos-dir 'ASOS_2013.csv부터 ASOS_2025.csv가 있는 폴더'
python ../tools/build_multi_plant/build.py
python ../tools/build_multi_plant/verify.py
```

`fetch_sources.py`는 공공데이터포털 공식 상세 페이지의 구조화 메타데이터에서 실제 CSV URL을 찾아 내려받는다. 이미 받은 원본은 SHA-256을 확인하고 재사용한다. 의도적으로 최신 원본을 새로 받을 때만 `--refresh`를 사용한다. 내려받기 오류는 `sources.json`에 기록한다.

`prepare_weather.py`는 ASOS 원본을 읽기만 한다. 필요한 관측소와 7개 열을 추려 기존 하동 결합 파일과 먼저 대조한다. 하나라도 다르면 추출 CSV를 새로 저장하지 않고 중단한다. 재현에 필요한 파일명·해시·크기는 남기되 사용자 컴퓨터의 절대 경로는 결과에 넣지 않는다.

`config.py`는 출처 ID별 지역, ASOS 연결, 공식 사양의 정확한 발전소명을 지정한다. 연결이 불명확한 용량은 비워 둔다. 지도상 최단거리나 모델 성능을 최적화한 관측소 선택은 아니다. 변경 시 기상 추출부터 다시 실행하고 기존 결과와 비교한다.

`build.py`는 호기별 분석 자료와 연속된 업로드 구간을 만든다. 품질 기준과 모든 제외 사유는 생성되는 `catalog.json`에 남긴다. 업로드 파일 이름에는 출처 ID·호기·시차·기간이 들어간다. 기준/기간 변경 후 이전 업로드 파일이 남아 있으면 `verify.py`가 manifest에 없는 파일을 발견해 실패한다. 기존 결과를 별도로 보존하고 새 출력 디렉터리를 정리한 뒤 재생성한다.

`verify.py`는 원본 발전량과 ASOS의 정확한 전날 관측값을 다시 조회해 모든 업로드 행과 대조한다. 실제 `load_rows`, `HAICScaler`, `build_sequences`로 입력 모양과 다음 날 정답도 검사한다. 검증용 스케일러는 앞 80% 행으로만 맞추고 디스크에 저장하지 않는다. 모델 학습이나 앱의 Production 모델을 변경하지 않는다.

재생성에는 저장소 안의 원문 발전 실적과 `weather/asos_selected_daily.csv`가 있으므로 `build.py`, `verify.py`만 실행해도 된다. 원래 ASOS 전체와 다시 비교할 때만 `--asos-dir`이 필요하다.
