# (13) "설비 수준 변화를 2~4주 안에 알린다"의 재확인: hadong_daily_full.csv 의 창 지표(pi_21d, pi_30d)를 1년 전 같은 날의 값과 견줘
#      -7.5% 를 넘는 첫날을 센다. 성능 지표는 그날 관측 날씨로 계산하는 사후 점검값이다(예측 입력이 아님). 기준값 7.5% 는 ASOS 묶음이 전체 기간을 보고 고른 값이다.
import os, numpy as np, pandas as pd
from t7_lib import S
A = pd.read_csv(os.path.join(S, 'asos', 'hadong_daily_full.csv'), parse_dates=['date']).set_index('date')
for col in ('pi_21d', 'pi_30d'):
    x = A[col]; prev = x.shift(365); dev = x / prev - 1
    for thr in (0.075,):
        for consec in (1, 3):
            hit = (dev < -thr).astype(int)
            run = hit.rolling(consec).sum() == consec
            after = run['2021-05-18':'2021-12-31']
            first = after[after].index[0] if after.any() else None
            fa = run['2016-01-01':'2018-06-30']
            # 오경보 구간에서 정지 보류일은 지표가 비어 있어 자동으로 빠짐
            n_alarm_days = int(fa.sum()); episodes = int(((fa.astype(int).diff() == 1)).sum())
            print('%s, 1년 전 같은 날 대비 -%.1f%%, %d일 연속: 2021-05-18 뒤 첫 경보 %s (%s일째) | 2016-01~2018-06 경보 상태 %d일, %d회'
                  % (col, thr * 100, consec, first.date() if first is not None else None, (first - pd.Timestamp('2021-05-18')).days + 1 if first is not None else None, n_alarm_days, episodes))
    print('  %s 값: 2021-05-17 %.4f, 2021-06-07 %.4f, 2021-06-17 %.4f, 2021-06-27 %.4f | 1년 전 같은 날 대비 2021-06-07 %+.1f%%, 06-17 %+.1f%%, 06-27 %+.1f%%'
          % (col, x['2021-05-17'], x['2021-06-07'], x['2021-06-17'], x['2021-06-27'], dev['2021-06-07'] * 100, dev['2021-06-17'] * 100, dev['2021-06-27'] * 100))
# 2015-01 하락
for col in ('pi_21d', 'pi_30d'):
    x = A[col]; base = x['2014-01-01':'2014-12-31']
    print('%s 2014년 값 범위 %.3f~%.3f (창 지표의 평소 흔들림), 2016-01~2018-06 표준편차 %.3f' % (col, base.min(), base.max(), A[col]['2016-01-01':'2018-06-30'].std()))
