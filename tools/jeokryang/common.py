"""적량면 관측 자료 검토에 쓰는 공통 함수. 경로는 모두 저장소 루트 기준이다."""
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DATASETS = ROOT / "datasets"
OUT = Path(__file__).resolve().parent / "out"
DAILY = DATASETS / "jeokryang_daily.csv"


def load_joined() -> pd.DataFrame:
    """날짜별로 발전 실적, 광양 관측, 적량 관측, 재분석 일사량을 한 줄에 놓는다.

    jr_gsr : 적량면 하루 일사량 (MJ/m2)
    gy_gsr : 광양시(266) 하루 일사량 (MJ/m2)
    era    : Open-Meteo 재분석 하루 일사량 (MJ/m2)
    """
    full = pd.read_csv(DATASETS / "hadong_daily_full.csv", parse_dates=["date"]).set_index("date")
    jr = pd.read_csv(DAILY, parse_dates=["date"]).set_index("date")
    era = pd.read_csv(DATASETS / "raw" / "wx_archive_daily.csv", parse_dates=["date"]).set_index("date")
    a = full.join(jr.rename(columns={"gsr_mj": "jr_gsr"}), how="left")
    a = a.join(era[["shortwave_radiation_sum"]].rename(columns={"shortwave_radiation_sum": "era"}))
    return a


def rmse(y, p) -> float:
    return float(np.sqrt(np.mean((np.asarray(p) - np.asarray(y)) ** 2)))


def bias_pct(y, p) -> float:
    """합계 치우침(%). 양수이면 예측 합계가 실제 합계보다 크다."""
    y, p = np.asarray(y), np.asarray(p)
    return float((p.sum() - y.sum()) / y.sum() * 100)
