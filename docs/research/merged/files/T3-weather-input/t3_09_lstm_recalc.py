"""t3_09: 실습 LSTM 수치를 저장된 예측 파일에서 다시 계산한다(새로 학습하지 않는다).

보완 조사 1(merged/gap1)과 ASOS 분석(asos/hadong_build/train_check)이 남긴 예측을 읽어
업로드 파일 세 개의 시험 RMSE 와, 겹치는 날로 맞춘 비교를 직접 계산한다.
"""
import glob
import numpy as np
import pandas as pd
import t3_common as c

pd.set_option("display.width", 250)


def rmse(y, p):
    y, p = np.asarray(y, float), np.asarray(p, float)
    return float(np.sqrt(np.mean((p - y) ** 2)))


print("[1] gap1/runs_practice 의 npz 구조")
z = np.load(c.GAP1 / "runs_practice" / "jma_s42.npz", allow_pickle=True)
print("  키:", list(z.keys()))
for k in z.keys():
    v = z[k]
    print("   ", k, getattr(v, "shape", None), v.dtype if hasattr(v, "dtype") else type(v))

res = {}
for tag in ["jma", "const", "asosproxy", "era_next", "era_next_asosrows"]:
    for f in sorted(glob.glob(str(c.GAP1 / "runs_practice" / f"{tag}_s4?.npz"))):
        z = np.load(f, allow_pickle=True)
        keys = list(z.keys())
        yk = [k for k in keys if k.lower() in ("y", "y_te", "y_test", "ytest", "y_true")]
        pk = [k for k in keys if k.lower() in ("pred", "p_te", "pred_te", "p", "yhat", "pred_test")]
        dk = [k for k in keys if "date" in k.lower()]
        if not (yk and pk):
            print("  예측 열을 찾지 못함:", f, keys)
            continue
        y, p = z[yk[0]].ravel(), z[pk[0]].ravel()
        dates = pd.to_datetime(z[dk[0]].ravel()) if dk else None
        seed = f.split("_s")[-1].replace(".npz", "")
        res[(tag, seed)] = pd.DataFrame({"date": dates, "y": y, "pred": p})
print("\n[2] 실습 절차 시험 RMSE(씨앗별)")
for tag in ["jma", "const", "asosproxy", "era_next", "era_next_asosrows"]:
    xs = [(s, rmse(d["y"], d["pred"]), len(d), d["date"].min(), d["date"].max()) for (t, s), d in res.items() if t == tag]
    if xs:
        vals = [x[1] for x in xs]
        print(f"  {tag:18s} " + ", ".join(f"s{s} {v:.2f}" for s, v, *_ in xs) + f" | 평균 {np.mean(vals):.2f} | n={xs[0][2]} ({xs[0][3].date()} ~ {xs[0][4].date()})")

print("\n[3] ASOS 쪽 예측 파일(train_check)")
for name in ["lag_gsr", "proxy_gsr", "lag_ss", "proxy_ss"]:
    d = pd.read_csv(c.ASOS / "hadong_build" / "train_check" / f"{name}_pred.csv")
    cols = list(d.columns)
    pc = [x for x in cols if x.startswith("pred")]
    yc = [x for x in cols if x in ("y", "actual", "y_true", "close")]
    dc = [x for x in cols if "date" in x.lower()]
    if not yc:
        print("  ", name, cols)
        continue
    vals = [rmse(d[yc[0]], d[k]) for k in pc]
    print(f"  {name:10s} 열 {cols} | " + ", ".join(f"{k} {v:.2f}" for k, v in zip(pc, vals)) + f" | 평균 {np.mean(vals):.2f} | n={len(d)} ({d[dc[0]].min()} ~ {d[dc[0]].max()})")

print("\n[4] 예보 파일로 학습한 실습 LSTM 을 같은 날짜의 규칙·7일 평균과 견줌(시험 264일)")
full = c.load_full().merge(c.load_prevruns_daily(), on="date", how="left").sort_values("date").reset_index(drop=True)
y = full["gen_kwh"]
ma7 = y.shift(1).rolling(7).mean()
rule = (y.shift(1).rolling(7).sum() / full["fc1_gsr"].shift(1).rolling(7).sum() * full["fc1_gsr"]).clip(lower=0)
ref = pd.DataFrame({"date": full["date"], "ma7": ma7, "rule": rule})
for (t, s), d in res.items():
    if t != "jma":
        continue
    m = d.merge(ref, on="date")
    bias = (m["pred"].sum() - m["y"].sum()) / m["y"].sum() * 100
    print(f"  jma s{s}: LSTM {rmse(m['y'], m['pred']):.2f} | 규칙 {rmse(m['y'], m['rule']):.2f} | 7일 평균 {rmse(m['y'], m['ma7']):.2f}"
          f" | LSTM/규칙 {rmse(m['y'], m['pred']) / rmse(m['y'], m['rule']):.3f} | LSTM/7일 평균 {rmse(m['y'], m['pred']) / rmse(m['y'], m['ma7']):.3f}"
          f" | 치우침 {bias:+.2f}% | 예측 최솟값 {m['pred'].min():.1f}")

print("\n[5] 서빙 변형 표(gap1/preds_serve_variants.csv): 관측으로 학습하고 서빙 때 예보를 넣은 경우")
sv = pd.read_csv(c.GAP1 / "preds_serve_variants.csv", parse_dates=["date"])
g = sv.groupby(["묶음", "모델", "방법", "시드"]).apply(lambda d: pd.Series({"rmse": rmse(d["y"], d["pred"]), "n": len(d), "d0": d["date"].min(), "d1": d["date"].max()}), include_groups=False).reset_index()
t = g.groupby(["묶음", "모델", "방법"]).agg(rmse_mean=("rmse", "mean"), rmse_min=("rmse", "min"), rmse_max=("rmse", "max"), seeds=("rmse", "size"), n=("n", "first"), d0=("d0", "first"), d1=("d1", "first")).reset_index()
print(t.round(2).to_string(index=False))
t.to_csv(c.HERE / "t3_09_serve_variants_recalc.csv", index=False)
