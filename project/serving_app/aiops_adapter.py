"""FastAPI ↔ AIOps 연결 지점. 판정·학습 정책은 AIOps 담당자가 제공한다.

AIOps 담당자는 앱 시작 시 configure_evaluator(callback)을 호출한다.
callback(rows=..., predictions=..., model_version=...) -> DriftCheck | dict
rows는 요청의 전체 연속 행(date, close, volume, expected), predictions는
각 대상일의 date/predicted/actual/expected다. 관측 기반 expected는 감시에만 쓴다.
"""
from collections.abc import Callable

from serving_app.schemas import DriftCheck

_evaluator: Callable | None = None


def configure_evaluator(evaluator: Callable | None) -> None:
    """프로세스 시작 시 판정기를 연결한다. None은 미연결 상태로 되돌린다."""
    global _evaluator
    _evaluator = evaluator


def evaluate_batch(*, rows: list[dict], predictions: list[dict], model_version: str, plant_id: str = 'hadong-sewage') -> DriftCheck:
    if _evaluator is None:
        return DriftCheck(status='skipped', reason='aiops_not_configured', model_version=model_version)
    import inspect
    arguments=dict(rows=rows,predictions=predictions,model_version=model_version)
    if 'plant_id' in inspect.signature(_evaluator).parameters:
        arguments['plant_id']=plant_id
    elif plant_id!='hadong-sewage':
        raise ValueError('Evaluator must accept plant_id for multiple plants')
    return DriftCheck.model_validate(_evaluator(**arguments))
