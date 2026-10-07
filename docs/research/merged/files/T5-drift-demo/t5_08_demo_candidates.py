"""T5 대조 6: 일사량 예보가 있는 2025년 구간에서 '주입 시연'의 후보 시작일을 고른다.
같은 시작일 s 에 대해 (1) 성능 지표 배치 편차(주입 없음, x0.86), (2) 실습 LSTM(일사량 예보 입력, 시드 3개)의 배치 21건 RMSE 배수와 재학습 전후 치우침을 한 표에 놓는다.
배치는 행 s ~ s+40, 대상 21일은 s+20 ~ s+40, 재학습 뒤 평가는 s+41 ~ s+61. 성능 지표의 기준선은 s 전날까지 365일의 PI."""
from pathlib import Path
import glob, numpy as np, pandas as pd
HERE = Path(__file__).resolve().parent; S = HERE.parents[1]
pd.set_option("display.width", 300); pd.set_option("display.max_rows", 200); pd.set_option("display.max_columns", 40)
a = pd.read_csv(S / "asos" / "hadong_daily_full.csv", parse_dates=["date"]).set_index("date").loc[:"2025-12-31"]
gen = a.gen_kwh.values.copy(); e = a.pi_expected_kwh.values; idx = a.index


def gate(g):
    outage = (g <= 0) | ((e >= 30) & (g < 0.3 * e)); low = ((e >= 80) & (g < 0.7 * e)) | outage
    susp = pd.Series(low.astype(float)).rolling(7, min_periods=1).sum().values >= 3
    return ~np.isnan(e) & (e > 0) & ~outage & ~susp


def dev(s, f):
    i0 = idx.get_loc(s); g = gen.copy(); g[i0:] *= f; v = gate(g); gc = np.clip(g, 0.5 * e, 1.5 * e)
    mb = v.copy(); mb[i0:] = False; mb[:i0 - 365] = False
    mt = np.zeros(len(g), bool); mt[i0 + 20:i0 + 41] = True; mt &= v
    return (gc[mt].sum() / e[mt].sum()) / (gc[mb].sum() / e[mb].sum()) - 1 if mt.sum() >= 15 else np.nan, int(mt.sum())


D = pd.concat([pd.read_csv(f) for f in sorted(glob.glob(str(HERE / "t5_02_ft_seed*.csv")))], ignore_index=True)
D["x"] = D.batch_rmse / D.train_rmse
rows = []
for s in sorted(D.start.unique()):
    st = pd.Timestamp(s)
    if st + pd.Timedelta(days=40) > pd.Timestamp("2025-12-31"):
        continue
    d0, n0 = dev(st, 1.0); d1, n1 = dev(st, 0.86)
    r = dict(시작일=s, 대상21일=f"{(st + pd.Timedelta(days=20)).date()}~{(st + pd.Timedelta(days=40)).date()}", PI편차_주입없음=round(d0 * 100, 1), PI편차_x086=round(d1 * 100, 1))
    for f, tag in ((1.0, "주입없음"), (0.86, "x086")):
        q = D[(D.start == s) & (D.factor == f)]
        r[f"RMSE배수_{tag}(시드 최소~최대)"] = "%.2f~%.2f" % (q.x.min(), q.x.max())
        r[f"RMSE배수최대_{tag}"] = q.x.max()
    q = D[(D.start == s) & (D.factor == 0.86)]
    r["다음21일 치우침% 고정(시드별)"] = "/".join("%+.0f" % v for v in q.next_bias_pct_frozen)
    r["다음21일 치우침% 재학습(시드별)"] = "/".join("%+.0f" % v for v in q.next_bias_pct_ft)
    r["치우침 절댓값이 세 시드 모두 줄어듦"] = bool((q.next_bias_pct_ft.abs() < q.next_bias_pct_frozen.abs()).all())
    r["다음21일 RMSE 고정→재학습(시드 평균)"] = "%.1f→%.1f" % (q.next_rmse_frozen.mean(), q.next_rmse_ft.mean())
    r["RMSE가 세 시드 모두 줄어듦"] = bool((q.next_rmse_ft < q.next_rmse_frozen).all())
    rows.append(r)
T = pd.DataFrame(rows)
T["깨끗한 후보"] = (T.PI편차_주입없음.abs() <= 7.5) & (T.PI편차_x086 < -7.5) & (T.RMSE배수최대_주입없음 <= 1.3) & (T.RMSE배수최대_x086 <= 1.3)
print(T.drop(columns=["RMSE배수최대_주입없음", "RMSE배수최대_x086"]).to_string(index=False))
print("\n시작일 %d개 가운데: 성능 지표가 주입 없음은 ±7.5%% 안, x0.86 은 -7.5%% 아래 %d개 | 그중 21건 RMSE 가 두 경우 모두 세 시드에서 1.3배 이하 %d개 | 그중 재학습 뒤 치우침 절댓값이 세 시드 모두 줄어듦 %d개, RMSE 도 세 시드 모두 줄어듦 %d개" % (
    len(T), int(((T.PI편차_주입없음.abs() <= 7.5) & (T.PI편차_x086 < -7.5)).sum()), int(T["깨끗한 후보"].sum()),
    int((T["깨끗한 후보"] & T["치우침 절댓값이 세 시드 모두 줄어듦"]).sum()), int((T["깨끗한 후보"] & T["치우침 절댓값이 세 시드 모두 줄어듦"] & T["RMSE가 세 시드 모두 줄어듦"]).sum())))
T.to_csv(HERE / "t5_08_demo_candidates.csv", index=False)
