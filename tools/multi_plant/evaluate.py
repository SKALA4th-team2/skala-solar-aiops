"""발전소별 오차와 포트폴리오 합계의 오차를 같은 대상일에서 함께 낸다. 단순 기준 예측과 견준다.

무엇을 견주는가:
    - 기준 예측 둘: 전일값(어제의 하루 발전량), 7일 평균(직전 7일의 평균). 둘 다 학습이 없고 과거 값만 쓴다.
    - --predictions 를 주면 모델의 예측도 같은 대상일에서 견준다.
      파일의 열: plant_id, target_date, predicted_kwh  (model_id 등 다른 열은 읽지 않는다)

무엇을 내는가 (단위: 하루 kWh):
    - 발전소별: RMSE, MAE, 합계 오차율(절대오차의 합 ÷ 실제의 합), 치우침, 용량 1kW 당 RMSE
    - 포트폴리오: 같은 대상일의 예측 합계와 실제 합계의 RMSE, MAE, 합계 오차율, 치우침
    - 발전소별 RMSE 의 합(틀린 계산)과 포트폴리오 RMSE 를 나란히 놓는다. 오차가 서로 지워지면 합계의 오차만 작아진다
    - 발전소 평균(작은 발전소도 같은 무게)과 발전량 가중(큰 발전소가 무겁다) 지표
    - 커버리지: 기간의 날 수, 함께 평가한 대상일, 빠진 날과 빠진 발전소

읽을 때 주의할 것:
    - 대상일은 모든 구성원이 값을 가진 날만 쓴다. 일부 발전소만 더한 값을 포트폴리오 합계라고 부르지 않는다.
    - 기간이 구성 변경을 걸치면 멈춘다. 구성이 바뀐 앞뒤는 발전소 집합이 달라 그대로 견줄 수 없다.
    - "용량 1kW 당 RMSE" 는 크기가 다른 발전소를 견주려는 값이다. 제도의 오차율이 아니다.
    - --hourly 의 값은 제도의 식(시간대별, 설비 용량 분모, 이용률 10% 이상)을 **단순 기준 예측**에 적용한 참고값이다.
      우리 모델의 값도, 정산 성능도 아니다. 하루 합계를 24칸으로 나눈 값은 여기서 만들지 않는다.

실행 (저장소 루트에서. 표준 라이브러리만 쓴다):
    python tools/multi_plant/evaluate.py --data-root <자료 폴더> --portfolio <portfolio_id> --start YYYY-MM-DD --end YYYY-MM-DD \
        [--predictions <예측 CSV>] [--members a,b,c] [--hourly] [--json <결과 파일>]
"""
import argparse
import json
import math
import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C  # noqa: E402

BASELINES = ("persistence", "ma7")
LABEL = {"persistence": "전일값", "ma7": "7일 평균", "model": "모델"}


def baseline_daily(series):
    """{날짜: 값}에서 기준 예측 둘을 만든다. 필요한 과거 값이 하나라도 없으면 그날은 만들지 않는다."""
    pers, ma7 = {}, {}
    for d in series:
        prev = [series.get(d - timedelta(days=k)) for k in range(1, 8)]
        if prev[0] is not None:
            pers[d] = prev[0]
        if all(v is not None for v in prev):
            ma7[d] = sum(prev) / 7
    return {"persistence": pers, "ma7": ma7}


def metrics(actual, predicted, capacity_kw=None):
    n = len(actual)
    err = [p - a for a, p in zip(actual, predicted)]
    total = sum(actual)
    out = {
        "n": n,
        "rmse_kwh": math.sqrt(sum(e * e for e in err) / n),
        "mae_kwh": sum(abs(e) for e in err) / n,
        "wape_pct": sum(abs(e) for e in err) / total * 100 if total > 0 else None,
        "bias_pct": sum(err) / total * 100 if total > 0 else None,
        "mean_actual_kwh": total / n,
    }
    out["rmse_per_kw"] = out["rmse_kwh"] / capacity_kw if capacity_kw else None
    return out


def read_predictions(path):
    headers, rows = C.read_csv(path)
    need = ["plant_id", "target_date", "predicted_kwh"]
    if any(c not in headers for c in need):
        raise SystemExit(f"{path}: 열 {need} 가 있어야 한다")
    out = {}
    for n, r in enumerate(rows, start=2):
        d = C.parse_date(r["target_date"])
        v = C.parse_number(r["predicted_kwh"])
        if d is None or v is None:
            raise SystemExit(f"{path}:{n}: target_date 나 predicted_kwh 를 읽을 수 없다")
        if d in out.setdefault(r["plant_id"].strip(), {}):
            raise SystemExit(f"{path}:{n}: {r['plant_id']} {d} 의 예측이 두 번 있다")
        out[r["plant_id"].strip()][d] = v
    return out


def evaluate_daily(loaded, members, start, end, predictions=None):
    plants = loaded["plants"]
    series = {p: C.daily_series(loaded["daily"][p]) for p in members if p in loaded["daily"]}
    no_data = [p for p in members if p not in series]
    result = {"members": members, "members_without_data": no_data}
    if no_data:
        result["status"] = "not_evaluable"
        result["reason"] = "자료가 없는 구성원이 있어 포트폴리오 합계를 만들 수 없다"
        return result
    base = {p: baseline_daily(series[p]) for p in members}
    own = {p: {d for d in series[p] if start <= d <= end and series[p][d] is not None
               and all(d in base[p][b] for b in BASELINES)} for p in members}
    common = sorted(set.intersection(*own.values()))
    days = (end - start).days + 1
    coverage = {
        "period_days": days,
        "common_target_days": len(common),
        "first_target": common[0].isoformat() if common else None,
        "last_target": common[-1].isoformat() if common else None,
        "excluded_days": days - len(common),
        "per_plant_own_target_days": {p: len(own[p]) for p in members},
        "per_plant_days_lost_to_others": {p: len(own[p]) - len(common) for p in members},
    }
    result["coverage"] = coverage
    if not common:
        result["status"] = "not_evaluable"
        result["reason"] = "모든 구성원이 값을 가진 대상일이 없다"
        return result

    methods = {b: {p: base[p][b] for p in members} for b in BASELINES}
    model_days = common
    if predictions is not None:
        lacking = [p for p in members if p not in predictions]
        coverage["model_members_without_predictions"] = lacking
        if lacking:
            coverage["model_status"] = "partial"
            coverage["model_note"] = "예측이 없는 구성원이 있어 모델의 포트폴리오 합계를 내지 않는다. 일부만 더한 값은 합계가 아니다"
        else:
            model_days = [d for d in common if all(d in predictions[p] for p in members)]
            coverage["model_status"] = "ok" if len(model_days) == len(common) else "restricted"
            coverage["model_target_days"] = len(model_days)
            coverage["model_days_without_predictions"] = len(common) - len(model_days)
            if model_days:
                methods["model"] = {p: predictions[p] for p in members}
    # 모델이 일부 날짜만 가지면, 견주는 모든 방법을 그 날짜로 맞춘다
    eval_days = model_days if "model" in methods else common
    coverage["evaluated_days"] = len(eval_days)

    caps = {p: C.capacity_kw_at(plants, p, eval_days[0]) for p in members}
    cap_total = sum(caps.values()) if all(c is not None for c in caps.values()) else None
    per_plant = {p: {"capacity_kw": caps[p], "methods": {}} for p in members}
    portfolio = {"capacity_kw": cap_total, "methods": {}}
    averages = {}
    actual_sum = [sum(series[p][d] for p in members) for d in eval_days]
    for m, pred in methods.items():
        for p in members:
            per_plant[p]["methods"][m] = metrics([series[p][d] for d in eval_days], [pred[p][d] for d in eval_days], caps[p])
        pm = metrics(actual_sum, [sum(pred[p][d] for p in members) for d in eval_days], cap_total)
        rmses = [per_plant[p]["methods"][m]["rmse_kwh"] for p in members]
        pm["sum_of_plant_rmse_kwh"] = sum(rmses)
        pm["root_sum_square_plant_rmse_kwh"] = math.sqrt(sum(r * r for r in rmses))
        pm["rmse_over_sum_of_plant_rmse"] = pm["rmse_kwh"] / sum(rmses) if sum(rmses) > 0 else None
        portfolio["methods"][m] = pm
        abs_err = sum(abs(pred[p][d] - series[p][d]) for p in members for d in eval_days)
        per_kw = [per_plant[p]["methods"][m]["rmse_per_kw"] for p in members]
        wapes = [per_plant[p]["methods"][m]["wape_pct"] for p in members]
        averages[m] = {
            "plant_mean_rmse_per_kw": sum(per_kw) / len(per_kw) if all(v is not None for v in per_kw) else None,
            "plant_mean_wape_pct": sum(wapes) / len(wapes) if all(v is not None for v in wapes) else None,
            "energy_weighted_wape_pct": abs_err / sum(actual_sum) * 100 if sum(actual_sum) > 0 else None,
            "portfolio_wape_pct": pm["wape_pct"],
        }
    result.update({"status": "ok", "per_plant": per_plant, "portfolio": portfolio, "averages": averages})
    return result


def evaluate_hourly(loaded, members, start, end):
    """제도의 식을 단순 기준 예측(어제 같은 시각 값, 직전 7일 같은 시각 평균)에 적용한 참고값."""
    plants, hourly = loaded["plants"], loaded["hourly"]
    lacking = [p for p in members if p not in hourly]
    if lacking:
        return {"status": "not_evaluable", "reason": "시간대별 자료가 없는 구성원이 있다", "members_without_hourly": lacking}

    def full(p, d):
        slots = hourly[p].get(d)
        return slots is not None and all(v is not None for v in slots)

    own = {}
    for p in members:
        own[p] = {d for d in hourly[p] if start <= d <= end and all(full(p, d - timedelta(days=k)) for k in range(0, 8))}
    common = sorted(set.intersection(*own.values()))
    if not common:
        return {"status": "not_evaluable", "reason": "모든 구성원이 직전 7일까지 시간대별 값을 가진 날이 없다"}
    caps = {p: C.capacity_kw_at(plants, p, common[0]) for p in members}
    if any(c is None for c in caps.values()):
        return {"status": "not_evaluable", "reason": "용량을 모르는 구성원이 있어 분모를 만들 수 없다"}

    def forecast(p, d, kind):
        if kind == "persistence":
            return hourly[p][d - timedelta(days=1)]
        return [sum(hourly[p][d - timedelta(days=k)][h] for k in range(1, 8)) / 7 for h in range(24)]

    def score(actual_rows, forecast_rows, cap):
        errs, energy = [], 0.0
        for a_row, f_row in zip(actual_rows, forecast_rows):
            for a, f in zip(a_row, f_row):
                if a >= 0.1 * cap:              # 설비이용률 10% 이상인 시간대만
                    errs.append(abs(f - a) / cap * 100)
                    energy += a
        if not errs:
            return None
        errs.sort()
        return {"eligible_hours": len(errs), "mean_error_pct": sum(errs) / len(errs), "median_error_pct": errs[len(errs) // 2],
                "share_le_4pct": sum(1 for e in errs if e <= 4) / len(errs) * 100,
                "share_le_6pct": sum(1 for e in errs if e <= 6) / len(errs) * 100, "eligible_energy_kwh": energy}

    out = {"status": "ok", "days": len(common), "first_day": common[0].isoformat(), "last_day": common[-1].isoformat(),
           "capacity_kw": {**caps, "_portfolio": sum(caps.values())}, "per_plant": {p: {} for p in members}, "portfolio": {},
           "note": "단순 기준 예측에 제도의 식을 적용한 참고값. 정지일을 건너뛰지 않았다. 유효 용량(고장·정비·출력제어를 뺀 용량)이 아니라 등록부의 설비 용량을 분모로 썼다"}
    for kind in BASELINES:
        fc = {p: [forecast(p, d, kind) for d in common] for p in members}
        for p in members:
            out["per_plant"][p][kind] = score([hourly[p][d] for d in common], fc[p], caps[p])
        a_sum = [[sum(hourly[p][d][h] for p in members) for h in range(24)] for d in common]
        f_sum = [[sum(fc[p][i][h] for p in members) for h in range(24)] for i in range(len(common))]
        out["portfolio"][kind] = score(a_sum, f_sum, sum(caps.values()))
    return out


def resolve_members(loaded, portfolio_id, start, end, override=None):
    if override:
        return None, override
    v1, m1 = C.members_at(loaded["members"], portfolio_id, start)
    v2, m2 = C.members_at(loaded["members"], portfolio_id, end)
    if v1 is None or v2 is None:
        raise SystemExit(f"{portfolio_id}: {start} 나 {end} 에 적용되는 구성이 없다")
    if v1 != v2:
        raise SystemExit(f"{portfolio_id}: 기간이 구성 변경을 걸친다(v{v1} → v{v2}). 구성 버전별로 기간을 나누거나, "
                         "앞뒤를 같은 발전소 집합으로 견주려면 --members 로 발전소를 고정한다")
    return v1, m1


def f(v, digits=2):
    return "-" if v is None else f"{v:.{digits}f}"


def render(result):
    d = result["daily"]
    lines = [f"포트폴리오 {result['portfolio_id']} (구성 v{result['composition_version']}), 기간 {result['start']} ~ {result['end']}",
             f"구성원: {', '.join(d['members'])}"]
    if d["status"] != "ok":
        lines.append(f"평가하지 않음: {d['reason']}" + (f" ({', '.join(d['members_without_data'])})" if d.get("members_without_data") else ""))
        return "\n".join(lines)
    c = d["coverage"]
    lines.append(f"[커버리지] 기간 {c['period_days']}일 가운데 함께 평가한 대상일 {c['evaluated_days']}일 ({c['first_target']} ~ {c['last_target']}), 빠진 날 {c['period_days'] - c['evaluated_days']}일")
    if "model_status" in c:
        lines.append(f"  모델 예측: {c['model_status']}" + (f", 예측이 없는 구성원 {', '.join(c['model_members_without_predictions'])}" if c.get("model_members_without_predictions") else "")
                     + (f", 예측이 없어 빠진 날 {c['model_days_without_predictions']}일" if c.get("model_days_without_predictions") else ""))
    for m in d["portfolio"]["methods"]:
        lines.append(f"[{LABEL[m]}] (하루 kWh)")
        for p, info in d["per_plant"].items():
            x = info["methods"][m]
            lines.append(f"  {p:<24} 용량 {f(info['capacity_kw'], 2)}kW  RMSE {f(x['rmse_kwh'])}  MAE {f(x['mae_kwh'])}  합계 오차율 {f(x['wape_pct'])}%  치우침 {f(x['bias_pct'])}%  1kW 당 RMSE {f(x['rmse_per_kw'], 3)}")
        x = d["portfolio"]["methods"][m]
        lines.append(f"  {'포트폴리오 합계':<17} 용량 {f(d['portfolio']['capacity_kw'], 2)}kW  RMSE {f(x['rmse_kwh'])}  MAE {f(x['mae_kwh'])}  합계 오차율 {f(x['wape_pct'])}%  치우침 {f(x['bias_pct'])}%  1kW 당 RMSE {f(x['rmse_per_kw'], 3)}")
        lines.append(f"  발전소별 RMSE 를 그냥 더한 값 {f(x['sum_of_plant_rmse_kwh'])} (포트폴리오 RMSE 가 아니다). 포트폴리오 RMSE 는 그 {f(x['rmse_over_sum_of_plant_rmse'] * 100, 1)}%")
        a = d["averages"][m]
        lines.append(f"  발전소 평균 합계 오차율 {f(a['plant_mean_wape_pct'])}%, 발전량 가중 {f(a['energy_weighted_wape_pct'])}%, 합계끼리 견준 값 {f(a['portfolio_wape_pct'])}%, 발전소 평균 1kW 당 RMSE {f(a['plant_mean_rmse_per_kw'], 3)}")
    h = result.get("hourly")
    if h:
        lines.append("[제도의 식을 단순 기준 예측에 적용한 참고값] 시간대별 |예측 − 실제| ÷ 설비 용량, 이용률 10% 이상인 시간대")
        if h["status"] != "ok":
            lines.append(f"  계산하지 않음: {h['reason']}")
        else:
            lines.append(f"  {h['days']}일 ({h['first_day']} ~ {h['last_day']}). {h['note']}")
            for kind in BASELINES:
                for p in d["members"]:
                    x = h["per_plant"][p][kind]
                    lines.append(f"  {LABEL[kind]:<6} {p:<24} 평균 {f(x['mean_error_pct'])}%  4% 이하 {f(x['share_le_4pct'], 1)}%  6% 이하 {f(x['share_le_6pct'], 1)}%  대상 {x['eligible_hours']}시간")
                x = h["portfolio"][kind]
                lines.append(f"  {LABEL[kind]:<6} {'포트폴리오 합계':<17} 평균 {f(x['mean_error_pct'])}%  4% 이하 {f(x['share_le_4pct'], 1)}%  6% 이하 {f(x['share_le_6pct'], 1)}%  대상 {x['eligible_hours']}시간")
    return "\n".join(lines)


def run(loaded, portfolio_id, start, end, predictions=None, members_override=None, hourly=False):
    version, members = resolve_members(loaded, portfolio_id, start, end, members_override)
    result = {"schema_version": C.SCHEMA_VERSION, "portfolio_id": portfolio_id, "composition_version": version,
              "start": start.isoformat(), "end": end.isoformat(),
              "daily": evaluate_daily(loaded, members, start, end, predictions)}
    if hourly:
        result["hourly"] = evaluate_hourly(loaded, members, start, end)
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--data-root", type=Path, required=True)
    p.add_argument("--portfolio", required=True)
    p.add_argument("--start", required=True)
    p.add_argument("--end", required=True)
    p.add_argument("--predictions", type=Path)
    p.add_argument("--members", help="쉼표로 나눈 plant_id. 구성 대신 이 집합으로 평가한다")
    p.add_argument("--hourly", action="store_true")
    p.add_argument("--json", type=Path)
    a = p.parse_args()

    loaded = C.load_root(a.data_root)
    blocking = C.errors_of(loaded["issues"])
    for i in blocking:
        print(f"[오류] {i['code']}  {i['where']}  {i['message']}")
    if blocking:
        print("자료에 오류가 있어 평가하지 않는다. 먼저 validate.py 로 고친다.")
        sys.exit(1)
    start, end = C.parse_date(a.start), C.parse_date(a.end)
    if start is None or end is None or end < start:
        raise SystemExit("--start, --end 는 YYYY-MM-DD 이고 순서가 맞아야 한다")
    override = [s.strip() for s in a.members.split(",")] if a.members else None
    predictions = read_predictions(a.predictions) if a.predictions else None
    result = run(loaded, a.portfolio, start, end, predictions, override, a.hourly)
    print(render(result))
    if a.json:
        a.json.parent.mkdir(parents=True, exist_ok=True)
        a.json.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
