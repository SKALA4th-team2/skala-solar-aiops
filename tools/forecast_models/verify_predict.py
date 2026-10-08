"""Compare the public inference helper with independently saved test predictions."""
from predict import predict
import argparse
import copy
import csv
import json
import math
from train import ROOT, DEFAULT, read


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--out',default=DEFAULT);args=ap.parse_args()
    out=ROOT/args.out;dest=out/'plants/15043409_u1';request=read(dest/'evaluation_request.json')
    with (dest/'test_predictions.csv').open(encoding='utf-8') as fp:expected=next(csv.DictReader(fp))
    checks=[]
    for name in ['LSTM','XGBoost','Prophet','Ensemble','LSTM_Main_Ensemble','Persistence','Mean7','RuleC','selected']:
        actual=predict(dest/'evaluation',request,name)
        assert actual['target_date']==expected['date'][:10]
        assert math.isclose(actual['predicted_kwh'],float(expected[actual['model']]),rel_tol=1e-6,abs_tol=1e-3)
        checks.append(actual)
    for kind in ['date_gap','nonfinite','negative_generation','radiation_out_of_range','wrong_length']:
        bad=copy.deepcopy(request)
        if kind=='date_gap':bad['sequence'][1]['date']=bad['sequence'][0]['date']
        elif kind=='nonfinite':bad['sequence'][0]['volume']=float('nan')
        elif kind=='negative_generation':bad['sequence'][0]['close']=-1
        elif kind=='radiation_out_of_range':bad['sequence'][0]['volume']=46
        else:bad['sequence'].pop()
        try:predict(dest/'evaluation',bad)
        except ValueError:pass
        else:raise AssertionError('Expected validation error: '+kind)
    result=dict(passed=True,model_choices_checked=len(checks),invalid_inputs_rejected=5,checks=checks)
    (out/'inference_check.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print('INFERENCE CHECK PASSED',len(checks),'models, 5 invalid requests rejected')


if __name__=='__main__':main()
