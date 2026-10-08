"""Perturb future values in temporary data copies; past model inputs must not change."""
import argparse
import json
from pathlib import Path
import tempfile
import numpy as np
import pandas as pd
from train import ROOT, DEFAULT, read, make_data, tabular


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--out',default=DEFAULT);args=ap.parse_args()
    out=ROOT/args.out;checks=[]
    for plant in read(out/'screening.json')['admitted']:
        source=ROOT/plant['source'];_,_,windows,y,dates,tr,va,te=make_data(source)
        cutoff=dates[te[0]];raw=pd.read_csv(source,parse_dates=['target_date'])
        # The current target's generation is an unknown label, never an input.
        mask=(raw.target_date>=cutoff)&raw.gen_kwh.notna()
        raw.loc[mask,'gen_kwh']=raw.loc[mask,'gen_kwh']*2+1
        # Target-day forecast is allowed; only later targets are unknown to this window.
        mask=raw.target_date>cutoff
        raw.loc[mask,'shortwave_radiation_previous_day1']*=.5
        with tempfile.TemporaryDirectory(prefix='forecast-causality-') as folder:
            modified=Path(folder)/'modified.csv';raw.to_csv(modified,index=False)
            _,_,changed,changed_y,changed_dates,_,_,_=make_data(modified)
        np.testing.assert_array_equal(dates,changed_dates)
        past=dates<=cutoff
        np.testing.assert_array_equal(windows[past],changed[past])
        before_x,before_p,_=tabular(windows[past],dates[past])
        after_x,after_p,_=tabular(changed[past],dates[past])
        pd.testing.assert_frame_equal(before_x,after_x);pd.testing.assert_frame_equal(before_p,after_p)
        assert changed_y[te[0]]!=y[te[0]] and not np.array_equal(windows[~past],changed[~past])
        checks.append(dict(plant_id=plant['plant_id'],cutoff=str(cutoff.date()),passed=True))
    result=dict(passed=True,plants_checked=len(checks),checks=checks,
                note='Verifies feature chronology only; forecast publication issue time remains unverified.')
    (out/'causality_check.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print('CAUSALITY CHECK PASSED',len(checks))


if __name__=='__main__':main()
