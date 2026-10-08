"""Solar RMSE warning only; PI and facility checks govern retraining."""
from serving_app.monitoring.policy import WINDOW_SIZE, assess, metrics
def compute_rmse(recent_predictions):
    if not recent_predictions:return 0.
    return metrics([r['actual'] for r in recent_predictions],[r['predicted'] for r in recent_predictions])['rmse_kwh']
def is_drift(recent_predictions,*,reference_rmse=None):
    return reference_rmse is not None and len(recent_predictions)>=WINDOW_SIZE and compute_rmse(recent_predictions[-WINDOW_SIZE:])>reference_rmse*1.5
