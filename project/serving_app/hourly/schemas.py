"""Hourly interval energy, explicit Korean local timestamps and fixed 24-hour origins."""
from datetime import datetime,timedelta
from pydantic import BaseModel,ConfigDict,Field,field_validator,model_validator
from serving_app import runtime as rt

class Strict(BaseModel):
    model_config=ConfigDict(extra='forbid',allow_inf_nan=False)

class Timestamp(Strict):
    timestamp:datetime
    @field_validator('timestamp')
    @classmethod
    def local_hour(cls,t):
        if t.utcoffset()!=timedelta(hours=9) or t.minute or t.second or t.microsecond:
            raise ValueError('timestamp must be an exact hour with +09:00 timezone')
        return t

class Generation(Timestamp):
    generation_kwh:float=Field(ge=0)

class Weather(Timestamp):
    shortwave_radiation:float=Field(ge=0,le=1500)
    temperature_2m:float=Field(ge=-60,le=60)
    cloud_cover:float=Field(ge=0,le=100)
    wind_speed_10m:float=Field(ge=0,le=200)

class Row(Generation,Weather):pass

def consecutive(rows):
    if rows[0].timestamp.hour!=0 or rows[-1].timestamp.hour!=23 or len(rows)%24:
        raise ValueError('Complete calendar days from 00:00 through 23:00 are required')
    if any(b.timestamp-a.timestamp!=timedelta(hours=1) for a,b in zip(rows,rows[1:])):
        raise ValueError('Missing, duplicated or unordered hour')

def capacity(pid,rows):
    try:c=rt.plant(pid)['capacity_kw']
    except KeyError:raise ValueError('Unknown or excluded plant') from None
    if any(r.generation_kwh>c for r in rows):raise ValueError('Hourly kWh exceeds nameplate kW × one hour')

class Predict(Strict):
    plant_id:str=rt.DEFAULT_PLANT
    history:list[Generation]=Field(min_length=24,max_length=24)
    forecast:list[Weather]=Field(min_length=24,max_length=24)
    @model_validator(mode='after')
    def check(self):
        consecutive(self.history+self.forecast);capacity(self.plant_id,self.history);return self

class Batch(Strict):
    plant_id:str=rt.DEFAULT_PLANT
    rows:list[Row]=Field(min_length=48,max_length=8760)
    @model_validator(mode='after')
    def check(self):
        consecutive(self.rows);capacity(self.plant_id,self.rows);return self

class Rollback(Strict):
    version:int=Field(ge=1)

class Portfolio(Strict):
    inputs:dict[str,Predict]=Field(min_length=1,max_length=100)
