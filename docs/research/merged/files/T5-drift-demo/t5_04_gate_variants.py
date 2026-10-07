"""T5 대조 4: 기대 발전량 대비 하루 비율로 정지·부분 정지를 가르는 규칙의 한도별 성적과, 보류 구간의 길이.
정답표는 보완 조사 3 의 설비 이벤트 달력(이웃 발전소 대비로 만든 사후 표)이다. 기대 발전량은 그날의 광양 관측으로 계산한 사후 값이다."""
from pathlib import Path
import numpy as np, pandas as pd
S = Path(__file__).resolve().parents[2]
a = pd.read_csv(S / "asos" / "hadong_daily_full.csv", parse_dates=["date"]).set_index("date")
a = a.loc[:"2025-12-31"]
gen = a.gen_kwh.values; e = a.pi_expected_kwh.values
cal = pd.read_csv(S / "solar" / "ev" / "equipment_event_calendar.csv", encoding="utf-8-sig")
cal["date"] = pd.to_datetime(cal["날짜"]); cal["cat"] = cal["범주"].astype(str).str.split("_").str[0]
cat = cal.set_index("date").cat.reindex(a.index).fillna("-")
years = len(a) / 365.25
rows = []
for emin in (80, 50):
    for th in (0.5, 0.6, 0.65, 0.7):
        for K in (1, 2):
            fl = (e >= emin) & (gen < th * e)
            if K == 2:
                fl = fl & np.r_[False, fl[:-1]]
            r = dict(기대하한=emin, 한도=th, 연속=K, 켜진날=int(fl.sum()))
            for c, tot in (("A", 40), ("B", 10), ("C", 14)):
                r[f"{c}({tot})"] = int((fl & (cat == c).values).sum())
            oth = fl & ~cat.isin(["A", "B", "C", "C2", "D", "E"]).values
            r["그 밖"] = int(oth.sum()); r["그 밖 연간"] = round(oth.sum() / years, 1)
            rows.append(r)
print(pd.DataFrame(rows).to_string(index=False))
ok = ~np.isnan(e)
print("\n기대 발전량이 80kWh 이상인 날의 비율: %.1f%% (광양 관측이 있는 %d일 가운데). 절반 출력 14일의 기대 발전량:" % ((e[ok] >= 80).mean() * 100, ok.sum()),
      {str(d.date()): round(float(a.pi_expected_kwh[d]), 0) for d in a.index[(cat == "C").values]})
susp = a.pi_partial_suspect.values.astype(bool); idx = a.index; out = []; i = 0
while i < len(susp):
    if susp[i]:
        j = i
        while j + 1 < len(susp) and susp[j + 1]:
            j += 1
        out.append("%s~%s(%d일)" % (idx[i].date(), idx[j].date(), j - i + 1)); i = j + 1
    else:
        i += 1
print("보류(pi_partial_suspect) 구간:", out)
normal = (~cat.isin(["A", "B", "C", "C2", "D", "E"]).values) & ok & (e >= 80)
q = (gen / e)[normal]
print("설비 이벤트가 아닌 날(기대 80 이상, %d일)의 실제/기대 분포: 1%% %.2f, 5%% %.2f, 50%% %.2f, 95%% %.2f" % (normal.sum(), *np.percentile(q, [1, 5, 50, 95])))
