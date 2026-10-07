"""T5 대조 2 의 요약: 시드별 CSV(t5_02_ft_seed*.csv)를 모아 배율별로 정리한다."""
from pathlib import Path
import glob
import warnings
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
HERE = Path(__file__).resolve().parent
pd.set_option("display.width", 250); pd.set_option("display.max_columns", 60)
D = pd.concat([pd.read_csv(f) for f in sorted(glob.glob(str(HERE / "t5_02_ft_seed*.csv")))], ignore_index=True)
print("시드", sorted(D.seed.unique()), "| 시작일", D.start.nunique(), "개", D.start.min(), "~", D.start.max(), "| 학습 RMSE", D.groupby("seed").train_rmse.first().round(2).to_dict())
D["batch_x"] = D.batch_rmse / D.train_rmse
D["next_x_frozen"] = D.next_rmse_frozen / D.train_rmse


def rng(s):
    return "%.1f ~ %.1f" % (s.min(), s.max())


rows = []
for f, g in D.groupby("factor", sort=False):
    per = g.groupby("seed")
    r = {"배율": f}
    r["배치 21건 RMSE / 학습 RMSE (시드별 중앙값의 범위)"] = "%.2f ~ %.2f" % (per.batch_x.median().min(), per.batch_x.median().max())
    r["배치 21건 RMSE 가 1.3배를 넘는 시작일 비율%"] = rng(per.batch_x.apply(lambda s: (s > 1.3).mean() * 100))
    r["배치 21건 치우침%(예측-실제, 시드별 중앙값)"] = rng(per.batch_bias_pct.median())
    r["뒤 5건 게이트 RMSE: 재학습 전 중앙"] = rng(per.gate5_before.median())
    r["뒤 5건 게이트 RMSE: 재학습 전 5%~95%(모은 값)"] = "%.1f ~ %.1f" % tuple(np.percentile(g.gate5_before, [5, 95]))
    r["뒤 5건 게이트 RMSE: 실습 설정 재학습 뒤 중앙"] = rng(per.gate5_ft.median())
    r["뒤 5건 게이트 RMSE: 강한 설정 재학습 뒤 중앙"] = rng(per.gate5_ftx.median())
    for tag, nm in (("frozen", "고정"), ("ft", "실습 설정 재학습"), ("ftx", "강한 설정 재학습"), ("level", "배율 보정")):
        r[f"다음 21일 RMSE 중앙: {nm}"] = rng(per[f"next_rmse_{tag}"].median())
        r[f"다음 21일 치우침% 중앙: {nm}"] = rng(per[f"next_bias_pct_{tag}"].median())
        r[f"다음 21일 |치우침%| 평균: {nm}"] = rng(per[f"next_bias_pct_{tag}"].apply(lambda s: s.abs().mean()))
    for tag, nm in (("ft", "실습 설정 재학습"), ("ftx", "강한 설정 재학습"), ("level", "배율 보정")):
        r[f"다음 21일 RMSE 가 고정보다 줄어든 시작일%: {nm}"] = rng(per.apply(lambda q: (q[f"next_rmse_{tag}"] < q.next_rmse_frozen).mean() * 100))
        r[f"다음 21일 RMSE 변화(뒤 - 전) 중앙 kWh: {nm}"] = rng(per.apply(lambda q: (q[f"next_rmse_{tag}"] - q.next_rmse_frozen).median()))
    r["재학습으로 예측이 움직인 크기(절댓값 평균 kWh) 중앙: 실습 설정"] = rng(per.next_absdiff_ft.median())
    r["재학습으로 예측이 움직인 크기(절댓값 평균 kWh) 중앙: 강한 설정"] = rng(per.next_absdiff_ftx.median())
    r["배율 보정 계수 중앙"] = "%.3f ~ %.3f" % (per.level_k.median().min(), per.level_k.median().max())
    rows.append(r)
T = pd.DataFrame(rows).set_index("배율").T
print(T.to_string())
T.to_csv(HERE / "t5_05_ft_summary.csv")

print("\n시드를 모은 값(시작일 x 시드)")
for f, g in D.groupby("factor", sort=False):
    print("  배율 %.2f: n=%d | 다음 21일 RMSE 평균 고정 %.1f, 실습 설정 %.1f, 강한 설정 %.1f, 배율 보정 %.1f | |치우침%%| 평균 고정 %.1f, 실습 설정 %.1f, 강한 설정 %.1f, 배율 보정 %.1f | 치우침%% 평균 고정 %+.1f, 실습 %+.1f, 강한 %+.1f, 보정 %+.1f" % (
        f, len(g), g.next_rmse_frozen.mean(), g.next_rmse_ft.mean(), g.next_rmse_ftx.mean(), g.next_rmse_level.mean(),
        g.next_bias_pct_frozen.abs().mean(), g.next_bias_pct_ft.abs().mean(), g.next_bias_pct_ftx.abs().mean(), g.next_bias_pct_level.abs().mean(),
        g.next_bias_pct_frozen.mean(), g.next_bias_pct_ft.mean(), g.next_bias_pct_ftx.mean(), g.next_bias_pct_level.mean()))
