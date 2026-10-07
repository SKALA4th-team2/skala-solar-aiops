# T6 다시 계산(3): 마감 시각 정각이 아니라 "마감 1시간 전까지의 계량값"만 쓸 수 있다고 볼 때의 민감도.
# 제출 마감 10시·14시·17시·20시에 대해 각각 9시·13시·16시·19시까지의 누적값(열 1..h)을 쓴다.
# 실행: PYTHONDONTWRITEBYTECODE=1 /Users/psm/workspace/skala-aiops/mlflow/.venv/bin/python T6_recalc3.py > out_recalc3.txt
import numpy as np, pandas as pd, json
SRC = '(작업 폴더)/solar/data_15043409.csv'
df = pd.read_csv(SRC, encoding='cp949'); df['d'] = pd.to_datetime(df['년월일']); df = df.sort_values('d').reset_index(drop=True)
A = df[[str(i) for i in range(1, 25)]].to_numpy(dtype=float); tot = A.sum(axis=1); dates = pd.DatetimeIndex(df['d']); mon = dates.month.to_numpy()
ok = tot >= 1.0
res = {}
print('시각(열 1..h 누적) | 발전량 가중 비중 | 월별 최소~최대 | 일별 하위 5% | 월별 비율로 보정한 하루 합계 추정의 RMSE(kWh)와 실제 합계 대비 오차율(평가 2023-05-31~2025-12-31, 비율은 그 이전 자료로 구함)')
s, e = '2023-05-31', '2025-12-31'
tr = np.asarray(dates < s) & ok; te = np.asarray((dates >= s) & (dates <= e))
for h in (9, 10, 13, 14, 16, 17, 19, 20):
    w = A[ok, :h].sum() / A[ok].sum()
    mm = [A[ok & (mon == m), :h].sum() / A[ok & (mon == m)].sum() for m in range(1, 13)]
    day = (A[ok, :h].sum(axis=1) / tot[ok])
    ratio = np.array([A[tr & (mon == m), :h].sum() / A[tr & (mon == m)].sum() for m in range(1, 13)])
    est = A[:, :h].sum(axis=1) / ratio[mon - 1]
    err = est[te] - tot[te]
    rm = float(np.sqrt(np.mean(err ** 2))); wp = float(np.abs(err).sum() / tot[te].sum() * 100)
    print(f'  {h:>2}시 | {w*100:6.2f}% | {min(mm)*100:6.2f}% ~ {max(mm)*100:6.2f}% | {np.quantile(day, .05)*100:6.2f}% | RMSE {rm:6.2f}kWh, {wp:5.2f}%')
    res[str(h)] = {'energy_weighted': float(w), 'month_min': float(min(mm)), 'month_max': float(max(mm)), 'day_p05': float(np.quantile(day, .05)), 'est_rmse': rm, 'est_wape_pct': wp}
json.dump(res, open('(작업 폴더)/merged/T6-scheme/out_recalc3.json', 'w'), indent=1)
