"""Gold API retains source semantics, nulls, release and per-pollutant QC."""
from datetime import datetime,date
from typing import Literal,Any
from pydantic import BaseModel,ConfigDict,Field

Pollutant=Literal['pm25','pm10','co','no2','so2','o3']
Resolution=Literal['hourly','daily','monthly']


class GoldRow(BaseModel):
    model_config=ConfigDict(extra='allow',allow_inf_nan=False)
    published_release_id:str
    source:str|None=None
    series_id:str|None=None
    location_id:str|None=None
    admin_code:str|None=None
    observation_time:datetime|None=None
    resolution:Resolution
    pollutant:Pollutant
    value:float|None=None
    unit:str|None=None
    aqi:int|None=None
    aqi_category:str|None=None
    aqi_color:str|None=None
    dominant_pollutants:list[str]|None=None
    aqi_method_version:str|None=None
    aqi_origin:str|None=None
    applicability_profile:str|None=None
    quality_status:str|None=None
    missing_reason:str|None=None
    aqi_status:str|None=None
    aqi_missing_reason:str|None=None
    coverage:float|None=None
    provider_aqi:int|None=None
    source_resolution_minutes:int|None=None
    temporal_support:str|None=None
    spatial_representation:str|None=None


class GoldResponse(BaseModel):
    model_config=ConfigDict(extra='allow')
    published_release_id:str
    resolution:Resolution
    rows:list[GoldRow]
