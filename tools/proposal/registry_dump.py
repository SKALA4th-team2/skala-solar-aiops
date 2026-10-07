"""MLflow 에 기록된 실행과 모델 레지스트리의 상태, 그리고 스케일러 파일의 내용을 그대로 적어 낸다.

"게이트를 통과했는가", "어느 버전이 Production 인가", "스케일러가 어느 자료로 맞춰졌는가"를
응답 문자열이 아니라 저장된 기록으로 확인하려는 도구다. 읽기만 한다.

실행 (서빙 앱의 작업 디렉터리, 곧 project/ 에서):
    python ../tools/proposal/registry_dump.py --label after-haic --out ../docs/proposal/evidence/registry
"""
import argparse
import datetime as dt
import json
import os
import pickle
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument("--label", required=True)
p.add_argument("--out", type=Path, required=True)
a = p.parse_args()
a.out.mkdir(parents=True, exist_ok=True)

MODEL_NAME = "HAIC_Predictor"
SCALER_PATH = "serving_app/models/scaler.pkl"
state = {"label": a.label, "dumped_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
         "cwd_name": Path.cwd().name, "mlflow_db_exists": os.path.exists("mlflow.db")}

if os.path.exists(SCALER_PATH):
    with open(SCALER_PATH, "rb") as f:
        state["scaler"] = {k: float(v) for k, v in pickle.load(f).items()}
else:
    state["scaler"] = None

state["model_files"] = sorted(x.name for x in Path("serving_app/models").iterdir())
state["uploads"] = sorted(x.name for x in Path("data/uploads").iterdir()) if os.path.isdir("data/uploads") else []

if state["mlflow_db_exists"]:
    import mlflow
    from mlflow.tracking import MlflowClient

    # 개인 PC 의 절대 경로가 증빙에 남지 않게, 작업 디렉터리 앞부분을 짧은 표기로 바꿔 적는다.
    state["tracking_uri"] = mlflow.get_tracking_uri().replace(str(Path.cwd()), "(project)")
    c = MlflowClient()
    runs = []
    for exp in c.search_experiments():
        for r in c.search_runs([exp.experiment_id], order_by=["attributes.start_time ASC"]):
            runs.append({
                "run_id": r.info.run_id[:8],
                "run_name": r.info.run_name,
                "status": r.info.status,
                "started": dt.datetime.fromtimestamp(r.info.start_time / 1000).astimezone().isoformat(timespec="seconds"),
                "params": dict(r.data.params),
                "metrics": {k: round(v, 4) for k, v in r.data.metrics.items()},
            })
    state["runs"] = runs
    versions = []
    for rm in c.search_registered_models():
        for mv in c.search_model_versions(f"name='{rm.name}'"):
            versions.append({"name": mv.name, "version": int(mv.version), "stage": mv.current_stage, "run_id": (mv.run_id or "")[:8]})
    state["model_versions"] = sorted(versions, key=lambda v: v["version"])
    state["production_versions"] = [v["version"] for v in versions if v["name"] == MODEL_NAME and v["stage"] == "Production"]
else:
    state["runs"] = []
    state["model_versions"] = []
    state["production_versions"] = []

out = a.out / f"registry_{a.label}.json"
out.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps(state, ensure_ascii=False, indent=2))
