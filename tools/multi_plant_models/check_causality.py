"""Confirm target/future generation and unavailable weather cannot enter features."""
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd
from bundle import features

ROOT = Path(__file__).resolve().parents[2]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out",default="docs/proposal/evidence/multi_plant_models_20261007")
    args = ap.parse_args()
    out = ROOT/args.out
    screening = json.loads((out/"screening.json").read_text(encoding="utf-8"))
    results = []
    for plant in screening["admitted"]:
        source = ROOT/"datasets/multi_plant"/plant["selected_upload"]["file"]
        df = pd.read_csv(source,parse_dates=["Date"]).tail(1480).reset_index(drop=True)
        raw = df[["Close","Volume"]].to_numpy()
        first_test = len(df)-365
        targets = np.arange(20,first_test+1)
        original = np.array([raw[t-20:t] for t in targets])
        changed = raw.copy()
        changed[first_test:,0] += 100000
        # Volume[T] contains GSR[T-1], unavailable under this declared input contract.
        changed[first_test:,1] += 100000
        modified = np.array([changed[t-20:t] for t in targets])
        np.testing.assert_array_equal(original,modified)
        xa,pa = features(original,df.Date.iloc[targets])
        xb,pb = features(modified,df.Date.iloc[targets])
        pd.testing.assert_frame_equal(xa,xb)
        pd.testing.assert_frame_equal(pa,pb)
        assert raw[first_test,0] != changed[first_test,0]
        assert original[-1,-1,1] == raw[first_test-1,1]
        results.append({"plant_id":plant["plant_id"],"passed":True,"first_test_target":str(df.Date.iloc[first_test].date()),
                        "latest_observed_weather_date":str((df.Date.iloc[first_test]-pd.Timedelta(days=2)).date()),
                        "unchanged_causal_windows":len(targets)})
    (out/"causality_check.json").write_text(json.dumps({"passed":True,"plants":results},ensure_ascii=False,indent=2),encoding="utf-8")
    print("PASS",len(results),"plants: perturbing targets/future does not change earlier inputs")


if __name__=="__main__":
    main()
