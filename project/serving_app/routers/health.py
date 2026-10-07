"""Day1: 헬스체크 엔드포인트."""
from fastapi import APIRouter

from serving_app import model_loader
from serving_app.schemas import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health():
    model = model_loader._model_cache
    model_loaded = model is not None
    return {
        "status": "ok",
        "model_loaded": model_loaded,
        "model_version": model.version if model_loaded else None,
        "loading_mode": _current_loading_mode(),
    }


def _current_loading_mode() -> str:
    import os

    return os.getenv("LOADING_MODE", "lazy")
