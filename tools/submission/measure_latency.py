"""Measure warmed sequential HTTP predictions, including the audit transaction."""
import argparse,json,statistics,time,urllib.request
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--base',default='http://127.0.0.1:8078');p.add_argument('--out',type=Path,required=True);a=p.parse_args()
with urllib.request.urlopen(a.base+'/ui/sample?plant_id=hadong-sewage',timeout=60) as response:sample=json.load(response)['prediction']
payload=json.dumps(sample).encode()
def predict():
    with urllib.request.urlopen(urllib.request.Request(a.base+'/predict',data=payload,headers={'Content-Type':'application/json'}),timeout=60) as response:
        result=json.load(response);assert len(result['predictions'])==24 and result['prediction_id']
predict();times=[]
for _ in range(30):
    start=time.perf_counter();predict();times.append((time.perf_counter()-start)*1000)
result=dict(scope='local loopback warmed single-plant sequential POST /predict including SQLite audit; not concurrent load SLA',count=len(times),p95_ms=sorted(times)[28],mean_ms=statistics.mean(times),max_ms=max(times),target_p95_ms=1000,passed=sorted(times)[28]<=1000,samples_ms=times)
a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps({k:v for k,v in result.items() if k!='samples_ms'}))
