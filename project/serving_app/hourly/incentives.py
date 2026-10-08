"""KPX July-2026 rule scenario, not a settlement or participation decision."""
from decimal import Decimal
import math

RULE_URL = 'https://www.kpx.or.kr/boardDownload.es?bid=0030&list_no=77795&seq=4'


def number(value):
    if not math.isfinite(float(value)) or float(value) < 0:
        raise ValueError('Expected finite nonnegative energy/capacity')
    return Decimal(str(value))


def evaluate(records, capacity_kw, coefficient=1):
    """Each row is one hour. Missing second forecast uses a declared single proxy.

    Compute the mean of the TWO absolute errors, never the error of their mean.
    Exclude unavailable/curtailed hours and utilization below 10% before rates.
    Monetary outputs remain scenarios even when two forecast columns are supplied.
    """
    if coefficient not in (1, .5):
        raise ValueError('Scenario coefficient must be 1 or 0.5')
    capacity = number(capacity_kw)
    if capacity == 0:
        raise ValueError('Positive nameplate capacity required')
    rows = []; eligible = []; proxy_count = 0
    for row in records:
        actual = number(row['actual']); first = number(row['predicted'])
        proxy = row.get('predicted_second') is None
        second = first if proxy else number(row['predicted_second'])
        proxy_count += int(proxy)
        valid = number(row.get('valid_capacity_kw', capacity_kw))
        if valid > capacity:
            raise ValueError('Valid capacity cannot exceed nameplate capacity')
        utilization = actual / valid * 100 if valid else None
        error = (abs(first-actual)+abs(second-actual))/2/valid*100 if valid else None
        reason = ('출력제어' if row.get('curtailed') else '고장·정비' if row.get('unavailable')
                  else '유효용량 없음' if not valid else '설비이용률 10% 미만' if utilization < 10 else None)
        rate = 0 if reason else 4 if error <= 4 else 3 if error <= 6 else 0
        item = dict(timestamp=row['timestamp'],actual_kwh=float(actual),predicted_kwh=float(first),
                    second_forecast_proxy=proxy,valid_capacity_kw=float(valid),
                    utilization_pct=float(utilization) if utilization is not None else None,
                    error_pct=float(error) if error is not None else None,eligible=reason is None,
                    exclusion_reason=reason,band='excluded' if reason else 'le4' if error<=4 else 'le6' if error<=6 else 'gt6',
                    base_rate_krw_per_kwh=rate,scenario_krw=float(actual*rate*Decimal(str(coefficient))))
        rows.append(item)
        if reason is None: eligible.append(item)
    n = len(eligible); le4 = sum(r['band']=='le4' for r in eligible); le6 = sum(r['band'] in ('le4','le6') for r in eligible)
    reasons = {}
    for r in rows:
        if r['exclusion_reason']:reasons[r['exclusion_reason']]=reasons.get(r['exclusion_reason'],0)+1
    return dict(rule_profile='kpx-2026-07-25-scenario-v1',rule_source=RULE_URL,settlement_confirmed=False,
                scope='과거 자료 재생 기반 모의 계산 · 실제 지급액/참여자격 판정 아님',
                assumptions=['실적 발전량을 정산용 전력거래량의 대용값으로 사용',
                             '출력제어·고장·정비 정보 미제공 시 없음으로 가정',
                             '제출시각 및 참여자격 미검증; 2026-07-25 공개 규칙 고정'],
                forecast_basis='single_forecast_proxy' if proxy_count else 'two_forecasts',
                second_forecast_proxy_hours=proxy_count,coefficient=coefficient,
                total_hours=len(rows),eligible_hours=n,excluded_hours=len(rows)-n,excluded_reasons=reasons,
                mean_error_pct=sum(r['error_pct'] for r in eligible)/n if n else None,
                le4_hours=le4,le6_hours=le6,between4and6_hours=le6-le4,over6_hours=n-le6,
                le4_pct=100*le4/n if n else None,le6_pct=100*le6/n if n else None,
                eligible_energy_kwh=sum(r['actual_kwh'] for r in eligible),
                scenario_krw=round(sum(r['scenario_krw'] for r in rows),2),rows=rows)
