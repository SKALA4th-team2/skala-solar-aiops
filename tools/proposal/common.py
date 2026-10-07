"""기획서의 수치 점검과 그림에 함께 쓰는 자료 읽기와 계산 함수.

정의는 조사 문서와 같게 맞췄다.
- 실습 코드의 창과 분할: project/data/features.py 의 build_sequences, train_test_split 과 같은 규칙을 옮겨 적었다(모듈을 import 하지 않는다).
- 성능 지표(PI)와 정지·보류 관문: tools/verify/t5_independent_audit.py 의 정의를 그대로 따른다.
경로는 모두 저장소 루트 기준이다.
"""
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DATASETS = ROOT / "datasets"
EVIDENCE = ROOT / "docs" / "proposal" / "evidence"
ASSETS = ROOT / "docs" / "proposal" / "assets"

SEQ_LEN = 20          # project/data/features.py 의 SEQ_LEN
TEST_RATIO = 0.2      # train_test_split 의 기본값


def load_upload(name="hadong_upload_forecast_jma.csv") -> pd.DataFrame:
    return pd.read_csv(DATASETS / name, parse_dates=["Date"])


def load_daily_full() -> pd.DataFrame:
    return pd.read_csv(DATASETS / "hadong_daily_full.csv", parse_dates=["date"]).set_index("date").sort_index()


def load_raw_generation() -> pd.DataFrame:
    raw = pd.read_csv(DATASETS / "raw" / "data_15043409.csv", encoding="cp949")
    raw["date"] = pd.to_datetime(raw["년월일"])
    return raw.set_index("date").sort_index()


def practice_split(n_rows: int):
    """실습 코드와 같은 분할. 표본 i 는 행 i ~ i+19 를 입력으로, 행 i+20 을 정답으로 쓴다."""
    n_samples = n_rows - SEQ_LEN
    split = int(n_samples * (1 - TEST_RATIO))
    train_targets = np.arange(SEQ_LEN, SEQ_LEN + split)
    test_targets = np.arange(SEQ_LEN + split, n_rows)
    return n_samples, train_targets, test_targets


def rmse(y, p) -> float:
    y, p = np.asarray(y, dtype=float), np.asarray(p, dtype=float)
    return float(np.sqrt(np.mean((p - y) ** 2)))


def total_error_pct(y, p) -> float:
    """합계 오차율(%): 절대오차의 합 ÷ 실제 발전량의 합."""
    y, p = np.asarray(y, dtype=float), np.asarray(p, dtype=float)
    return float(np.abs(p - y).sum() / y.sum() * 100)


def bias_pct(y, p) -> float:
    """치우침(%): (예측 합 - 실제 합) ÷ 실제 합. 양수이면 높게 예측했다."""
    y, p = np.asarray(y, dtype=float), np.asarray(p, dtype=float)
    return float((p.sum() - y.sum()) / y.sum() * 100)


def baselines_for_targets(close: np.ndarray, vol: np.ndarray, targets: np.ndarray) -> dict:
    """학습 없는 기준 예측. 모두 대상일 전날까지의 행만 쓴다.

    업로드 파일의 d 행에는 d 일의 발전량(close)과 d+1 일에 대한 하루 전 예보(vol)가 있다.
    그래서 j 일에 대한 예보는 vol[j-1] 이다.
    """
    out = {"어제 값": [], "7일 평균": [], "20일 평균": [], "규칙C": []}
    for t in targets:
        out["어제 값"].append(close[t - 1])
        out["7일 평균"].append(close[t - 7:t].mean())
        out["20일 평균"].append(close[t - 20:t].mean())
        eff = close[t - 7:t].sum() / vol[t - 8:t - 1].sum()      # 최근 7일의 발전량 합 ÷ 그 7일에 대한 예보 합
        out["규칙C"].append(eff * vol[t - 1])                     # × 대상일 예보
    return {k: np.array(v) for k, v in out.items()}


def gate(x: pd.Series, e: pd.Series):
    """정지, 보류, 유효일. x 는 실제 발전량, e 는 그날 관측 날씨로 계산한 기대 발전량."""
    out = (x <= 0) | ((e >= 30) & (x < 0.3 * e))                       # 정지: 0 이하이거나, 기대 30kWh 이상인데 실제가 30% 미만
    low = out | ((e >= 80) & (x < 0.7 * e))                             # 낮은 날: 정지이거나, 기대 80kWh 이상인데 실제가 70% 미만
    hold = low.astype(int).rolling(7, min_periods=1).sum() >= 3         # 보류: 최근 7일에 낮은 날이 3일 이상
    valid = e.notna() & (e > 0) & ~out & ~hold
    return out, hold, valid


def pi(x: pd.Series, e: pd.Series, valid: pd.Series, start, end, clip=True):
    """성능 지표: 유효일의 실제 발전량(기대의 0.5 ~ 1.5배로 자름) 합 ÷ 기대 발전량 합. (값, 유효일 수)"""
    idx = x.index
    m = (idx >= pd.Timestamp(start)) & (idx <= pd.Timestamp(end)) & valid
    z = x.clip(0.5 * e, 1.5 * e) if clip else x
    den = e[m].sum()
    return (float(z[m].sum() / den) if den > 0 else float("nan")), int(m.sum())


def baseline_365(x, e, valid, end):
    """end 까지의 365일로 계산한 기준선."""
    end = pd.Timestamp(end)
    return pi(x, e, valid, end - pd.Timedelta(days=364), end)


def injection_scan(x: pd.Series, e: pd.Series, factors, starts, baseline: float, min_valid: int = 15) -> dict:
    """시작일마다 그날부터 발전량에 배율을 곱하고, 대상 21일(시작일+20 ~ +40)의 성능 지표 편차를 고정 기준선과 견준다.

    tools/verify/t5_independent_audit.py 의 주입 계산과 같은 순서다(주입한 값으로 정지·보류를 다시 판정한다).
    유효일이 min_valid 에 못 미치는 배치의 편차는 None 이다(판정하지 않음).
    """
    out = {}
    for f in factors:
        devs = []
        for st in starts:
            xx = x.copy()
            xx.loc[st:] *= f
            _, _, valid = gate(xx, e)
            value, n = pi(xx, e, valid, st + pd.Timedelta(days=20), st + pd.Timedelta(days=40))
            devs.append(None if n < min_valid else value / baseline - 1)
        out[f] = devs
    return out
