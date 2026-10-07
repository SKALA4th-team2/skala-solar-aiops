"""Portable inference for ASOS lag-1 plant model bundles; no training imports."""
import json
from pathlib import Path
import numpy as np
import pandas as pd

SEQUENCE = 20
WINDOW_COLUMNS = [f"{kind}_{i}" for i in range(SEQUENCE) for kind in ("close", "volume")]


def features(windows, dates):
    windows = np.asarray(windows, dtype=float)
    if windows.ndim != 3 or windows.shape[1:] != (20, 2):
        raise ValueError("Expected chronological (n, 20, 2) generation/ASOS-lag1 windows")
    if not np.isfinite(windows).all() or (windows < 0).any():
        raise ValueError("Inputs must be finite and nonnegative")
    dates = pd.DatetimeIndex(dates)
    c = windows[:, :, 0]
    day = dates.dayofyear.to_numpy()
    x = pd.DataFrame(windows.reshape(len(windows), -1), columns=WINDOW_COLUMNS)
    for n in (7, 20):
        x[f"mean{n}"] = c[:, -n:].mean(axis=1)
        x[f"std{n}"] = c[:, -n:].std(axis=1)
    x["year_sin"] = np.sin(2*np.pi*day/365.25)
    x["year_cos"] = np.cos(2*np.pi*day/365.25)
    p = pd.DataFrame({"ds": dates, "observed_gsr_t_minus_2": windows[:, -1, 1],
                      "lag1": c[:, -1], "mean7": c[:, -7:].mean(axis=1)})
    return x, p


def request_frame(windows, dates):
    frame = pd.DataFrame(np.asarray(windows).reshape(-1, 40), columns=WINDOW_COLUMNS)
    frame.insert(0, "target_date", pd.DatetimeIndex(dates).strftime("%Y-%m-%d"))
    return frame


class Bundle:
    def __init__(self, path, kind="LSTM"):
        self.path = Path(path)
        self.meta = json.loads((self.path / "metadata.json").read_text(encoding="utf-8"))
        if self.meta["weather_semantics"] != "Volume[d] = observed ASOS GSR[d-1]; target T sees GSR[T-2]":
            raise ValueError("Incompatible weather semantics")
        self.kind = kind
        needs = [kind] if kind in ("LSTM", "XGBoost", "Prophet") else ["LSTM", "XGBoost", "Prophet"]
        self.models = {}
        if "LSTM" in needs:
            from tensorflow import keras
            self.models["LSTM"] = keras.models.load_model(self.path / "lstm.keras", compile=False)
        if "XGBoost" in needs:
            from xgboost import XGBRegressor
            m = XGBRegressor(n_jobs=2)
            m.load_model(self.path / "xgboost.ubj")
            self.models["XGBoost"] = m
        if "Prophet" in needs:
            from prophet.serialize import model_from_json
            self.models["Prophet"] = model_from_json((self.path / "prophet.json").read_text(encoding="utf-8"))

    def predict(self, frame):
        expected = ["target_date"] + WINDOW_COLUMNS
        if list(frame.columns) != expected:
            raise ValueError("Expected target_date followed by chronological close_i, volume_i, i=0..19")
        w = frame[WINDOW_COLUMNS].to_numpy(dtype=float).reshape(-1, 20, 2)
        x, p = features(w, pd.to_datetime(frame.target_date))
        preds = {}
        for kind, model in self.models.items():
            if kind == "LSTM":
                s = self.meta["scaler"]
                z = ((w-np.array(s["min"]))/np.array(s["range"])).astype("float32")
                # Keep inverse transform identical to the training prediction path.
                result = model.predict(z, verbose=0).ravel()*s["range"][0]+s["min"][0]
            elif kind == "XGBoost":
                result = model.predict(x)
            else:
                result = model.predict(p).yhat.to_numpy()
            preds[kind] = np.maximum(result, 0)
        if self.kind in preds:
            result = preds[self.kind]
        else:
            weights = self.meta["ensemble_weights"][self.kind]
            result = np.column_stack([preds[k] for k in ("LSTM", "XGBoost", "Prophet")]) @ weights
        return pd.DataFrame({"prediction_kwh": result})
