# 지역별 과거 예보 저장

`project/`에서 실행한다.

```powershell
.\.venv\Scripts\python.exe ..\tools\build_plant_forecasts\build.py
.\.venv\Scripts\python.exe ..\tools\build_plant_forecasts\verify.py
```

원본 캐시와 산출물은 `datasets/plant_forecasts/`에 저장한다. 스키마·출처·좌표의 한계·발표 시각의 한계는 `DATASET_README.md`에 정의하며 생성할 때 데이터 디렉터리로 복사한다. 실행 중 네트워크 오류나 요청 제한이 나면 완료된 캐시를 보존하며, 제한 해제 후 같은 명령으로 재개한다. 원본을 지우고 재실행하지 않는다.
