# T7(고객, 손익, Pain Point) 대조용 공통 함수. 원 조사 코드(solar/agg, solar/q6)를 import 하지 않고 새로 적었다.
# 읽는 자료: 하수처리장 원본 CSV(CP949), 하동 5곳 시간값 캐시(solar/verify1b/c_*.pkl, 원 조사가 공공데이터포털에서 받아 둔 사본).
# 부산 2곳은 디스크에 사본이 없어 이 폴더의 계산에는 들어가지 않는다(내려받지 않음).
import os, csv, io, pickle, numpy as np, pandas as pd

S = '(작업 폴더)'
RAW = os.path.join(S, 'solar', 'data_15043409.csv')
PKL = os.path.join(S, 'solar', 'verify1b', 'c_%s.pkl')
NAMES = {'15043409': '하수처리장', '15043406': '보건소', '15043405': '변전소', '15043408': '정수장', '15043404': '공설운동장'}
CAP = {'15043409': 55.0, '15043406': 40.0, '15043405': 48.3, '15043408': 93.02, '15043404': 369.85}
HADONG = list(NAMES)


def load_raw():
    """하수처리장 원본 CSV -> (날짜 index, 시간값 T x 24)."""
    rows = list(csv.reader(io.StringIO(open(RAW, 'rb').read().decode('cp949'))))
    hdr, rows = rows[0], [r for r in rows[1:] if r and r[0]]
    idx = pd.to_datetime([r[0] for r in rows])
    H = np.array([[float(x) if x not in ('', None) else 0.0 for x in r[8:32]] for r in rows])
    tot = np.array([float(r[2]) if r[2] else np.nan for r in rows])
    return hdr, idx, H, tot


def load_pkl(pk):
    o = pickle.load(open(PKL % pk, 'rb'))
    ds = sorted(o['d'])
    H = np.array([[0.0 if v is None else float(v) for v in o['d'][d][0][2]] for d in ds])
    return pd.to_datetime(ds), H, o.get('nm', '')


def stop_mask(cf, p, group, thr=0.3, ref_min=1.0, win=61, causal=False):
    """정지일 판정. cf: 발전소별 하루 이용시간(kWh/kW) DataFrame.
    하루 합계 0 이거나, 이웃(같은 지역 다른 발전소)의 이용시간 중앙값이 ref_min 이상인 날에
    (자기/이웃) 비율이 평소(앞뒤 win일 중앙값)의 thr 배 미만이면 정지."""
    ref = cf[[q for q in group if q != p]].median(axis=1)
    r = (cf[p] / ref).where(ref >= ref_min)
    if causal:
        base = r.shift(1).rolling(win, min_periods=15).median()
    else:
        base = r.rolling(win, center=True, min_periods=15).median()
    rel = r / base
    return ((cf[p] == 0) | (rel < thr)).values, rel


def forecasts(H, stop):
    """정지일을 건너뛴 단순 예측 세 가지. PERS: 직전 정상일의 같은 시간 값. MA7: 직전 정상일 7일 평균.
    ORA: 대상일의 실제 하루 합계 x 직전 7일 시간 비중(예측 시점에 받을 수 없는 값을 쓰는 참고 계산)."""
    T = len(H); ok = ~stop; pos = np.where(ok)[0]
    Hv = H[pos]
    pers = np.full_like(Hv, np.nan); pers[1:] = Hv[:-1]
    ma7 = np.full_like(Hv, np.nan)
    for i in range(7, len(Hv)):
        ma7[i] = Hv[i - 7:i].mean(axis=0)
    s = np.nansum(ma7, axis=1, keepdims=True)
    prof = ma7 / np.where(s > 0, s, np.nan)
    ora = prof * Hv.sum(axis=1, keepdims=True)
    out = {}
    for k, v in (('PERS', pers), ('MA7', ma7), ('ORA', ora)):
        a = np.full((T, 24), np.nan); a[pos] = v; out[k] = a
    valid = np.zeros(T, bool); valid[pos[7:]] = True
    valid &= ~np.isnan(out['MA7']).any(axis=1)
    return out, valid


def price(e, t1=4.0, t2=6.0):
    return np.where(e <= t1, 4.0, np.where(e <= t2, 3.0, 0.0))


def agg(Hd, Fd, Vd, caps, members, days):
    """집합(그날 정지한 구성원은 용량·예측·실제에서 뺌)의 시간대별 오차율(%), 실제 합, 대상 여부, 편향."""
    T = len(days)
    A = np.zeros((T, 24)); F = np.zeros((T, 24)); C = np.zeros(T)
    for p in members:
        m = Vd[p][:, None]
        A += np.where(m, Hd[p], 0.0); F += np.where(m, np.nan_to_num(Fd[p]), 0.0); C += Vd[p] * caps[p]
    Cc = np.where(C > 0, C, np.nan)[:, None]
    err = np.abs(F - A) / Cc * 100
    bias = (F - A) / Cc * 100
    elig = (C[:, None] > 0) & (A >= 0.1 * Cc) & days[:, None]
    return err, A, elig, bias


def summarize(err, A, elig, bias=None, shift=0.0, scale=1.0, t1=4.0, t2=6.0):
    e = err[elig] * scale + shift; a = A[elig]
    pr = price(e, t1, t2)
    d = dict(n=int(elig.sum()), err=float(e.mean()), med=float(np.median(e)), unit=float((a * pr).sum() / a.sum()),
             kwh=float(a.sum()), won=float((a * pr).sum()))
    if bias is not None:
        d['bias'] = float(bias[elig].mean())
    return d


def sens(err, A, elig, t1=4.0, t2=6.0, scale=1.0):
    b = summarize(err, A, elig, t1=t1, t2=t2, scale=scale)
    p1 = summarize(err, A, elig, shift=1.0, t1=t1, t2=t2, scale=scale)
    p2 = summarize(err, A, elig, shift=2.0, t1=t1, t2=t2, scale=scale)
    return b, (p1['unit'] / b['unit'] - 1) * 100, (p2['unit'] / b['unit'] - 1) * 100
