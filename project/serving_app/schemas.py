"""태양광 예측 API 계약. 한 행은 당일 발전량과 다음 날 일사량 예보다."""
from datetime import date as Date
from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, model_validator

from data.features import SEQ_LEN
from serving_app import runtime as rt

MAX_GENERATION_KWH = 1320.0
MAX_FORECAST_MJ = 45.0


def parse_calendar_date(value):
    if isinstance(value, Date) and type(value) is Date:
        return value
    if not isinstance(value, str):
        raise ValueError('날짜는 YYYY-MM-DD 문자열이어야 합니다.')
    try:
        parsed = Date.fromisoformat(value)
    except ValueError:
        raise ValueError('날짜는 YYYY-MM-DD 형식의 유효한 날짜여야 합니다.') from None
    if parsed.isoformat() != value:
        raise ValueError('날짜는 YYYY-MM-DD 형식이어야 합니다.')
    return parsed


CalendarDate = Annotated[Date, BeforeValidator(parse_calendar_date)]
Generation = Annotated[float, Field(ge=0, allow_inf_nan=False, strict=True)]
Forecast = Annotated[float, Field(ge=0, le=MAX_FORECAST_MJ, allow_inf_nan=False, strict=True)]


def validate_daily_dates(dates: list[Date]) -> None:
    if any((current - previous).days != 1 for previous, current in zip(dates, dates[1:])):
        raise ValueError('날짜는 중복이나 빠진 날 없이 하루씩 이어진 오름차순이어야 합니다.')

def validate_capacity(plant_id,values):
    try:capacity=rt.plant(plant_id).get('capacity_kw')
    except KeyError:return  # HTTP route provides the documented 404.
    if capacity and any(value>capacity*24 for value in values):
        raise ValueError(f'발전량은 해당 설비 용량 × 24시간({capacity*24:g}kWh) 이하여야 합니다.')


class DailyPoint(BaseModel):
    model_config = ConfigDict(extra='forbid')
    date: CalendarDate = Field(description='해당 행의 날짜 (YYYY-MM-DD)')
    close: Generation = Field(description='해당 날짜의 하루 발전량 (kWh)')
    volume: Forecast = Field(description='다음 날에 대한 하루 전 일사량 예보의 하루 합계 (MJ/m²)')


class PredictRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    plant_id: str = Field(default=rt.DEFAULT_PLANT, pattern=r'^[a-z0-9][a-z0-9-]{1,39}$')
    sequence: list[DailyPoint] = Field(
        min_length=SEQ_LEN, max_length=SEQ_LEN,
        description=f'대상일 직전의 연속 {SEQ_LEN}일, 오래된 날짜부터. 마지막 행에 대상일의 예보를 담는다.',
    )

    @model_validator(mode='after')
    def check_dates(self):
        validate_capacity(self.plant_id,[p.close for p in self.sequence])
        validate_daily_dates([point.date for point in self.sequence])
        if self.sequence[-1].date == Date.max:
            raise ValueError('다음 날의 예측 대상일을 계산할 수 없는 날짜입니다.')
        return self


class PredictResponse(BaseModel):
    plant_id: str = rt.DEFAULT_PLANT
    predicted_close: float = Field(ge=0, allow_inf_nan=False, description='대상일의 하루 발전량 예측 (kWh)')
    target_date: CalendarDate = Field(description='예측 대상일: 입력 마지막 날짜의 다음 날')
    model_version: str


Expected = Annotated[float, Field(ge=0, allow_inf_nan=False, strict=True)]


class BatchTestRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    plant_id: str = Field(default=rt.DEFAULT_PLANT, pattern=r'^[a-z0-9][a-z0-9-]{1,39}$')
    dates: list[CalendarDate] = Field(min_length=SEQ_LEN + 1, description='하루씩 이어진 날짜(YYYY-MM-DD), 최소 21개')
    prices: list[Generation] = Field(min_length=SEQ_LEN + 1, description='해당 날짜의 하루 발전량 (kWh)')
    volumes: list[Forecast] = Field(min_length=SEQ_LEN + 1, description='다음 날 일사량 예보 (MJ/m²)')
    expected: list[Expected | None] = Field(min_length=SEQ_LEN + 1, description='사후 관측 날씨로 계산한 해당 날짜의 기대 발전량(kWh). 없으면 null. 모델 입력에는 쓰지 않는다.')

    @model_validator(mode='after')
    def check_alignment(self):
        validate_capacity(self.plant_id,self.prices)
        if len(self.dates)>400:
            raise ValueError('배치는 최대 400행입니다.')
        if not (len(self.dates) == len(self.prices) == len(self.volumes) == len(self.expected)):
            raise ValueError('dates, prices, volumes, expected는 같은 길이여야 합니다.')
        validate_daily_dates(self.dates)
        return self


class DriftCheck(BaseModel):
    model_config = ConfigDict(extra='forbid')
    status: Literal['ok', 'drift_alerted', 'retrain_triggered', 'facility_check', 'skipped', 'input_anomaly']
    model_version: str
    reason: str | None = Field(default=None, description='미판정 등의 사유. aiops_not_configured는 판정기 미연결')
    pi: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    baseline: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    deviation_pct: float | None = Field(default=None, allow_inf_nan=False)
    head_deviation_pct: float | None = Field(default=None, allow_inf_nan=False)
    valid_days: int | None = Field(default=None, ge=0)
    outage_days: int | None = Field(default=None, ge=0)
    hold_days: int | None = Field(default=None, ge=0)
    rmse21: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    promoted: bool | None = None
    rmse: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    job_id: str | None = None


class BatchTestResponse(BaseModel):
    plant_id: str = rt.DEFAULT_PLANT
    predictions: list[Annotated[float, Field(ge=0, allow_inf_nan=False)]]
    drift_check: DriftCheck


class HealthResponse(BaseModel):
    plant_id: str = rt.DEFAULT_PLANT
    worker_updated_at: str | None = None
    execution_unit: str = 'local'
    status: str
    model_loaded: bool
    model_version: str | None = Field(description='현재 메모리 모델의 버전. 미로딩이면 null')
    model_source: str | None = Field(description='현재 메모리 모델의 출처(local 또는 mlflow). 미로딩이면 null')
    loading_mode: str
