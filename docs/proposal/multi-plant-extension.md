# 다개소 운영과 가상 합계

현재 구현은 발전소별 시간별 LSTM31개다. 각 개소에 모델·스케일러·버전·업로드·작업을 분리한다. 동일 이름의 서로 다른 호기는 plant_id와용량으로 구분한다. 모든 개소를 이어붙여 한 학습창으로 사용하지 않는다.

all-approved는31개 가상 포트폴리오다. 같은 대상24시간의 모든 입력이 있을 때만 complete=true와합계predictions를 반환한다. 빠진 개소가 있으면 predictions=null,partial_predictions와missing을 반환한다. 독립 평가의 공통8496시간에서 예측합과실적합으로 구한 RMSE는1044.7334kWh/시간이다. 개별RMSE를 합산하지 않았다.

설비용량 합계는22.914065MW이며 전력거래 제도 참여·계약·시장제출·정산 검증을 완료했다는 뜻이 아니다. [입력 계약](multi-plant-data-contract.md), [API](5-api-spec.md), [포트폴리오 평가](evidence/hourly_20261007/portfolio_quality.json)를 참조한다. 이전 확장 제안은 [보관 원문](archive/20261007-daily/)으로 분리했다.
