"""MLflow 레지스트리에서 "승격"과 "되돌리기"가 실제로 어떻게 동작하는지 확인한다.

앱의 재학습 경로를 실행하는 것이 아니다. 앱이 승격할 때 부르는 두 호출
(serving_app/train_and_register.py 의 register_model, transition_model_version_stage)을
같은 인자로 직접 불러, 그 뒤 레지스트리의 상태와 "models:/<이름>/Production" 이 가리키는 버전을 본다.

  1. 지금 상태
  2. 이미 있는 실행(run)의 모델을 새 버전으로 등록하고 Production 으로 올린 뒤의 상태
  3. 새 버전을 Archived 로 내린 뒤(사람이 하는 되돌리기)의 상태

검증용 사본의 레지스트리에서만 돌린다. 새 버전은 3번에서 Archived 로 내려가므로 Production 은 처음과 같아진다.

실행 (검증용 사본의 project/ 에서):
    python <저장소>/tools/proposal/registry_semantics.py --out <저장소>/docs/proposal/evidence/registry/registry_semantics.json
"""
import argparse
import datetime as dt
import json
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

import mlflow  # noqa: E402
from mlflow.tracking import MlflowClient  # noqa: E402

p = argparse.ArgumentParser()
p.add_argument("--out", type=Path, required=True)
a = p.parse_args()

MODEL_NAME = "HAIC_Predictor"
URI = f"models:/{MODEL_NAME}/Production"
c = MlflowClient()


def snapshot(label):
    versions = sorted(
        ({"version": int(mv.version), "stage": mv.current_stage, "run_id": (mv.run_id or "")[:8]}
         for mv in c.search_model_versions(f"name='{MODEL_NAME}'")),
        key=lambda v: v["version"],
    )
    latest = c.get_latest_versions(MODEL_NAME, stages=["Production"])      # "models:/이름/Production" 을 풀 때 MLflow 가 쓰는 조회
    return {
        "step": label,
        "versions": versions,
        "production_versions": [v["version"] for v in versions if v["stage"] == "Production"],
        "uri": URI,
        "uri_resolves_to_version": int(latest[0].version) if latest else None,
    }


steps = [snapshot("1. 처음 상태")]
prod = steps[0]["production_versions"]
assert prod, "Production 버전이 없다. train_and_register.py 가 게이트를 통과한 적이 있어야 한다."
run_id = next(mv.run_id for mv in c.search_model_versions(f"name='{MODEL_NAME}'") if int(mv.version) == prod[0])

new = mlflow.register_model(f"runs:/{run_id}/model", MODEL_NAME)                       # train_and_register.py:61 과 같은 호출
c.transition_model_version_stage(name=MODEL_NAME, version=new.version, stage="Production")   # train_and_register.py:62 와 같은 호출
steps.append(snapshot(f"2. v{new.version} 을 등록하고 Production 으로 올린 뒤 (앱의 승격과 같은 두 호출)"))

c.transition_model_version_stage(name=MODEL_NAME, version=new.version, stage="Archived")
steps.append(snapshot(f"3. v{new.version} 을 Archived 로 내린 뒤 (사람이 하는 되돌리기)"))

result = {
    "checked_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
    "what": "레지스트리의 승격과 되돌리기 동작. 앱의 재학습 경로를 실행한 결과가 아니다",
    "mlflow_version": mlflow.__version__,
    "source_run_of_new_version": run_id[:8],
    "steps": steps,
}
a.out.parent.mkdir(parents=True, exist_ok=True)
a.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps(result, ensure_ascii=False, indent=2))
