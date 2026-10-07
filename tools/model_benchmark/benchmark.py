"""Reproducible, offline Hadong next-day model comparison (no serving app edits).

Run from project/: .venv/Scripts/python -B ../tools/model_benchmark/benchmark.py
The final 365 target days are held out; preceding 180 days select all settings.
Daily rolling one-step predictions use actual history available before each target.
"""
from __future__ import annotations

import os
os.environ.setdefault("TF_ENABLE_ONEDNN_OPTS", "0")
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
os.environ.setdefault("TF_NUM_INTRAOP_THREADS", "4")
os.environ.setdefault("TF_NUM_INTEROP_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "4")
os.environ.setdefault("MPLBACKEND", "Agg")

import argparse
import hashlib
import importlib.metadata
import json
import platform
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

# This Windows TensorFlow build fails DLL initialization if NumPy is loaded first.
# Keep non-LSTM stages lightweight and initialize TensorFlow first in LSTM workers.
if "--stage" in sys.argv and sys.argv[sys.argv.index("--stage")+1] in ("lstm", "final_lstm"):
    import tensorflow as tf

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "datasets/hadong_upload_forecast_jma.csv"
SEEDS = [42, 43, 44]
SEQ = 20
CLIP = "All forecasts floored at zero, including validation and baselines."


def dump(path, obj):
    Path(path).write_text(json.dumps(obj, ensure_ascii=False, indent=2,
                                    allow_nan=False, default=str), encoding="utf-8")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def metric(y, p):
    y, p = np.asarray(y), np.maximum(np.asarray(p), 0)
    assert y.shape == p.shape and np.isfinite(p).all()
    return {"rmse_kwh": float(np.sqrt(np.mean((p-y)**2))),
            "mae_kwh": float(np.mean(np.abs(p-y))),
            "wape_pct": float(np.abs(p-y).sum()/y.sum()*100),
            "bias_pct": float((p-y).sum()/y.sum()*100), "n": len(y)}


def log(message):
    print(datetime.now(ZoneInfo("Asia/Seoul")).strftime("%H:%M:%S"), message, flush=True)


def data():
    df = pd.read_csv(SOURCE, parse_dates=["Date"])
    assert len(df) == 1337
    assert df.Date.is_unique and df.Date.is_monotonic_increasing
    assert df.Date.diff().dropna().eq(pd.Timedelta(days=1)).all()
    assert np.isfinite(df[["Close", "Volume"]]).all().all()
    assert df.Close.ge(0).all() and df.Volume.gt(0).all()
    # Check every target forecast against the original saved weather series.
    weather = pd.read_csv(ROOT / "datasets/raw/wx_prevruns_daily.csv").set_index("date")
    target_dates = (df.Date + pd.Timedelta(days=1)).dt.strftime("%Y-%m-%d")
    orig = weather.loc[target_dates, "shortwave_radiation_previous_day1"].to_numpy()
    assert np.allclose(df.Volume, orig, rtol=0, atol=1e-6)
    c, v = df.Close.to_numpy(), df.Volume.to_numpy()
    targets = np.arange(SEQ, len(df))
    windows = np.array([np.column_stack((c[t-SEQ:t], v[t-SEQ:t])) for t in targets])
    features, names = [], []
    for j in range(SEQ):
        names.extend([f"generation_lag_{SEQ-j}", f"forecast_for_target_minus_{SEQ-1-j}"])
    names += ["mean7", "std7", "mean20", "std20", "efficiency7", "rule_c",
              "year_sin", "year_cos"]
    bases = {"Persistence": [], "Mean7": [], "Mean20": [], "RuleC": []}
    for t, win in zip(targets, windows):
        eff = c[t-7:t].sum()/v[t-8:t-1].sum()
        rule = eff*v[t-1]
        day = df.Date.iloc[t].dayofyear
        features.append([*win.flatten(), c[t-7:t].mean(), c[t-7:t].std(),
                         c[t-20:t].mean(), c[t-20:t].std(), eff, rule,
                         np.sin(2*np.pi*day/365.25), np.cos(2*np.pi*day/365.25)])
        for key, value in zip(bases, [c[t-1], c[t-7:t].mean(), c[t-20:t].mean(), rule]):
            bases[key].append(value)
    x = pd.DataFrame(features, columns=names)
    y = c[targets]
    dates = df.Date.iloc[targets].reset_index(drop=True)
    p = pd.DataFrame({"ds": dates, "y": y, "irradiance": v[targets-1],
                      "lag1": c[targets-1], "mean7": x.mean7,
                      "efficiency7": x.efficiency7, "rule_c": x.rule_c})
    n = len(y)
    train = np.arange(n-545)
    val = np.arange(n-545, n-365)
    test = np.arange(n-365, n)
    return df, targets, windows, x, y, dates, p, train, val, test, bases


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="docs/proposal/evidence/model_benchmark_20261007")
    ap.add_argument("--stage", choices=["prepare", "xgb", "prophet", "lstm", "select",
                                        "final_xgb", "final_prophet", "final_lstm", "report", "all"],
                    default="all")
    args = ap.parse_args()
    out = ROOT / args.out
    out.mkdir(parents=True, exist_ok=True)
    (out/"models").mkdir(exist_ok=True)
    (out/".gitignore").write_text("models/\n*.log\n", encoding="utf-8")
    df, targets, windows, x, y, dates, p, tr, va, te, bases = data()
    split = {k: {"n": len(ix), "first_target": str(dates.iloc[ix[0]].date()),
                 "last_target": str(dates.iloc[ix[-1]].date())}
             for k, ix in [("train",tr),("validation",va),("test",te)]}
    log(f"stage={args.stage}; splits={split}")

    def savepred(name, stage, ix, pred):
        pred = np.maximum(np.asarray(pred).reshape(-1), 0)
        assert len(pred) == len(ix) and np.isfinite(pred).all()
        pd.DataFrame({"date": dates.iloc[ix].to_numpy(), "actual_kwh": y[ix],
                      "prediction_kwh": pred}).to_csv(out/f"{stage}_{name}.csv", index=False)
        return pred

    def getpred(name, stage):
        return pd.read_csv(out/f"{stage}_{name}.csv").prediction_kwh.to_numpy()

    def prepare():
        protected = [q for folder in ["project", "datasets"] for q in (ROOT/folder).rglob("*")
                     if q.is_file() and ".venv" not in q.parts and "__pycache__" not in q.parts
                     and "multi_plant" not in q.parts]
        dump(out/"input_hashes.json", {str(q.relative_to(ROOT)):sha(q) for q in protected})
        protocol = {"created_kst": datetime.now(ZoneInfo("Asia/Seoul")).isoformat(),
                    "source":str(SOURCE.relative_to(ROOT)), "source_sha256":sha(SOURCE),
                    "splits":split, "seeds":SEEDS, "sequence_days":SEQ,
                    "selection_metric":"validation RMSE kWh, no final-test tuning",
                    "evaluation":"Rolling one-day-ahead, actual observations through T-1; fixed model weights throughout each validation/test block",
                    "weather_alignment":"Volume[d] is forecast for d+1; target T uses Volume[T-1]. Checked all 1337 rows against saved raw forecast.",
                    "refit":"Select on validation, freeze settings/weights, refit on train+validation; scale only refit data; then evaluate 365-day test once",
                    "lstm":"Existing teaching architecture LSTM32 -> LSTM32 -> LSTM16 -> Dense16 -> Dense1; 3 seeds averaged, never choose best seed",
                    "lstm_search":{"learning_rates":[0.001,0.0003,0.003],"max_epochs":120,"patience":120,"batch_size":32,"shuffle":False,
                                   "checkpoint":"Complete all 120 epochs, restore minimum-validation-loss weights; no premature stopping"},
                    "xgb_search":{"depth":[2,3,5],"learning_rate":[0.03,0.08],"min_child_weight":[1,5],"max_trees":1200,"early_stopping_rounds":50},
                    "prophet_search":{"changepoint_prior_scale":[0.01,0.05,0.2],"regressors":[["irradiance"],["irradiance","lag1","mean7","efficiency7","rule_c"]],"trend":"linear","yearly_fourier_order":5,"weekly":False},
                    "ensembles":"equal LX; LX convex weights step .05; three-model convex weights step .1; three-model weights with LSTM >= .5; learned on validation only",
                    "postprocess":CLIP,
                    "fairness":"Same target days and information available at T-1, architecture-specific feature engineering. XGB/Prophet see known calendar; teaching LSTM stays (20,2). Not a pure architecture-only ablation.",
                    "limitations":["Single plant only; added multi_plant files excluded by user choice",
                                    "One temporal holdout, not evidence of all-site generalization",
                                    "Archived Best Match forecast availability at historical issue hour remains an assumption",
                                    "Research has already examined this dataset; this is a held-out development evaluation, not a newly collected blind dataset",
                                    "Daily totals, not hourly market settlement predictions",
                                    "No live serving, drift injection or automatic retraining is tested",
                                    "No test targets used for hyperparameters, scaler fit, epochs, ensemble weights or refit; prior test-day actuals are valid T-1 inputs"]}
        dump(out/"protocol.json",protocol)
        dump(out/"environment.json", {"python":sys.version,"platform":platform.platform(),
                                      "packages":{k:importlib.metadata.version(k) for k in
                                                  ["numpy","pandas","tensorflow","keras","xgboost","prophet","scikit-learn","matplotlib"]},
                                      "TF_ENABLE_ONEDNN_OPTS":os.environ["TF_ENABLE_ONEDNN_OPTS"]})
        for k, pred in bases.items():
            savepred(k,"val",va,np.array(pred)[va])
        pd.DataFrame({"date":dates, "split":["train" if j in tr else "validation" if j in va else "test" for j in range(len(y))],
                      "target_forecast_mj":p.irradiance}).to_csv(out/"split_manifest.csv",index=False)
        dump(out/"data_audit.json",{"rows":len(df),"targets":len(y),"duplicate_dates":0,"missing_days":0,
                                    "nonfinite_values":0,"forecast_matches_raw":True,
                                    "first_window_dates":df.Date.iloc[:20].astype(str).tolist(),
                                    "first_target":str(dates.iloc[0]),"test_not_used_in_selection":True})

    def xgb(final=False):
        from xgboost import XGBRegressor
        if final:
            selected=json.loads((out/"selected_xgb.json").read_text())
            cfg=selected["config"]; rounds=selected["rounds"]
            fitix=np.concatenate([tr,va]); ix=te
            model=XGBRegressor(**cfg,n_estimators=rounds,n_jobs=4,tree_method="hist",random_state=42)
            start=time.perf_counter(); model.fit(x.iloc[fitix],y[fitix])
            pred=model.predict(x.iloc[ix]); savepred("XGBoost","test",ix,pred)
            model.save_model(out/"models/xgboost.ubj")
            pd.DataFrame({"feature":x.columns,"importance":model.feature_importances_}).sort_values("importance",ascending=False).to_csv(out/"xgb_feature_importance.csv",index=False)
            dump(out/"runtime_xgb.json",{"final_fit_seconds":time.perf_counter()-start,"rounds":rounds})
            return
        results=[]; best=None
        for depth in [2,3,5]:
            for lr in [.03,.08]:
                for child in [1,5]:
                    cfg={"max_depth":depth,"learning_rate":lr,"min_child_weight":child,
                         "subsample":.9,"colsample_bytree":.9,"reg_lambda":5.,"objective":"reg:squarederror"}
                    start=time.perf_counter()
                    m=XGBRegressor(**cfg,n_estimators=1200,n_jobs=4,tree_method="hist",random_state=42,early_stopping_rounds=50)
                    m.fit(x.iloc[tr],y[tr],eval_set=[(x.iloc[va],y[va])],verbose=False)
                    pred=np.maximum(m.predict(x.iloc[va]),0)
                    result={"config":cfg,"rounds":int(m.best_iteration+1),
                            **metric(y[va],pred),"seconds":time.perf_counter()-start}
                    results.append(result); log(f"XGB depth={depth} lr={lr} child={child} val_RMSE={result['rmse_kwh']:.3f}")
                    if best is None or result["rmse_kwh"]<best["rmse_kwh"]:
                        best=result; savepred("XGBoost","val",va,pred)
                    dump(out/"search_xgb.json",results)
        dump(out/"selected_xgb.json",best)

    def prophet(final=False):
        from prophet import Prophet
        from prophet.serialize import model_to_json
        import logging
        logging.getLogger("cmdstanpy").setLevel(logging.WARNING)
        def fit(cfg,fitix,ix):
            m=Prophet(changepoint_prior_scale=cfg["changepoint_prior_scale"],
                      yearly_seasonality=5,weekly_seasonality=False,daily_seasonality=False,
                      seasonality_prior_scale=1.,uncertainty_samples=0)
            for reg in cfg["regressors"]:
                m.add_regressor(reg,prior_scale=1.,standardize=True)
            cols=["ds","y"]+cfg["regressors"]
            m.fit(p.iloc[fitix][cols],seed=42)
            return m,np.maximum(m.predict(p.iloc[ix].drop(columns="y"))["yhat"].to_numpy(),0)
        if final:
            cfg=json.loads((out/"selected_prophet.json").read_text())["config"]
            start=time.perf_counter(); m,pred=fit(cfg,np.concatenate([tr,va]),te)
            savepred("Prophet","test",te,pred)
            (out/"models/prophet.json").write_text(model_to_json(m),encoding="utf-8")
            dump(out/"runtime_prophet.json",{"final_fit_predict_seconds":time.perf_counter()-start})
            return
        results=[];best=None
        for cps in [.01,.05,.2]:
            for regs in [["irradiance"],["irradiance","lag1","mean7","efficiency7","rule_c"]]:
                cfg={"changepoint_prior_scale":cps,"regressors":regs}
                start=time.perf_counter(); m,pred=fit(cfg,tr,va)
                result={"config":cfg,**metric(y[va],pred),"seconds":time.perf_counter()-start}
                results.append(result);log(f"Prophet cps={cps} regressors={len(regs)} val_RMSE={result['rmse_kwh']:.3f}")
                if best is None or result["rmse_kwh"]<best["rmse_kwh"]:
                    best=result;savepred("Prophet","val",va,pred)
                dump(out/"search_prophet.json",results)
        dump(out/"selected_prophet.json",best)

    def lstm(final=False):
        # Import TensorFlow before other compiled ML frameworks in this process.
        import tensorflow as tf
        from tensorflow import keras
        tf.config.threading.set_intra_op_parallelism_threads(4)
        tf.config.threading.set_inter_op_parallelism_threads(1)
        tf.config.experimental.enable_op_determinism()
        sys.path.insert(0,str(ROOT/"project"))
        from serving_app.lstm_model import build_model
        class Progress(keras.callbacks.Callback):
            def on_epoch_end(self,epoch,logs=None):
                if (epoch+1)%10==0:
                    log(f"LSTM epoch={epoch+1} loss={logs['loss']:.6f}" +
                        (f" val_loss={logs['val_loss']:.6f}" if 'val_loss' in logs else ""))
        def scaled(fitix):
            last=targets[fitix[-1]]
            close=df.Close.iloc[:last+1].to_numpy(); vol=df.Volume.iloc[:last].to_numpy()
            lo=np.array([close.min(),vol.min()]); scale=np.array([np.ptp(close),np.ptp(vol)])
            assert (scale>0).all()
            return ((windows-lo)/scale).astype("float32"), ((y-lo[0])/scale[0]).astype("float32"),lo,scale
        def fit(lr,seed,fitix,ix,epochs,validate):
            keras.backend.clear_session();keras.utils.set_random_seed(seed)
            xx,yy,lo,scale=scaled(fitix)
            m=build_model()
            m.compile(optimizer=keras.optimizers.Adam(learning_rate=lr),loss="mse")
            callbacks=[Progress()]
            if validate:
                callbacks.append(keras.callbacks.EarlyStopping(monitor="val_loss",patience=120,
                                                               min_delta=0.,restore_best_weights=True))
            start=time.perf_counter()
            h=m.fit(xx[fitix],yy[fitix],validation_data=(xx[ix],yy[ix]) if validate else None,
                    epochs=epochs,batch_size=32,shuffle=False,verbose=0,callbacks=callbacks)
            pred=np.maximum(m.predict(xx[ix],verbose=0).ravel()*scale[0]+lo[0],0)
            selected_epoch=int(np.argmin(h.history["val_loss"])+1) if validate else epochs
            return m,pred,{"seed":seed,"learning_rate":lr,"best_epoch":selected_epoch,
                           "epochs_run":len(h.history['loss']),"seconds":time.perf_counter()-start,
                           "scaler_min":lo.tolist(),"scaler_range":scale.tolist(),
                           "scaler_last_generation_date":str(df.Date.iloc[targets[fitix[-1]]].date()),
                           "scaler_last_forecast_row":str(df.Date.iloc[targets[fitix[-1]]-1].date())},h.history
        if final:
            selected=json.loads((out/"selected_lstm.json").read_text())
            preds=[];records=[]
            # Epoch count is the median across validation-seed optima, fixed before test.
            epochs=selected["refit_epochs"]
            for seed in SEEDS:
                log(f"Final LSTM seed={seed} epochs={epochs}")
                m,pred,record,h=fit(selected['learning_rate'],seed,np.concatenate([tr,va]),te,epochs,False)
                savepred(f"LSTM_seed{seed}","test",te,pred);preds.append(pred);records.append(record)
                m.save(out/f"models/lstm_seed{seed}.keras")
                dump(out/f"history_final_lstm_{seed}.json",h)
                dump(out/"runtime_lstm.json",records)
            savepred("LSTM","test",te,np.mean(preds,axis=0))
            dump(out/"models/lstm_scaler.json",records[0])
            return
        results=[];best=None
        for lr in [.001,.0003,.003]:
            preds=[];records=[]
            for seed in SEEDS:
                log(f"Tune LSTM lr={lr} seed={seed}")
                m,pred,record,h=fit(lr,seed,tr,va,120,True)
                record.update(metric(y[va],pred));records.append(record);preds.append(pred)
                dump(out/f"history_val_lstm_{lr}_{seed}.json",h)
                savepred(f"LSTM_lr{lr}_seed{seed}","val",va,pred)
                log(f"LSTM seed={seed} best_epoch={record['best_epoch']} val_RMSE={record['rmse_kwh']:.3f}")
            pred=np.mean(preds,axis=0)
            result={"learning_rate":lr,"seeds":records,
                    "refit_epochs":int(np.median([r['best_epoch'] for r in records])),**metric(y[va],pred)}
            results.append(result)
            if best is None or result["rmse_kwh"]<best["rmse_kwh"]:
                best=result;savepred("LSTM","val",va,pred)
            dump(out/"search_lstm.json",results)
        dump(out/"selected_lstm.json",best)

    def select():
        base_names=list(bases)+["LSTM","XGBoost","Prophet"]
        vp={k:getpred(k,"val") for k in base_names}
        weights={"Mean_LSTM_XGB":[.5,.5,0.]}
        mat=np.column_stack([vp[k] for k in ["LSTM","XGBoost","Prophet"]])
        grids={"Weighted_LSTM_XGB":[[i/20,1-i/20,0.] for i in range(21)],
               "Weighted_All":[[i/10,j/10,(10-i-j)/10] for i in range(11) for j in range(11-i)],
               "LSTM_Main_Ensemble":[[i/10,j/10,(10-i-j)/10] for i in range(5,11) for j in range(11-i)]}
        for name,grid in grids.items():
            weights[name]=min(grid,key=lambda w:metric(y[va],mat@w)['rmse_kwh'])
        for name,w in weights.items():
            vp[name]=savepred(name,"val",va,mat@w)
        scores=[{"model":k,**metric(y[va],pred)} for k,pred in vp.items()]
        scores.sort(key=lambda r:r['rmse_kwh'])
        pd.DataFrame(scores).to_csv(out/"validation_metrics.csv",index=False)
        selected={"frozen_kst":datetime.now(ZoneInfo("Asia/Seoul")).isoformat(),
                  "test_evaluated":False,"weights_order":["LSTM","XGBoost","Prophet"],
                  "ensemble_weights":weights,"validation_selected_model":scores[0]['model'],
                  "validation_ranking":scores,
                  "xgb":json.loads((out/"selected_xgb.json").read_text()),
                  "prophet":json.loads((out/"selected_prophet.json").read_text()),
                  "lstm":json.loads((out/"selected_lstm.json").read_text())}
        dump(out/"frozen_selection.json",selected)
        log(f"FROZEN before test: selected={scores[0]['model']}; weights={weights}")

    def report():
        frozen=json.loads((out/"frozen_selection.json").read_text())
        pred={k:savepred(k,"test",te,np.array(v)[te]) for k,v in bases.items()}
        pred.update({k:getpred(k,"test") for k in ["LSTM","XGBoost","Prophet"]})
        mat=np.column_stack([pred[k] for k in ["LSTM","XGBoost","Prophet"]])
        for name,w in frozen['ensemble_weights'].items():
            pred[name]=savepred(name,"test",te,mat@w)
        rows=sorted([{"model":k,**metric(y[te],v)} for k,v in pred.items()],key=lambda r:r['rmse_kwh'])
        pd.DataFrame(rows).to_csv(out/"test_metrics.csv",index=False)
        seedrows=[{"model":f"LSTM_seed{s}",**metric(y[te],getpred(f'LSTM_seed{s}','test'))} for s in SEEDS]
        pd.DataFrame(seedrows).to_csv(out/"lstm_seed_metrics.csv",index=False)
        combined=pd.DataFrame({"date":dates.iloc[te].to_numpy(),"actual_kwh":y[te],**pred})
        combined.to_csv(out/"test_predictions.csv",index=False)
        monthly=[]
        months=dates.iloc[te].dt.to_period('M').astype(str).to_numpy()
        for month in np.unique(months):
            mask=months==month
            for name,pp in pred.items():
                monthly.append({"month":month,"model":name,**metric(y[te][mask],pp[mask])})
        pd.DataFrame(monthly).to_csv(out/"monthly_metrics.csv",index=False)
        errors=pd.DataFrame({k:v-y[te] for k,v in pred.items()})
        errors.corr().to_csv(out/"error_correlations.csv")
        # Paired circular moving-block bootstrap preserves some serial dependence.
        rng=np.random.default_rng(20261007);n=len(te);block=14
        starts=rng.integers(0,n,size=(2000,int(np.ceil(n/block))))
        indexes=((starts[:,:,None]+np.arange(block))%n).reshape(2000,-1)[:,:n]
        comparisons=[]
        selected=frozen['validation_selected_model']
        for a,b in [(selected,'RuleC'),(selected,'LSTM'),('LSTM','XGBoost')]:
            da=np.sqrt(np.mean((pred[a]-y[te])[indexes]**2,axis=1))
            db=np.sqrt(np.mean((pred[b]-y[te])[indexes]**2,axis=1))
            d=da-db
            comparisons.append({"a":a,"b":b,"difference_rmse_a_minus_b":metric(y[te],pred[a])['rmse_kwh']-metric(y[te],pred[b])['rmse_kwh'],
                                "ci95_low":float(np.quantile(d,.025)),"ci95_high":float(np.quantile(d,.975)),
                                "replicates":2000,"block_days":block})
        dump(out/"paired_bootstrap.json",comparisons)
        before=json.loads((out/"input_hashes.json").read_text())
        changes=[path for path,h in before.items() if not (ROOT/path).exists() or sha(ROOT/path)!=h]
        integrity={"checked_files":len(before),"changed_existing_files":changes,
                   "source_sha256":sha(SOURCE),"selection_sha256":sha(out/"frozen_selection.json")}
        dump(out/"integrity.json",integrity)
        assert not changes, f"Existing inputs/code changed during run: {changes}"
        result={"completed_kst":datetime.now(ZoneInfo("Asia/Seoul")).isoformat(),
                "splits":split,"validation_selected_model":selected,
                "test_lowest_rmse_model":rows[0]['model'],"test_ranking":rows,
                "lstm_seed_results":seedrows,"weights":frozen['ensemble_weights'],
                "paired_bootstrap":comparisons,"integrity":integrity}
        dump(out/"results.json",result)
        lines=["하동 태양광 모델 비교 — 실제 실행 결과", "",
               "최종 시험: 2025-02-28 ~ 2026-02-27, 365일. 하루 발전량(kWh).",
               f"검증 구간에서 사전 선택한 모델: {selected}",
               f"시험 구간에서 관측된 최저 RMSE: {rows[0]['model']}","",
               "model | RMSE(kWh) | MAE(kWh) | WAPE(%) | Bias(%)"]
        lines += [f"{r['model']} | {r['rmse_kwh']:.3f} | {r['mae_kwh']:.3f} | {r['wape_pct']:.3f} | {r['bias_pct']:.3f}" for r in rows]
        lines += ["", "앙상블 비중 순서: LSTM, XGBoost, Prophet",json.dumps(frozen['ensemble_weights'],ensure_ascii=False,indent=2),
                  "", "LSTM은 시드 42·43·44 세 모델의 평균이다. 단일 시드 결과는 lstm_seed_metrics.csv에 있다.",
                  "시드별 검증 최적 epoch의 중앙값으로 재학습했다. 최종 시험으로 epoch/가중치를 조절하지 않았다.",
                  "매일 전날까지의 실제 발전량과 보관된 하루 전 예보를 이용하는 1일 선행 평가다. 365일 일괄 장기예보가 아니다.",
                  "학습 때만 스케일러를 맞췄다. 최종 모델은 학습+검증 구간으로 다시 학습했고 시험 기간에는 재학습하지 않았다.",
                  "XGBoost는 20일 원시창+파생 특성+달력, Prophet은 달력+선택된 회귀변수, LSTM은 수업 (20,2) 입력을 사용한다.",
                  "원시 정보의 가용 시점은 같지만 특성 표현은 다르다. 순수 구조만의 우열을 증명하는 실험은 아니다.",
                  "기존 보고서의 264일/전체 자료 스케일링 평가와 시험 기간·전처리가 달라 수치를 직접 비교하면 안 된다.",
                  "하동 1곳의 시간순 분할 1개 결과다. 다른 발전소·향후 기간 성능은 검증하지 않았다.",
                  "과거 Best Match 예보가 실제 당시 같은 시각에 제공됐는지는 저장소에 남은 가정이다.",
                  "일 단위 예측이며 시장 시간대별 정산 성능/실시간 서빙/자동 재학습 결과가 아니다.",
                  "이 자료는 기존 연구에서 이미 분석된 자료이므로 새로 수집된 완전 블라인드 시험은 아니다.",
                  "기존 project/ 코드와 원본 데이터 해시 검사를 통과했다.",
                  "", "공식 API 참고:",
                  "https://facebook.github.io/prophet/docs/quick_start.html",
                  "https://facebook.github.io/prophet/docs/seasonality,_holiday_effects,_and_regressors.html",
                  "https://xgboost.readthedocs.io/en/stable/python/sklearn_estimator.html",
                  "https://keras.io/api/callbacks/early_stopping/"]
        (out/"report.txt").write_text('\n'.join(lines),encoding='utf-8')
        import matplotlib.pyplot as plt
        plt.rcParams['font.family']='Malgun Gothic'
        plt.rcParams['axes.unicode_minus']=False
        fig,ax=plt.subplots(figsize=(11,6.5),layout='constrained')
        names=[r['model'] for r in rows]; values=[r['rmse_kwh'] for r in rows]
        colors=['#2563eb' if name==selected else '#e58a19' if name=='LSTM' else '#98a3b3' for name in names]
        bars=ax.barh(names,values,color=colors);ax.invert_yaxis()
        ax.bar_label(bars,fmt='%.2f',padding=5)
        ax.set_xlim(0,max(values)*1.15);ax.set_xlabel('RMSE (하루 kWh, 낮을수록 좋음)')
        ax.set_title('하동 발전량 예측: 365일 시험 구간 비교\n2025-02-28 ~ 2026-02-27 · 파랑: 검증 구간 사전 선택 · 주황: LSTM')
        ax.spines[['top','right']].set_visible(False)
        fig.savefig(out/'test_rmse.png',dpi=170);plt.close(fig)
        log('RESULTS '+json.dumps(result,ensure_ascii=False))

    stages={"prepare":prepare,"xgb":xgb,"prophet":prophet,"lstm":lstm,"select":select,
            "final_xgb":lambda:xgb(True),"final_prophet":lambda:prophet(True),
            "final_lstm":lambda:lstm(True),"report":report}
    if args.stage=='all':
        # Separate processes isolate compiled frameworks and permit stepwise recovery.
        import subprocess
        for stage in stages:
            command=[sys.executable,'-X','utf8','-B',str(Path(__file__).resolve()),'--out',args.out,'--stage',stage]
            with (out/f'{stage}.log').open('w',encoding='utf-8') as fp:
                log(f'START {stage}')
                subprocess.run(command,stdout=fp,stderr=subprocess.STDOUT,check=True,cwd=ROOT/'project')
            log(f'DONE {stage}')
    else:
        if args.stage!='prepare':
            protocol=json.loads((out/'protocol.json').read_text(encoding='utf-8'))
            assert sha(SOURCE)==protocol['source_sha256']
        if args.stage.startswith('final_') or args.stage=='report':
            assert (out/'frozen_selection.json').exists(), 'Freeze selection before test'
        stages[args.stage]()


if __name__=='__main__':
    main()
