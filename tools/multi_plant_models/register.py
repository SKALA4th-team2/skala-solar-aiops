"""Register versioned, reloadable offline candidates in an isolated local SQLite store."""
import os
os.environ.setdefault("TF_ENABLE_ONEDNN_OPTS", "0")
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
os.environ.setdefault("MLFLOW_DISABLE_AGENT_HINT", "1")
os.environ.setdefault("MLFLOW_ENABLE_ASYNC_LOGGING", "false")
import tensorflow as tf  # Before NumPy/MLflow on this Windows host.
tf.config.threading.set_intra_op_parallelism_threads(2)
tf.config.threading.set_inter_op_parallelism_threads(1)
import argparse
import importlib.metadata
import json
from pathlib import Path
import sys
import numpy as np
import pandas as pd
import mlflow
from mlflow.models import infer_signature
from mlflow.tracking import MlflowClient
from bundle import Bundle
from run import ROOT, DEFAULT_OUT, read, dump, sha, now

KINDS = ["LSTM", "XGBoost", "Prophet", "Ensemble", "LSTM_Main_Ensemble"]


class PlantModel(mlflow.pyfunc.PythonModel):
    def __init__(self, kind):
        self.kind = kind

    def load_context(self, context):
        from bundle import Bundle
        self.bundle = Bundle(context.artifacts["bundle"], self.kind)

    def predict(self, context, model_input, params=None):
        return self.bundle.predict(model_input)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out",default=DEFAULT_OUT)
    ap.add_argument("--plant")
    args = ap.parse_args()
    out = ROOT/args.out
    store = out/"mlflow"
    store.mkdir(exist_ok=True)
    tracking = "sqlite:///" + (store/"mlflow.db").as_posix()
    mlflow.set_tracking_uri(tracking)
    client = MlflowClient()
    expname = "solar-multi-plant-asos-lag1"
    exp = client.get_experiment_by_name(expname)
    expid = exp.experiment_id if exp else client.create_experiment(expname, artifact_location=(store/"artifacts").as_uri())
    requirements = [f"{k}=={importlib.metadata.version(k)}" for k in ["numpy", "pandas", "tensorflow", "keras", "xgboost", "scikit-learn", "prophet", "cloudpickle"]]
    all_records = read(out/"registry_index.json")["models"] if (out/"registry_index.json").exists() else []
    resultfiles = sorted((out/"plants").glob("*/result.json"))
    if args.plant:
        resultfiles = [p for p in resultfiles if p.parent.name == args.plant]
        if not resultfiles:
            raise ValueError("Plant training must finish successfully before registration")
    for resultfile in resultfiles:
        dest = resultfile.parent
        result = read(resultfile)
        pid = result["plant_id"]
        for file, expected in result["artifact_hashes"].items():
            assert sha(dest/"models"/file) == expected, f"Artifact hash mismatch: {pid}/{file}"
        example = pd.read_csv(dest/"input_example.csv")
        expected = pd.read_csv(dest/"test_predictions.csv").iloc[:len(example)]
        for kind in KINDS:
            if any(r["plant_id"]==pid and r["kind"]==kind and r["metadata_sha256"]==sha(dest/"models/metadata.json") and r.get("pip_requirements")==requirements for r in all_records):
                continue
            name = f"Solar_{pid}_{kind}"
            with mlflow.start_run(experiment_id=expid,run_name=f"{pid}-{kind}") as run:
                mlflow.set_tags({"plant_id":pid,"plant_name":result["name"],"kind":kind,
                                 "artifact_role":"evaluation_candidate_not_production",
                                 "weather":"ASOS_observed_T_minus_2","seed":"42"})
                mlflow.log_params({"sequence_days":20,"selected_by_validation":result["selected_by_validation"],
                                   "trained_through":result["splits"]["validation"]["last"],"test_days":365,
                                   "source_sha256":read(dest/"models/metadata.json")["source_sha256"]})
                for split in ["validation","test"]:
                    mlflow.log_metrics({f"{split}_{k}":v for k,v in result[f"{split}_metrics"][kind].items() if k!="n"})
                for filename in ["result.json","frozen_selection.json","reload_check.json","artifact_hashes.json"]:
                    mlflow.log_artifact(str(dest/filename),artifact_path="evidence")
                output_example = pd.DataFrame({"prediction_kwh":expected[kind].to_numpy()})
                info = mlflow.pyfunc.log_model(name="model",python_model=PlantModel(kind),
                    artifacts={"bundle":str(dest/"models")},code_paths=[str(Path(__file__).parent/"bundle.py")],
                    signature=infer_signature(example,output_example),input_example=example,
                    pip_requirements=requirements,metadata={"plant_id":pid,"weather_semantics":"ASOS_lag1"})
                version = mlflow.register_model(info.model_uri,name)
                client.set_model_version_tag(name,version.version,"artifact_role","evaluation_candidate_not_production")
                client.set_registered_model_alias(name,"candidate",version.version)
                uri = f"models:/{name}/{version.version}"
                loaded = mlflow.pyfunc.load_model(uri)
                actual = loaded.predict(example).prediction_kwh.to_numpy()
                np.testing.assert_allclose(actual,expected[kind],rtol=1e-6,atol=1e-3)
                record = {"plant_id":pid,"kind":kind,"registered_name":name,"version":version.version,
                          "run_id":run.info.run_id,"model_uri":uri,"alias":"candidate",
                          "reload_passed":True,"max_abs_error_kwh":float(np.max(np.abs(actual-expected[kind]))),
                          "metadata_sha256":sha(dest/"models/metadata.json"),"registered_utc":now(),"pip_requirements":requirements}
                previous = [r for r in all_records if r["plant_id"]==pid and r["kind"]==kind]
                if previous:
                    historypath = out/"registry_history.json"
                    history = read(historypath) if historypath.exists() else []
                    history.extend(previous)
                    dump(historypath,history)
                    all_records = [r for r in all_records if not (r["plant_id"]==pid and r["kind"]==kind)]
                all_records.append(record)
                dump(out/"registry_index.json",{"tracking_uri":tracking,"experiment_id":expid,
                                                "models":all_records,"production_promoted":False})
                print("REGISTERED",name,version.version,flush=True)
                del loaded
                tf.keras.backend.clear_session()


if __name__ == "__main__":
    main()
