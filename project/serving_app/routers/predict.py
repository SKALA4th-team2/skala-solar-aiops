"""태양광 단건·배치 예측. 감시·재학습 정책은 aiops_adapter로 분리한다."""
from datetime import timedelta
import math

from fastapi import APIRouter, HTTPException

from data.features import SEQ_LEN  # = 20
from serving_app import model_loader
from serving_app.schemas import PredictRequest, PredictResponse, BatchTestRequest, BatchTestResponse
from serving_app.aiops_adapter import evaluate_batch

router = APIRouter()


def get_ready_model():
    """모델 파일이 준비되지 않은 상태를 클라이언트가 구분할 수 있게 한다."""
    try:
        return model_loader.get_model()
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=503,
            detail="예측 모델 또는 스케일러가 준비되지 않았습니다. 모델 준비 후 다시 요청하세요.",
        ) from exc


@router.post("/predict", response_model=PredictResponse, responses={503: {"description": "모델 또는 스케일러 미준비"}})
def predict(req: PredictRequest):
    """연속 20일의 발전량과 다음 날 예보로 대상일의 발전량(kWh)을 예측한다."""
    model = get_ready_model()
    # 날짜는 API 검증용이다. 모델에는 학습 시와 같은 두 피처만 전달한다.
    sequence = [{"close": point.close, "volume": point.volume} for point in req.sequence]
    predicted_close = model.predict_one(sequence)
    if not math.isfinite(predicted_close):
        raise HTTPException(503, "모델이 유한한 예측값을 반환하지 않았습니다.")
    return PredictResponse(
        predicted_close=round(max(0.0, predicted_close), 2),
        target_date=req.sequence[-1].date + timedelta(days=1),
        model_version=model.version,
    )


@router.post("/predict/batch-test", response_model=BatchTestResponse, response_model_exclude_unset=True,
             responses={503: {"description": "모델 또는 스케일러 미준비, 비유한 모델 출력"}})
def batch_test(req: BatchTestRequest):
    """실제 예보로 배치 예측하고, 전체 행과 사후 기대 발전량을 AIOps 연결부에 전달한다."""
    model = get_ready_model()
    predictions = []
    records = []
    for i in range(len(req.prices) - SEQ_LEN):
        sequence = [
            {"close": req.prices[j], "volume": req.volumes[j]}
            for j in range(i, i + SEQ_LEN)
        ]
        value = model.predict_one(sequence)
        if not math.isfinite(value):
            raise HTTPException(503, "모델이 유한한 예측값을 반환하지 않았습니다.")
        pred = max(0.0, value)
        target = i + SEQ_LEN
        predictions.append(pred)
        records.append({
            "date": req.dates[target].isoformat(), "predicted": pred,
            "actual": req.prices[target], "expected": req.expected[target],
        })
    rows = [
        {"date": day.isoformat(), "close": close, "volume": volume, "expected": expected}
        for day, close, volume, expected in zip(req.dates, req.prices, req.volumes, req.expected)
    ]
    check = evaluate_batch(rows=rows, predictions=records, model_version=model.version)
    return BatchTestResponse(predictions=predictions, drift_check=check)
