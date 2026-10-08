"""Solar daily policy, values adopted from decisions 0005--0008 and 0011."""
import math
from datetime import date

WINDOW_SIZE=21
MIN_VALID_DAYS=15
DECLINE_PCT=-7.5
RMSE_WARNING_MULTIPLIER=1.5
MIN_GATE_DAYS=180
MEAN7_GATE_RATIO=.80
RULEC_GATE_RATIO=1.05
MAX_BIAS_PCT=10.


def metrics(actual,predicted):
    if len(actual)!=len(predicted) or not actual:raise ValueError('Aligned nonempty samples required')
    if not all(math.isfinite(float(v)) for v in list(actual)+list(predicted)):raise ValueError('Nonfinite metric input')
    errors=[p-y for y,p in zip(actual,predicted)]
    total=sum(actual)
    return dict(n=len(actual),rmse_kwh=math.sqrt(sum(e*e for e in errors)/len(errors)),
                mae_kwh=sum(abs(e) for e in errors)/len(errors),
                bias_pct=100*sum(errors)/total if total>0 else None)


def initial_gate(scores):
    model=scores['LSTM'];limit=min(MEAN7_GATE_RATIO*scores['Mean7']['rmse_kwh'],RULEC_GATE_RATIO*scores['RuleC']['rmse_kwh'])
    bias=model['bias_pct']
    passed=model['n']>=MIN_GATE_DAYS and model['rmse_kwh']<=limit and bias is not None and abs(bias)<=MAX_BIAS_PCT
    return dict(passed=passed,limit_kwh=limit,rmse_kwh=model['rmse_kwh'],bias_pct=bias,n=model['n'],
                bias_warning=bias is not None and abs(bias)>5,policy='relative-80-105-bias10-v1')


def classify(rows,capacity_kw):
    """Expected is post-observation evidence, never a forecast-model feature."""
    flags=[];scale=capacity_kw/55
    for index,row in enumerate(rows):
        x=row['close'];e=row.get('expected');available=e is not None and math.isfinite(e) and e>0
        outage=x<=0 or (available and e>=30*scale and x<.3*e)
        low=outage or (available and e>=80*scale and x<.7*e)
        prior=[f for r,f in zip(rows[max(0,index-6):index],flags[-6:]) if (date.fromisoformat(row['date'])-date.fromisoformat(r['date'])).days<=6]
        hold=sum(f['low'] for f in prior)+int(low)>=3
        flags.append(dict(outage=outage,low=low,hold=hold,valid=available and not outage and not hold,
                          daily_alert=available and e>=80*scale and x<.5*e))
    return flags


def performance_index(rows,flags):
    selected=[(r['close'],r['expected']) for r,f in zip(rows,flags) if f['valid']]
    if not selected:return None,0
    return sum(min(max(x,.5*e),1.5*e) for x,e in selected)/sum(e for _,e in selected),len(selected)


def assess(rows,predictions,*,capacity_kw,baseline,reference_rmse,model_version):
    result=dict(status='skipped',model_version=str(model_version))
    if len(rows)<41 or len(predictions)<21:return dict(result,reason='insufficient_window')
    rows=rows[-41:];predictions=predictions[-21:];flags=classify(rows,capacity_kw)
    tail=flags[-21:];pi,n=performance_index(rows[-21:],tail);head,head_n=performance_index(rows[:20],flags[:20])
    rmse=metrics([p['actual'] for p in predictions],[p['predicted'] for p in predictions])['rmse_kwh']
    result.update(pi=pi,baseline=baseline,valid_days=n,outage_days=sum(f['outage'] for f in tail),
                  hold_days=sum(f['hold'] for f in tail),rmse21=rmse)
    if baseline is None or baseline<=0:return dict(result,reason='baseline_unavailable')
    deviation=100*(pi/baseline-1) if pi is not None else None
    head_deviation=100*(head/baseline-1) if head is not None else None
    result.update(deviation_pct=deviation,head_deviation_pct=head_deviation)
    facility=any(f['outage'] or f['hold'] or f['daily_alert'] for f in flags)
    if n<MIN_VALID_DAYS:return dict(result,status='facility_check' if facility else 'skipped',reason='insufficient_valid_days')
    if facility:return dict(result,status='facility_check',reason='outage_or_hold_in_training_window')
    if deviation<DECLINE_PCT:
        eligible=head_n>=MIN_VALID_DAYS and head_deviation<DECLINE_PCT
        return dict(result,status='drift_alerted',reason='retrain_eligible' if eligible else 'input_window_not_yet_below_limit')
    if reference_rmse and rmse>reference_rmse*RMSE_WARNING_MULTIPLIER:
        return dict(result,status='input_anomaly',reason='rmse_warning_only')
    return dict(result,status='ok',reason=None)
