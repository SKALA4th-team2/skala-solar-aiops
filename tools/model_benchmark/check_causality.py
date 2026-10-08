"""Perturb future generation in memory to detect target leakage into features."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--out',default='docs/proposal/evidence/model_benchmark_20261007')
    args=ap.parse_args()
    path=Path(__file__).with_name('benchmark.py')
    spec=importlib.util.spec_from_file_location('benchmark_causality',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    baseline=module.data();changed_frame=baseline[0].copy()
    original_reader=pd.read_csv
    first_test=baseline[9][0]
    raw_cutoff=baseline[1][first_test]
    changed_frame.loc[raw_cutoff:,'Close']+=10000
    def perturbed_reader(source,*positional,**keywords):
        if Path(source).resolve()==module.SOURCE:
            return changed_frame.copy()
        return original_reader(source,*positional,**keywords)
    with patch.object(module.pd,'read_csv',side_effect=perturbed_reader):
        changed=module.data()
    count=first_test+1
    assert np.array_equal(baseline[2][:count],changed[2][:count])
    assert np.array_equal(baseline[3].iloc[:count],changed[3].iloc[:count])
    assert np.array_equal(baseline[6].drop(columns='y').iloc[:count],changed[6].drop(columns='y').iloc[:count])
    assert changed[4][first_test]!=baseline[4][first_test]
    result={'status':'PASS','test':'Perturb generation from first test target onward by +10000 kWh in memory. All three model feature sets up to and including that target remain unchanged; its label changes.',
            'checked_samples':int(count),'benchmark_sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
    out=module.ROOT/args.out
    (out/'causality_check.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
