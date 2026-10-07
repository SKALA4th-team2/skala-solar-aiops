# T6 (제도의 현재 상태와 시나리오의 규칙상 근거) 다시 계산.
# 입력: 발전 실적 원본 CSV(CP949)만 쓴다. project 모듈은 import 하지 않는다.
# 실행: PYTHONDONTWRITEBYTECODE=1 /Users/psm/workspace/skala-aiops/mlflow/.venv/bin/python T6_recalc.py > out_recalc.txt
#
# 날짜 표기: D = 거래일(맞히려는 날), D-1 = 예측값을 제출하는 날, D-2 = 그 전날.
# 시간 열 h 는 (h-1)시~h시 구간으로 본다(사전 조사 D1 의 결론. 전력시장운영규칙의 거래시간 표기와 같다).
# 시간값은 kWh 로 읽는다(공공데이터의 열 이름은 kw 다. 사전 조사 D1 의 판단을 따른 가정이다).
import json
import numpy as np
import pandas as pd

SRC = '(작업 폴더)/solar/data_15043409.csv'
OUT_JSON = '(작업 폴더)/merged/T6-scheme/out_recalc.json'
res = {}

df = pd.read_csv(SRC, encoding='cp949')
df['d'] = pd.to_datetime(df['년월일'])
df = df.sort_values('d').reset_index(drop=True)
hours = [str(i) for i in range(1, 25)]
H = df[hours].apply(pd.to_numeric, errors='coerce')
tot_col = pd.to_numeric(df['총량(kw)'], errors='coerce')
full = pd.date_range(df['d'].min(), df['d'].max(), freq='D')
print('== 0. 원자료 점검')
print('행 수', len(df), '| 기간', df['d'].min().date(), '~', df['d'].max().date(), '| 달력 일수', len(full),
      '| 빠진 날짜', len(full) - df['d'].nunique(), '| 중복 날짜', int(df['d'].duplicated().sum()))
print('총량 열과 시간값 합의 최대 차이', float((tot_col - H.sum(axis=1)).abs().max()), '| 시간값 결측', int(H.isna().sum().sum()))
print('시간값 최대', float(H.max().max()), '| 일 합계 중앙값', round(float(tot_col.median()), 1), '| 일 합계 평균', round(float(tot_col.mean()), 1))
Hm = H.set_index(df['d']).reindex(full)          # 날짜 연속 격자
A = Hm.to_numpy(dtype=float)                      # (일, 24)
tot = np.nansum(A, axis=1); tot[np.isnan(A).all(axis=1)] = np.nan
dates = full
res['basic'] = {'rows': int(len(df)), 'start': str(df['d'].min().date()), 'end': str(df['d'].max().date()),
                'missing_dates': int(len(full) - df['d'].nunique()), 'hour_max': float(H.max().max()),
                'daily_median': float(tot_col.median())}

# ---------------------------------------------------------------------------
print('\n== 1. 하동 한 곳의 묶음 내 비중과 예측제도 정산금 상한(과거 실적만 쓴 산수)')
for cap in (55.0, 50.0):
    print(f'  용량 {cap:.0f}kW ÷ 20MW = {cap/20000*100:.3f}%')
yrs = pd.Series(tot, index=dates).groupby(dates.year)
cnt = yrs.count(); full_years = [y for y in cnt.index if cnt[y] >= 360]
print('  완전한 해:', full_years[0], '~', full_years[-1], f'({len(full_years)}개)')
res['settle_cap'] = {}
for cap in (55.0, 50.0):
    elig = np.where(A >= 0.1 * cap, A, 0.0).sum(axis=1)
    ey = pd.Series(elig, index=dates).groupby(dates.year).sum()
    m = float(ey[full_years].mean())
    print(f'  용량 {cap:.0f}kW: 이용률 10% 이상 시간대 발전량 연평균 {m:,.0f}kWh. 전부 4원이면 연 {m*4:,.0f}원, 전부 3원이면 연 {m*3:,.0f}원')
    res['settle_cap'][str(int(cap))] = {'elig_kwh_per_year': m, 'krw_at_4': m * 4, 'krw_at_3': m * 3}
allm = float(yrs.sum()[full_years].mean())
print(f'  참고: 전체 발전량 연평균 {allm:,.0f}kWh. 4원이면 연 {allm*4:,.0f}원. 일 합계 중앙값 {float(tot_col.median()):.1f}×365×4 = {float(tot_col.median())*365*4:,.0f}원')
res['settle_cap']['all_kwh_per_year'] = allm

# ---------------------------------------------------------------------------
print('\n== 2. 제출 시각에 D-1 의 하루 발전량이 얼마나 끝나 있는가 (열 h = (h-1)~h시 가정, 계량값이 즉시 들어온다는 가정)')
ok = (tot >= 1.0)
with np.errstate(invalid="ignore", divide="ignore"):
    cum = np.cumsum(A, axis=1) / tot[:, None]
res['cum_share'] = {}
print('  대상: 일 합계 1kWh 이상', int(ok.sum()), '일')
print('  시각   일별 비중의 평균  중앙값   하위5%   발전량 가중(전체 합 기준)')
for h in (10, 14, 17, 18, 19, 20):
    s = cum[ok, h - 1]
    w = float(np.nansum(A[ok, :h]) / np.nansum(A[ok]))
    print(f'  {h:>2}시   {s.mean()*100:8.1f}%   {np.median(s)*100:6.1f}%  {np.quantile(s, .05)*100:6.1f}%   {w*100:6.1f}%')
    res['cum_share'][str(h)] = {'mean': float(s.mean()), 'median': float(np.median(s)), 'p05': float(np.quantile(s, .05)), 'energy_weighted': w}
print('  월별: 17시까지 끝난 비중(발전량 가중) / 20시까지')
mon = dates.month.to_numpy()
res['cum_share_month'] = {}
for m in range(1, 13):
    k = ok & (mon == m)
    w17 = float(np.nansum(A[k, :17]) / np.nansum(A[k])); w20 = float(np.nansum(A[k, :20]) / np.nansum(A[k])); w10 = float(np.nansum(A[k, :10]) / np.nansum(A[k])); w14 = float(np.nansum(A[k, :14]) / np.nansum(A[k]))
    print(f'   {m:>2}월  10시 {w10*100:5.1f}%  14시 {w14*100:5.1f}%  17시 {w17*100:5.1f}%  20시 {w20*100:6.2f}%')
    res['cum_share_month'][str(m)] = {'10': w10, '14': w14, '17': w17, '20': w20}

# ---------------------------------------------------------------------------
def lagmean(x, a, b):
    """x[T-a .. T-b] 의 평균(일 단위). 결측이 끼면 NaN."""
    out = np.full(len(x), np.nan)
    for T in range(a, len(x)):
        w = x[T - a:T - b + 1]
        if not np.isnan(w).any():
            out[T] = w.mean()
    return out

WINDOWS = {
    'ASOS 분할 A 평가 구간(2023-05-31~2025-12-31)': ('2023-05-31', '2025-12-31'),
    '사전 조사 D2 평가 구간(2023-07-17~2026-02-28)': ('2023-07-17', '2026-02-28'),
}
print('\n== 3. 일 단위 대리 지표: MAE ÷ (용량 × 24시간) 이 단순 예측을 걸러 내는가 (미래 정보 없음)')
res['daily_proxy'] = {}
preds_def = {
    '학습 구간 평균(상수)': None,
    '어제 값(D-1)': lambda: lagmean(tot, 1, 1),
    '7일 평균(D-7~D-1)': lambda: lagmean(tot, 7, 1),
    '20일 평균(D-20~D-1)': lambda: lagmean(tot, 20, 1),
    '그저께 값(D-2)': lambda: lagmean(tot, 2, 2),
    '7일 평균(D-8~D-2)': lambda: lagmean(tot, 8, 2),
    '20일 평균(D-21~D-2)': lambda: lagmean(tot, 21, 2),
}
dnp = dates.to_numpy()
for wname, (s, e) in WINDOWS.items():
    te = (dates >= s) & (dates <= e) & ~np.isnan(tot)
    tr = (dates < s) & ~np.isnan(tot)
    print(f'  [{wname}] 평가 {int(te.sum())}일, 실제 하루 평균 {np.nanmean(tot[te]):.1f}kWh')
    print('   예측                     RMSE    MAE   실제합계대비%  용량50×24h%  용량55×24h%  | 55kW 기준 일별 |오차|÷(용량×24h): 4%이하 / 4~6% / 6%초과 인 날의 비율')
    res['daily_proxy'][wname] = {}
    for pname, f in preds_def.items():
        p = np.full(len(tot), float(np.nanmean(tot[tr]))) if f is None else f()
        k = te & ~np.isnan(p)
        err = p[k] - tot[k]
        rmse = float(np.sqrt(np.mean(err ** 2))); mae = float(np.mean(np.abs(err)))
        wape = float(np.abs(err).sum() / tot[k].sum() * 100)
        b50 = mae / (50 * 24) * 100; b55 = mae / (55 * 24) * 100
        r = np.abs(err) / (55 * 24) * 100
        sh = (float((r <= 4).mean()), float(((r > 4) & (r <= 6)).mean()), float((r > 6).mean()))
        print(f'   {pname:<22}{rmse:7.2f}{mae:7.2f}{wape:12.2f}{b50:12.2f}{b55:12.2f}        {sh[0]*100:5.1f}% / {sh[1]*100:5.1f}% / {sh[2]*100:5.1f}%')
        res['daily_proxy'][wname][pname] = {'n': int(k.sum()), 'rmse': rmse, 'mae': mae, 'wape_pct': wape, 'cap50x24_pct': b50, 'cap55x24_pct': b55,
                                            'share_le4': sh[0], 'share_4to6': sh[1], 'share_gt6': sh[2]}

# ---------------------------------------------------------------------------
print('\n== 4. 제도 식(시간대별, 설비용량 분모, 이용률 10% 이상 시간대만)을 하동 한 곳에 그대로 적용한 가상 계산')
print('   실제 정산은 20MW 초과 묶음 단위다. 아래는 한 곳만 떼어 계산한 값이라 묶음의 오차율과 같지 않다.')

def hour_lag(a, b):
    """같은 시각의 D-a..D-b 평균. shape (일, 24)."""
    out = np.full(A.shape, np.nan)
    for T in range(a, len(A)):
        w = A[T - a:T - b + 1]
        if not np.isnan(w).any():
            out[T] = w.mean(axis=0)
    return out

def profile_alloc(total_pred, a=20, b=1):
    """하루 합계 예측을 직전 20일(D-20..D-1)의 평균 시간 분포로 나눈다. 분포에는 대상일 값을 쓰지 않는다."""
    out = np.full(A.shape, np.nan)
    for T in range(a, len(A)):
        w = A[T - a:T - b + 1]
        if np.isnan(w).any() or np.isnan(total_pred[T]):
            continue
        s = w.sum()
        if s <= 0:
            continue
        out[T] = total_pred[T] * w.sum(axis=0) / s
    return out

def fp(rate):
    return np.where(rate <= 4, 4.0, np.where(rate <= 6, 3.0, 0.0))

def scheme(P1, P2, te, cap):
    """1차 예측 P1, 2차 예측 P2 로 차수별 오차율과 평균 오차율을 구한다."""
    k = te[:, None] & (A >= 0.1 * cap) & ~np.isnan(P1) & ~np.isnan(P2)
    a = A[k]
    f1 = np.abs(P1[k] - a) / cap * 100; f2 = np.abs(P2[k] - a) / cap * 100; f = (f1 + f2) / 2
    unit = float((a * fp(f)).sum() / a.sum())
    return {'n_hours': int(k.sum()), 'fer1': float(f1.mean()), 'fer2': float(f2.mean()), 'fer_avg': float(f.mean()),
            'share_le4': float((f <= 4).mean()), 'share_4to6': float(((f > 4) & (f <= 6)).mean()), 'share_gt6': float((f > 6).mean()),
            'krw_per_kwh': unit, 'elig_kwh': float(a.sum())}

P_d1 = hour_lag(1, 1); P_d2 = hour_lag(2, 2); P_7a = hour_lag(7, 1); P_7b = hour_lag(8, 2)
P_perfect = profile_alloc(tot)                         # 대상일 실제 합계를 씀(예측 시점에 받을 수 없는 값)
P_m20a = profile_alloc(lagmean(tot, 20, 1))            # 20일 평균(D-20..D-1)을 분포로 나눔
P_m20b = profile_alloc(lagmean(tot, 21, 2), a=21, b=2) # 1차 제출용: D-21..D-2 만 씀
CASES = {
    '1차 = 그저께 같은 시각 값, 2차 = 어제 같은 시각 값': (P_d2, P_d1, False),
    '1차·2차 모두 어제 같은 시각 값(2차 변경 제출 수준의 정보를 1차에도 썼다고 가정, 1차에는 불가능)': (P_d1, P_d1, True),
    '1차 = 7일 같은 시각 평균(D-8~D-2), 2차 = 7일 같은 시각 평균(D-7~D-1)': (P_7b, P_7a, False),
    '1차 = 20일 평균 합계(D-21~D-2)를 시간 분포로 나눔, 2차 = 20일 평균 합계(D-20~D-1)를 시간 분포로 나눔': (P_m20b, P_m20a, False),
    '하루 합계를 완벽히 맞히고 직전 20일 시간 분포로 나눔(대상일 실제 합계 사용)': (P_perfect, P_perfect, True),
}
res['scheme_single_site'] = {}
for wname, (s, e) in WINDOWS.items():
    te = np.asarray((dates >= s) & (dates <= e))
    res['scheme_single_site'][wname] = {}
    for cap in (55.0, 50.0):
        print(f'  [{wname}] 용량 {cap:.0f}kW')
        print('   예측 방식: 1차 오차율 / 2차 오차율 / 평균 오차율(%) | 평균 오차율이 4%이하 / 4~6% / 6%초과 인 시간대 비율 | kWh당 평균 단가(원) | 대상 시간대 수')
        res['scheme_single_site'][wname][str(int(cap))] = {}
        for cname, (P1, P2, fut) in CASES.items():
            r = scheme(P1, P2, te, cap)
            tag = ' [예측 시점에 받을 수 없는 값을 씀]' if fut else ''
            print(f'   {cname}{tag}')
            print(f'       {r["fer1"]:6.2f} / {r["fer2"]:6.2f} / {r["fer_avg"]:6.2f} | {r["share_le4"]*100:5.1f}% / {r["share_4to6"]*100:5.1f}% / {r["share_gt6"]*100:5.1f}% | {r["krw_per_kwh"]:.2f} | {r["n_hours"]}')
            r['uses_info_not_available_at_forecast_time'] = fut
            res['scheme_single_site'][wname][str(int(cap))][cname] = r

# ---------------------------------------------------------------------------
print('\n== 5. 중개사업자 수 산수(전력거래소 2026-07-22 정보공개, 2026-03-31 기준)')
land, jeju, total, both = 35, 22, 42, 15
print(f'  육지 {land} + 제주 {jeju} - 중복 {both} = {land + jeju - both} (공개 합계 {total})')
print(f'  육지에만 있는 사업자 {land - both}곳, 제주에만 있는 사업자 {jeju - both}곳, 양쪽 모두 {both}곳')
res['brokers'] = {'land': land, 'jeju': jeju, 'both': both, 'total_check': land + jeju - both, 'land_only': land - both, 'jeju_only': jeju - both}

json.dump(res, open(OUT_JSON, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print('\n저장:', OUT_JSON)
