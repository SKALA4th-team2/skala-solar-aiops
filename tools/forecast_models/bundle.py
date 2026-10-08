"""Forecast model package implementing the GitHub FastAPI predict_one contract."""
import hashlib
import json
import pickle
from pathlib import Path
import numpy as np

CONTRACT = "solar_next_day_jma_msm_day1_v1"


class ForecastModel:
    def __init__(self, directory):
        from tensorflow import keras
        self.directory = Path(directory)
        self.metadata = json.loads((self.directory/"metadata.json").read_text(encoding="utf-8"))
        if self.metadata["input_contract"] != CONTRACT:
            raise ValueError("Wrong weather/input contract")
        hashes = json.loads((self.directory/"bundle_hashes.json").read_text(encoding="utf-8"))
        for filename, expected in hashes.items():
            if hashlib.sha256((self.directory/filename).read_bytes()).hexdigest() != expected:
                raise ValueError(f"Model bundle integrity failure: {filename}")
        # Only load the trusted, locally generated scaler packaged with this model.
        with (self.directory/"scaler.pkl").open("rb") as fp:
            self.scaler_values = pickle.load(fp)
        self._keras_model = keras.models.load_model(self.directory/"model.keras",compile=False)
        if self._keras_model.input_shape[1:] != (20,2):
            raise ValueError("Expected teaching-model input (20,2)")
        self.version = self.metadata["bundle_version"]
        self.source = "local"

    def transform(self, windows):
        a = np.asarray(windows,dtype=float)
        if a.ndim!=3 or a.shape[1:]!=(20,2) or not np.isfinite(a).all():
            raise ValueError("Expected finite (n,20,2) windows")
        if (a[:,:,0]<0).any() or ((a[:,:,1]<0)|(a[:,:,1]>45)).any():
            raise ValueError("Generation must be >=0 and forecast radiation in [0,45]")
        s = self.scaler_values
        lo = np.array([s["close_min"],s["volume_min"]])
        ranges = np.array([s["close_max"]-s["close_min"],s["volume_max"]-s["volume_min"]])
        return ((a-lo)/ranges).astype("float32")

    def predict_windows(self, windows):
        z = self._keras_model.predict(self.transform(windows),verbose=0).ravel()
        s = self.scaler_values
        return np.maximum(z*(s["close_max"]-s["close_min"])+s["close_min"],0)

    def predict_one(self, sequence):
        """20 chronological {close: generation[d], volume: forecast[d+1]} rows -> kWh."""
        return float(self.predict_windows([[[r["close"],r["volume"]] for r in sequence]])[0])
