"""Screen, train, freeze, evaluate, save and reload individual plant models.
Run from project/: .venv/Scripts/python -X utf8 -B ../tools/multi_plant_models/run.py
"""
import os
os.environ.setdefault("TF_ENABLE_ONEDNN_OPTS", "0")
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
os.environ.setdefault("TF_NUM_INTRAOP_THREADS", "2")
os.environ.setdefault("TF_NUM_INTEROP_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "2")
import argparse
import hashlib
import importlib.metadata
import json
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

if "--plant" in sys.argv:
    import tensorflow as tf  # Must precede numpy on this Windows host.
import numpy as np
import pandas as pd
from bundle import features, request_frame, Bundle

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "datasets/multi_plant"
DEFAULT_OUT = "docs/proposal/evidence/multi_plant_models_20261007"
SEMANTICS = "Volume[d] = observed ASOS GSR[d-1]; target T sees GSR[T-2]"


def dump(path, value):
    path = Path(path)
    temporary = path.with_name(path.name+".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False,
                                    default=str), encoding="utf-8")
    os.replace(temporary,path)


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat()


def metric(y, pred):
    pred = np.maximum(np.asarray(pred), 0)
    assert y.shape == pred.shape and np.isfinite(pred).all() and y.sum() > 0
    return {"rmse_kwh": float(np.sqrt(np.mean((pred-y)**2))),
            "mae_kwh": float(np.mean(np.abs(pred-y))),
            "wape_pct": float(100*np.abs(pred-y).sum()/y.sum()), "n": len(y)}


def screen(out):
    sources = [Path(__file__).resolve(), Path(__file__).with_name("bundle.py").resolve(),
               ROOT/"project/serving_app/lstm_model.py", ROOT/"project/data/features.py"]
    hashes = {str(p.relative_to(ROOT)):sha(p) for p in sources}
    dump(out/"training_code_hashes.json",hashes)
    for source in sources:
        target = out/"source_snapshot"/source.relative_to(ROOT)
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(source,target)
    (out/"requirements-freeze.txt").write_text(subprocess.check_output(
        [sys.executable,"-m","pip","freeze"],text=True,encoding="utf-8"),encoding="utf-8")
    catalog = read(DATA/"catalog.json")
    admitted, excluded = [], []
    for plant in catalog["plants"]:
        options = [u for u in plant.get("uploads", []) if u["rows"] >= 1115 and u["end"] >= "2025-01-01"]
        if not options:
            excluded.append({"plant_id": plant["plant_id"], "name": plant["name"],
                             "reason": "upstream_quality_review" if plant["status"] != "upload_ready" else "no_recent_contiguous_1115_day_segment",
                             "available_segments": plant.get("uploads", [])})
            continue
        upload = max(options, key=lambda u: (u["end"], u["rows"]))
        try:
            path = DATA/upload["file"]
            assert sha(path) == upload["sha256"], "catalog hash mismatch"
            df = pd.read_csv(path, parse_dates=["Date"])
            assert df.Date.is_unique and df.Date.diff().dropna().eq(pd.Timedelta(days=1)).all(), "calendar gaps"
            assert np.isfinite(df[["Close", "Volume"]]).all().all(), "nonfinite"
            assert df[["Close", "Volume"]].ge(0).all().all(), "negative inputs"
            daily = pd.read_csv(DATA/plant["daily_file"], parse_dates=["date"]).set_index("date")
            matched = daily.loc[df.Date]
            assert matched.generation_valid.eq(1).all(), "invalid generation"
            assert np.allclose(df.Close, matched.gen_kwh, rtol=0, atol=1e-6), "generation mismatch"
            assert np.allclose(df.Volume, matched.gsr_lag1_mj_m2, rtol=0, atol=1e-6), "lag1 mismatch"
            previous = daily.reindex(df.Date-pd.Timedelta(days=1)).gsr_mj_m2.to_numpy()
            mask = np.isfinite(previous)
            assert np.allclose(df.Volume.to_numpy()[mask], previous[mask], rtol=0, atol=1e-6), "calendar lag mismatch"
            # Fixed time horizon prevents long-lived sites dominating runtime/age.
            df = df.tail(1480)
            assert df.Close.eq(0).mean() <= .25 and df.Close.nunique() > 10, "degenerate generation"
            assert df.Volume.nunique() > 10, "degenerate weather"
            plant = dict(plant, selected_upload=upload, retained_rows=len(df),
                         retained_start=str(df.Date.iloc[0].date()), retained_end=str(df.Date.iloc[-1].date()),
                         daily_sha256=sha(DATA/plant["daily_file"]),
                         retained_zero_fraction=float(df.Close.eq(0).mean()))
            admitted.append(plant)
        except Exception as exc:
            excluded.append({"plant_id": plant["plant_id"], "name": plant["name"], "reason": str(exc)})
    dump(out/"screening.json", {"created_utc": now(), "admitted": admitted, "excluded": excluded,
                               "upstream_exclusions": {"15043390": "monthly_only", "15043397": "monthly_only", "15156688": "unverified_meter_units"}})
    dump(out/"protocol.json", {"created_utc": now(), "catalog_sha256": sha(DATA/"catalog.json"),
         "weather_semantics": SEMANTICS, "sequence_days": 20,
         "screening": "Latest segment with >=1115 contiguous rows and end >=2025-01-01; use last <=1480 rows. No gap joining, imputation or post-test error exclusions.",
         "splits": "Chronological: final365 test, preceding180 validation, rest training (>=550 targets).",
         "evaluation": "Rolling next-day with actual history through T-1, fixed weights during test; no target-day observed weather.",
         "lstm": "Teaching architecture (20,2), seed42, Adam .001, 120 full epochs; best validation-loss epoch then refit train+validation for that fixed count.",
         "xgb": "depth2/3/5 x learning_rate .03/.08, 800 rounds max, patience40; selected on validation",
         "prophet": "cps .01/.05/.2, yearly Fourier5, observed GSR T-2/lag1/mean7 regressors",
         "ensembles": "Validation-only simplex grid .1; Ensemble unrestricted, LSTM_Main_Ensemble requires LSTM>=.5.",
         "selection": "validation RMSE including Persistence/Mean7/Seasonal7; no forced ML winner or Production promotion",
         "limitations": ["Single seed per site screening; less tuning than previous 3-seed Hadong forecast experiment",
                          "Lagged observed weather differs from previous forecast-based Hadong experiment",
                          "Regional ASOS proxy, finalized historical observations; historical revision availability not reconstructed",
                          "Evaluation-fit artifacts end before test; not refit on all history or a live AIOps deployment",
                          "43 eligible-format units are not 43 distinct sites; capacities/units retain source caveats",
                          "Different feature engineering, same causal information; no fault labels inferred from zero generation"]})
    dump(out/"environment.json", {"python": sys.version, "packages": {k: importlib.metadata.version(k) for k in ["numpy", "pandas", "tensorflow", "keras", "xgboost", "prophet"]}})
    return admitted


def train(out, plant_id):
    from tensorflow import keras
    from xgboost import XGBRegressor
    from prophet import Prophet
    from prophet.serialize import model_to_json
    tf.config.threading.set_intra_op_parallelism_threads(2)
    tf.config.threading.set_inter_op_parallelism_threads(1)
    tf.config.experimental.enable_op_determinism()
    sys.path.insert(0, str(ROOT/"project"))
    from serving_app.lstm_model import build_model
    plant = next(p for p in read(out/"screening.json")["admitted"] if p["plant_id"] == plant_id)
    dest = out/"plants"/plant_id
    dest.mkdir(parents=True, exist_ok=True)
    modeldir = dest/"models"
    modeldir.mkdir(exist_ok=True)
    source = DATA/plant["selected_upload"]["file"]
    assert sha(source) == plant["selected_upload"]["sha256"]
    assert sha(DATA/plant["daily_file"]) == plant["daily_sha256"]
    df = pd.read_csv(source, parse_dates=["Date"]).tail(1480).reset_index(drop=True)
    a = df[["Close", "Volume"]].to_numpy()
    w = np.array([a[t-20:t] for t in range(20, len(df))])
    y = a[20:, 0]
    dates = pd.DatetimeIndex(df.Date.iloc[20:])
    x, p = features(w, dates)
    n = len(y)
    tr, va, te = np.arange(n-545), np.arange(n-545,n-365), np.arange(n-365,n)
    fitix = np.r_[tr,va]
    def split(ix):
        return {"first": str(dates[ix[0]].date()), "last": str(dates[ix[-1]].date()), "n": len(ix)}
    splits = {k: split(ix) for k,ix in [("train",tr),("validation",va),("test",te)]}
    pd.DataFrame({"date": dates, "split": ["train"]*len(tr)+["validation"]*len(va)+["test"]*len(te)}).to_csv(dest/"split_manifest.csv", index=False)
    val = {"Persistence": w[va,-1,0], "Mean7": w[va,-7:,0].mean(axis=1), "Seasonal7": w[va,-7,0]}
    test = {"Persistence": w[te,-1,0], "Mean7": w[te,-7:,0].mean(axis=1), "Seasonal7": w[te,-7,0]}
    searches = {"XGBoost": [], "Prophet": []}
    bestx = None
    for depth in [2,3,5]:
        for lr in [.03,.08]:
            cfg = dict(max_depth=depth, learning_rate=lr, min_child_weight=5, reg_lambda=5., subsample=.9,
                       colsample_bytree=.9, objective="reg:squarederror", tree_method="hist", n_jobs=2, random_state=42)
            m = XGBRegressor(**cfg, n_estimators=800, early_stopping_rounds=40)
            m.fit(x.iloc[tr], y[tr], eval_set=[(x.iloc[va], y[va])], verbose=False)
            pred = np.maximum(m.predict(x.iloc[va]),0)
            row = {"config": cfg, "rounds": int(m.best_iteration+1), **metric(y[va], pred)}
            searches["XGBoost"].append(row)
            if bestx is None or row["rmse_kwh"] < bestx["rmse_kwh"]:
                bestx, val["XGBoost"] = row, pred
    def fit_prophet(cps, ix, target):
        m = Prophet(changepoint_prior_scale=cps, yearly_seasonality=5, weekly_seasonality=False,
                    daily_seasonality=False, seasonality_prior_scale=1., uncertainty_samples=0)
        for reg in ["observed_gsr_t_minus_2", "lag1", "mean7"]:
            m.add_regressor(reg, prior_scale=1., standardize=True)
        m.fit(p.iloc[ix].assign(y=y[ix]), seed=42)
        return m, np.maximum(m.predict(p.iloc[target]).yhat.to_numpy(),0)
    bestp = None
    for cps in [.01,.05,.2]:
        m, pred = fit_prophet(cps, tr, va)
        row = {"cps": cps, **metric(y[va], pred)}
        searches["Prophet"].append(row)
        if bestp is None or row["rmse_kwh"] < bestp["rmse_kwh"]:
            bestp, val["Prophet"] = row, pred
    def fit_lstm(ix, target, epochs, validation):
        keras.backend.clear_session()
        keras.utils.set_random_seed(42)
        last_row = int(ix[-1]+20)
        lo = np.array([a[:last_row+1,0].min(), a[:last_row,1].min()])
        ranges = np.array([np.ptp(a[:last_row+1,0]), np.ptp(a[:last_row,1])])
        assert (ranges > 0).all()
        xx = ((w-lo)/ranges).astype("float32")
        yy = ((y-lo[0])/ranges[0]).astype("float32")
        m = build_model()
        callbacks = [keras.callbacks.EarlyStopping(patience=120,restore_best_weights=True)] if validation else []
        class Progress(keras.callbacks.Callback):
            def on_epoch_end(self, epoch, logs=None):
                if (epoch+1)%20 == 0:
                    print(plant_id, "validation" if validation else "refit", epoch+1, logs, flush=True)
        h = m.fit(xx[ix], yy[ix], validation_data=(xx[target],yy[target]) if validation else None,
                  epochs=epochs, batch_size=32, shuffle=False, callbacks=callbacks+[Progress()], verbose=0)
        pred = np.maximum(m.predict(xx[target],verbose=0).ravel()*ranges[0]+lo[0],0)
        scaler = {"min": lo.tolist(), "range": ranges.tolist(), "last_generation_date": str(df.Date.iloc[last_row].date()),
                  "last_weather_row": str(df.Date.iloc[last_row-1].date())}
        return m, pred, scaler, h.history
    m, val["LSTM"], _, hist = fit_lstm(tr, va, 120, True)
    epochs = int(np.argmin(hist["val_loss"])+1)
    dump(dest/"validation_lstm_history.json",hist)
    mat = np.column_stack([val[k] for k in ["LSTM","XGBoost","Prophet"]])
    grid = [[i/10,j/10,(10-i-j)/10] for i in range(11) for j in range(11-i)]
    weights = {}
    for name, candidates in [("Ensemble",grid),("LSTM_Main_Ensemble",[g for g in grid if g[0]>=.5])]:
        weights[name] = min(candidates, key=lambda g: metric(y[va],mat@g)["rmse_kwh"])
        val[name] = mat@weights[name]
    val_scores = {k: metric(y[va],v) for k,v in val.items()}
    selected = min(val_scores, key=lambda k: val_scores[k]["rmse_kwh"])
    frozen = {"frozen_utc": now(), "test_evaluated": False, "selected_by_validation": selected,
              "ensemble_weights": weights, "xgb": bestx, "prophet": bestp, "lstm_epochs": epochs,
              "seed": 42, "validation_metrics": val_scores, "searches": searches}
    dump(dest/"frozen_selection.json", frozen)
    pd.DataFrame({"date": dates[va], "actual_kwh": y[va], **val}).to_csv(dest/"validation_predictions.csv",index=False)
    # No hyperparameter or ensemble selection below this point.
    m = XGBRegressor(**bestx["config"], n_estimators=bestx["rounds"])
    m.fit(x.iloc[fitix],y[fitix]); test["XGBoost"] = np.maximum(m.predict(x.iloc[te]),0)
    m.save_model(modeldir/"xgboost.ubj")
    m, test["Prophet"] = fit_prophet(bestp["cps"],fitix,te)
    (modeldir/"prophet.json").write_text(model_to_json(m),encoding="utf-8")
    m, test["LSTM"], scaler, hist = fit_lstm(fitix,te,epochs,False)
    m.save(modeldir/"lstm.keras")
    dump(dest/"refit_lstm_history.json",hist)
    mat = np.column_stack([test[k] for k in ["LSTM","XGBoost","Prophet"]])
    for name, weight in weights.items():
        test[name] = mat@weight
    scores = {k: metric(y[te],pred) for k,pred in test.items()}
    pd.DataFrame({"date":dates[te],"actual_kwh":y[te],**test}).to_csv(dest/"test_predictions.csv",index=False)
    metadata = {"plant_id":plant_id,"name":plant["name"],"unit":plant["unit"],"capacity_kw":plant["capacity_kw"],
                "weather_semantics":SEMANTICS,"weather_mapping":plant["weather_mapping"],"source_sha256":sha(source),
                "source":str(source.relative_to(ROOT)),"unit_basis":plant["unit_basis"],"splits":splits,
                "trained_through":splits["validation"]["last"],"scaler":scaler,"ensemble_weights":weights,
                "weights_order":["LSTM","XGBoost","Prophet"],"selected_by_validation":selected,
                "validation_metrics":val_scores,"test_metrics":scores,"lstm_seed":42,"lstm_epochs":epochs,
                "artifact_role":"evaluation_candidate_not_production","feature_columns":list(x.columns),
                "postprocess":"max(prediction,0)","created_utc":now()}
    dump(modeldir/"metadata.json",metadata)
    dump(modeldir/"scaler.json",scaler)
    # Reconstruct predictions from serialized weights and saved scaler in fresh objects.
    frame = request_frame(w[te],dates[te])
    reload_checks = {}
    for kind in ["LSTM","XGBoost","Prophet","Ensemble","LSTM_Main_Ensemble"]:
        loaded = Bundle(modeldir,kind).predict(frame).prediction_kwh.to_numpy()
        np.testing.assert_allclose(loaded,test[kind],rtol=1e-6,atol=1e-3)
        reload_checks[kind] = float(np.max(np.abs(loaded-test[kind])))
    frame.iloc[:3].to_csv(dest/"input_example.csv",index=False)
    dump(dest/"reload_check.json",{"passed":True,"days":len(te),"max_abs_error_kwh":reload_checks})
    hashes = {f.name:sha(f) for f in modeldir.iterdir() if f.is_file()}
    dump(dest/"artifact_hashes.json",hashes)
    dump(dest/"result.json",{"plant_id":plant_id,"name":plant["name"],"unit":plant["unit"],"completed_utc":now(),
                             "selected_by_validation":selected,"splits":splits,"test_metrics":scores,
                             "validation_metrics":val_scores,"reload_passed":True,"artifact_hashes":hashes})
    print("COMPLETE",plant_id,selected,scores[selected],flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out",default=DEFAULT_OUT)
    ap.add_argument("--plant")
    ap.add_argument("--workers",type=int,default=2)
    ap.add_argument("--screen-only",action="store_true")
    args = ap.parse_args()
    out = ROOT/args.out
    out.mkdir(parents=True,exist_ok=True)
    (out/".gitignore").write_text("**/models/\n*.log\n**/*.log\nmlflow/\n",encoding="utf-8")
    if args.plant:
        train(out,args.plant)
        return
    if (out/"screening.json").exists():
        admitted = read(out/"screening.json")["admitted"]
    else:
        admitted = screen(out)
    print("ADMITTED",len(admitted),"EXCLUDED",len(read(out/"screening.json")["excluded"]),flush=True)
    if args.screen_only:
        return
    expected_code = read(out/"training_code_hashes.json")
    changed_code = [rel for rel,expected in expected_code.items() if sha(ROOT/rel)!=expected]
    assert not changed_code, f"Code differs from this run's snapshot; use a new --out: {changed_code}"
    def worker(plant):
        pid = plant["plant_id"]
        if (out/"plants"/pid/"result.json").exists():
            return pid,0
        with (out/f"{pid}.log").open("w",encoding="utf-8") as fp:
            r = subprocess.run([sys.executable,"-X","utf8","-B",str(Path(__file__).resolve()),"--out",args.out,"--plant",pid],
                               stdout=fp,stderr=subprocess.STDOUT,cwd=ROOT/"project")
        return pid,r.returncode
    status = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(worker,p) for p in admitted]
        for future in as_completed(futures):
            pid,code = future.result()
            status.append({"plant_id":pid,"exit_code":code})
            dump(out/"execution_status.json",status)
            print(now(),"DONE",len(status),"/",len(admitted),pid,"exit",code,flush=True)
    if any(s["exit_code"] for s in status):
        raise SystemExit("Some plant jobs failed; inspect per-plant logs, then resume")
    changed_code = [rel for rel,expected in expected_code.items() if sha(ROOT/rel)!=expected]
    dump(out/"training_code_integrity_at_completion.json",
         {"passed":not changed_code,"changed_files":changed_code,"checked_files":len(expected_code)})
    assert not changed_code, f"Training sources changed during the run: {changed_code}"


if __name__ == "__main__":
    main()
