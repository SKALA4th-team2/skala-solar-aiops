"""T5 대조 2 의 보충: 재학습 게이트(뒤 5건 RMSE)의 흔들림과 통과율, 치우침이 줄어든 시작일 비율, 시드별 값."""
from pathlib import Path
import glob, numpy as np, pandas as pd
HERE = Path(__file__).resolve().parent
D = pd.concat([pd.read_csv(f) for f in sorted(glob.glob(str(HERE / "t5_02_ft_seed*.csv")))], ignore_index=True)
pd.set_option("display.width", 250)
print("[1] 시드별·배율별: 다음 21일 RMSE 평균(고정, 실습 설정 재학습, 배율 보정)과 치우침% 평균, |치우침|이 줄어든 시작일 비율")
rows = []
for (f, s), g in D.groupby(["factor", "seed"], sort=False):
    rows.append(dict(배율=f, 시드=s, n=len(g), RMSE고정=round(g.next_rmse_frozen.mean(), 1), RMSE재학습=round(g.next_rmse_ft.mean(), 1), RMSE보정=round(g.next_rmse_level.mean(), 1),
                     치우침고정=round(g.next_bias_pct_frozen.mean(), 1), 치우침재학습=round(g.next_bias_pct_ft.mean(), 1), 치우침보정=round(g.next_bias_pct_level.mean(), 1),
                     절댓값치우침_줄어든비율_재학습=round((g.next_bias_pct_ft.abs() < g.next_bias_pct_frozen.abs()).mean() * 100, 1),
                     절댓값치우침_줄어든비율_보정=round((g.next_bias_pct_level.abs() < g.next_bias_pct_frozen.abs()).mean() * 100, 1),
                     RMSE줄어든비율_재학습=round((g.next_rmse_ft < g.next_rmse_frozen).mean() * 100, 1)))
print(pd.DataFrame(rows).to_string(index=False))
print("\n[2] 재학습 게이트에 쓰이는 뒤 5건 RMSE(실습 설정 재학습 뒤)가 한도 이하인 시작일 비율%. 한도는 예시 값이다")
rows = []
for f, g in D.groupby("factor", sort=False):
    r = dict(배율=f, 중앙=round(g.gate5_ft.median(), 1), p5=round(np.percentile(g.gate5_ft, 5), 1), p95=round(np.percentile(g.gate5_ft, 95), 1))
    for G in (35, 40, 45, 50, 60):
        r[f"<= {G}"] = round((g.gate5_ft <= G).mean() * 100, 1)
    rows.append(r)
print(pd.DataFrame(rows).to_string(index=False))
print("\n[3] 같은 모델의 다음 21일 RMSE(고정)와 뒤 5건 RMSE(재학습 전)의 상관: %.2f (배율 1.0, 시드 모음). 5건 RMSE 의 변동계수 %.2f, 21건 RMSE 의 변동계수 %.2f" % (
    D[D.factor == 1.0][["gate5_before", "next_rmse_frozen"]].corr().iloc[0, 1], D[D.factor == 1.0].gate5_before.std() / D[D.factor == 1.0].gate5_before.mean(),
    D[D.factor == 1.0].batch_rmse.std() / D[D.factor == 1.0].batch_rmse.mean()))
print("\n[4] 배치 21건 RMSE 의 학습 RMSE 대비 배수 분포(시드 모음): 배율별 5%, 50%, 95%, 1.3배 초과 비율, 1.5배 초과 비율")
for f, g in D.groupby("factor", sort=False):
    x = g.batch_rmse / g.train_rmse
    print("  배율 %.2f: %.2f, %.2f, %.2f | 1.3배 초과 %.1f%%, 1.5배 초과 %.1f%% | 배치 RMSE 중앙 %.1fkWh" % (f, *np.percentile(x, [5, 50, 95]), (x > 1.3).mean() * 100, (x > 1.5).mean() * 100, g.batch_rmse.median()))
print("\n[5] 상대 게이트(같은 뒤 5건에서 재학습 뒤 RMSE 가 재학습 전 이하): 통과율과, 통과한 경우·탈락한 경우의 다음 21일 RMSE 변화 중앙(kWh)")
for f, g in D.groupby("factor", sort=False):
    ps = g.gate5_ft <= g.gate5_before; ch = g.next_rmse_ft - g.next_rmse_frozen
    print("  배율 %.2f: 통과 %.1f%% | 통과한 시작일의 다음 21일 RMSE 변화 중앙 %+.1f (줄어든 비율 %.0f%%), 탈락한 시작일 %+.1f (줄어든 비율 %.0f%%) | 뒤 5건 RMSE 변화 중앙 %+.1f" % (
        f, ps.mean() * 100, ch[ps].median(), (ch[ps] < 0).mean() * 100, ch[~ps].median() if (~ps).any() else float('nan'), (ch[~ps] < 0).mean() * 100 if (~ps).any() else float('nan'), (g.gate5_ft - g.gate5_before).median()))
