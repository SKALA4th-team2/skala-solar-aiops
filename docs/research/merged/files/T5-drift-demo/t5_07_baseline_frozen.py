"""T5 대조 5: (가) 배포 시점에 고정한 기준선(직전 365일 PI)으로 본 2021년 시연 배치의 편차, (나) '직전 365일 기준선, 7.5%' 규칙이 2015~2025 에 낸 경보 전체 목록."""
from pathlib import Path
import numpy as np, pandas as pd
S = Path(__file__).resolve().parents[2]
a = pd.read_csv(S / "asos" / "hadong_daily_full.csv", parse_dates=["date"]).set_index("date").loc[:"2025-12-31"]
gen = a.gen_kwh.values; e = a.pi_expected_kwh.values; valid = a.pi_valid.values.astype(bool); idx = a.index
gc = np.clip(gen, 0.5 * e, 1.5 * e)


def pi(a_, b_):
    m = (idx >= a_) & (idx <= b_) & valid
    return gc[m].sum() / e[m].sum(), int(m.sum())


print("(가) 기준선을 배포 시점에 고정: 학습 끝 날짜까지의 365일 PI")
for nm, tr_end, batches in (("사전 조사 날짜", "2020-12-31", [("정상", "2021-04-22", "2021-05-12"), ("전환", "2021-05-13", "2021-06-02"), ("드리프트", "2021-06-02", "2021-06-22")]),
                            ("ASOS 날짜", "2021-04-06", [("정상", "2021-04-27", "2021-05-17"), ("드리프트", "2021-06-07", "2021-06-27")]),
                            ("절충(학습 끝 2021-04-01)", "2021-04-01", [("정상", "2021-04-22", "2021-05-12"), ("드리프트", "2021-06-07", "2021-06-27")])):
    te = pd.Timestamp(tr_end); b, nb = pi(te - pd.Timedelta(days=364), te)
    out = []
    for lab, x, y in batches:
        p, n = pi(pd.Timestamp(x), pd.Timestamp(y)); out.append("%s 배치(대상 %s~%s) PI %.4f, 편차 %+.1f%%, 판정일 %d" % (lab, x, y, p, (p / b - 1) * 100, n))
    print("  %s: 기준선(%s 까지 365일, 판정일 %d) %.4f | " % (nm, tr_end, nb, b) + " | ".join(out))

print("\n(나) 직전 365일 기준선 규칙의 경보 전체(2015-01-01 ~ 2025-12-31)")


def pin(n):
    num = pd.Series(np.where(valid, gc, 0.0)).rolling(n, min_periods=1).sum().values
    den = pd.Series(np.where(valid, e, 0.0)).rolling(n, min_periods=1).sum().values
    k = pd.Series(valid.astype(float)).rolling(n, min_periods=1).sum().values
    p = np.where(k >= np.ceil(0.7 * n), num / np.where(den > 0, den, np.nan), np.nan)
    bn = pd.Series(np.where(valid, gc, 0.0)).rolling(365, min_periods=200).sum().shift(n).values
    bd = pd.Series(np.where(valid, e, 0.0)).rolling(365, min_periods=200).sum().shift(n).values
    return pd.Series(p / (bn / bd) - 1, index=idx)


for n, K in ((30, 3), (21, 3), (21, 1)):
    dv = pin(n).loc["2015-01-01":]
    for nm, fl in (("하락", (dv < -0.075)), ("상승", (dv > 0.075))):
        fl = (fl.astype(int).rolling(K).sum() >= K)
        f = fl.values; out = []; i = 0
        while i < len(f):
            if f[i]:
                j = i
                while j + 1 < len(f) and f[j + 1]:
                    j += 1
                out.append("%s~%s(%d일, 최대 %+.1f%%)" % (fl.index[i].date(), fl.index[j].date(), j - i + 1, (dv.iloc[i:j + 1].min() if nm == "하락" else dv.iloc[i:j + 1].max()) * 100)); i = j + 1
            else:
                i += 1
        print("  N=%d, %d일 연속, %s: %d회 %d일 | %s" % (n, K, nm, len(out), int(f.sum()), out))
