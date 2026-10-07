"""Export an actual contiguous historical upload/request for a selected plant."""
import argparse,csv,io,json,sys
from datetime import date,timedelta
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'project'))
from serving_app import runtime as rt

def main():
    p=argparse.ArgumentParser();p.add_argument('--plant',default='hadong-sewage');p.add_argument('--end',default='2025-07-31');p.add_argument('--out',required=True);a=p.parse_args()
    history={r['date']:r for r in rt.read(rt.root()/'history'/f'{a.plant}.json')};end=date.fromisoformat(a.end)
    dates=[str(end-timedelta(days=i)) for i in range(40,-1,-1)]
    if any(d not in history for d in dates):raise SystemExit('This interval has missing/invalid daily data. Choose another end date.')
    rows=[history[d] for d in dates];out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    with (out/f'{a.plant}.csv').open('w',encoding='utf-8',newline='') as fp:
        writer=csv.writer(fp);writer.writerow(['Date','Close','Volume','Expected'])
        writer.writerows([r['date'],r['close'],r['volume'],r.get('expected') if r.get('expected') is not None else ''] for r in rows)
    body=dict(plant_id=a.plant,dates=dates,prices=[r['close'] for r in rows],volumes=[r['volume'] for r in rows],expected=[r.get('expected') for r in rows])
    rt.write(out/f'{a.plant}-batch.json',body)
    rt.write(out/f'{a.plant}-predict.json',dict(plant_id=a.plant,sequence=[{k:r[k] for k in ['date','close','volume']} for r in rows[-20:]]))
    print(out.resolve())
if __name__=='__main__':main()
