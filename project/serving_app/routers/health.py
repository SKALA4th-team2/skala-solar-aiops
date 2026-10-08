"""Day1: 헬스체크 엔드포인트."""
from fastapi import APIRouter

from serving_app import model_loader
from serving_app import runtime as rt
from fastapi import HTTPException
from serving_app.schemas import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health(plant_id: str = rt.DEFAULT_PLANT):
    try:rt.plant(plant_id)
    except KeyError:raise HTTPException(404,'등록되지 않은 발전소입니다.') from None
    model = model_loader._models.get((str(rt.root()),plant_id))
    if model is None and plant_id==rt.DEFAULT_PLANT:model=model_loader._model_cache
    with rt.db() as conn:heartbeat=conn.execute("SELECT updated_at FROM heartbeat WHERE name='worker'").fetchone()
    model_loaded = model is not None
    return {
        "status": "ok",
        'plant_id':plant_id,'worker_updated_at':heartbeat['updated_at'] if heartbeat else None,
        'execution_unit':__import__('os').getenv('EXECUTION_UNIT','local'),
        "model_loaded": model_loaded,
        "model_version": model.version if model_loaded else None,
        "model_source": model.source if model_loaded else None,
        "loading_mode": _current_loading_mode(),
    }


def _current_loading_mode() -> str:
    import os

    return os.getenv("LOADING_MODE", "lazy")
