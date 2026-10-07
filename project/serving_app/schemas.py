"""태양광 예측 API 계약. 한 행은 당일 발전량과 다음 날 일사량 예보다."""
from datetime import date as Date, timedelta
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, model_validator

from data.features import SEQ_LEN

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
Generation = Annotated[float, Field(ge=0, le=MAX_GENERATION_KWH, allow_inf_nan=False, strict=True)]
Forecast = Annotated[float, Field(ge=0, le=MAX_FORECAST_MJ, allow_inf_nan=False, strict=True)]


def validate_daily_dates(dates: list[Date]) -> None:
    if any((current - previous).days != 1 for previous, current in zip(dates, dates[1:])):
        raise ValueError('날짜는 중복이나 빠진 날 없이 하루씩 이어진 오름차순이어야 합니다.')


class DailyPoint(BaseModel):
    model_config = ConfigDict(extra='forbid')
    date: CalendarDate = Field(description='해당 행의 날짜 (YYYY-MM-DD)')
    close: Generation = Field(description='해당 날짜의 하루 발전량 (kWh)')
    volume: Forecast = Field(description='다음 날에 대한 하루 전 일사량 예보의 하루 합계 (MJ/m²)')


class PredictRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    sequence: list[DailyPoint] = Field(
        min_length=SEQ_LEN, max_length=SEQ_LEN,
        description=f'대상일 직전의 연속 {SEQ_LEN}일, 오래된 날짜부터. 마지막 행에 대상일의 예보를 담는다.',
    )

    @model_validator(mode='after')
    def check_dates(self):
        validate_daily_dates([point.date for point in self.sequence])
        if self.sequence[-1].date == Date.max:
            raise ValueError('다음 날의 예측 대상일을 계산할 수 없는 날짜입니다.')
        return self


class PredictResponse(BaseModel):
    predicted_close: float = Field(ge=0, allow_inf_nan=False, description='대상일의 하루 발전량 예측 (kWh)')
    target_date: CalendarDate = Field(description='예측 대상일: 입력 마지막 날짜의 다음 날')
    model_version: str


class BatchTestRequest(BaseModel):
    # 태양광 배치 계약은 후속 이슈에서 호출부와 함께 전환한다.
    prices: list[float] = Field(..., min_length=SEQ_LEN + 1)


class BatchTestResponse(BaseModel):
    predictions: list[float]
    drift_check: dict


class HealthResponse(BaseModel):
    status: str
    model_loaded: bool
    model_version: str | None = Field(description='현재 메모리 모델의 버전. 미로딩이면 null')
    model_source: str | None = Field(description='현재 메모리 모델의 출처(local 또는 mlflow). 미로딩이면 null')
    loading_mode: str
