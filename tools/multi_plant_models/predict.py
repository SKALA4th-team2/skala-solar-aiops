"""Load one saved plant/version and predict using its recorded input contract.

Without --input, runs the saved historical 3-row example (not a live forecast).
"""
import os
os.environ.setdefault("TF_ENABLE_ONEDNN_OPTS", "0")
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
os.environ.setdefault("MLFLOW_DISABLE_AGENT_HINT", "1")
import tensorflow as tf
tf.config.threading.set_intra_op_parallelism_threads(2)
tf.config.threading.set_inter_op_parallelism_threads(1)
import argparse
import hashlib
import json
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out",default="docs/proposal/evidence/multi_plant_models_20261007")
    ap.add_argument("--plant",required=True)
    ap.add_argument("--kind",default="LSTM",choices=["LSTM","XGBoost","Prophet","Ensemble","LSTM_Main_Ensemble"])
    ap.add_argument("--input",help="CSV in input_example.csv layout; one chronological 20-day window per row")
    ap.add_argument("--registry",action="store_true")
    args = ap.parse_args()
    out = ROOT/args.out
    dest = out/"plants"/args.plant
    if not dest.is_dir() or dest.resolve().parent != (out/"plants").resolve():
        raise ValueError("Unknown plant ID")
    for file,expected in json.loads((dest/"artifact_hashes.json").read_text(encoding="utf-8")).items():
        assert hashlib.sha256((dest/"models"/file).read_bytes()).hexdigest()==expected
    frame = pd.read_csv(args.input or dest/"input_example.csv")
    if args.registry:
        import mlflow
        index = json.loads((out/"registry_index.json").read_text(encoding="utf-8"))
        # Resolve the local store relative to --out; old absolute URI remains provenance only.
        mlflow.set_tracking_uri("sqlite:///"+(out/"mlflow/mlflow.db").as_posix())
        record = next(r for r in index["models"] if r["plant_id"]==args.plant and r["kind"]==args.kind)
        uri = record["model_uri"]
        model = mlflow.pyfunc.load_model(uri)
    else:
        from bundle import Bundle
        model = Bundle(dest/"models",args.kind)
        uri = str(dest/"models")
    predictions = model.predict(frame).prediction_kwh.tolist()
    print(json.dumps({"plant_id":args.plant,"kind":args.kind,"source":uri,"historical_example":args.input is None,
                      "predictions":[{"target_date":str(d),"prediction_kwh":p} for d,p in zip(frame.target_date,predictions)]},
                     ensure_ascii=False,indent=2))


if __name__=="__main__":
    main()
