"""API contract matching the dashboard's existing JSON field names."""

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

# Province identifiers come from the selected source, not the demo seed.
ProvinceCode = str
AirQualityStatus = Literal["Tốt", "Trung bình", "Kém", "Xấu"]


class ApiModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, allow_inf_nan=False)


class ProvinceSnapshot(ApiModel):
    province_code: ProvinceCode
    province_name: str
    aqi: int | None
    status: AirQualityStatus | None
    pm25: float | None
    pm10: float | None
    pm1: float | None = None


class EmissionRecord(ApiModel):
    province_code: ProvinceCode
    province_name: str
    year: int
    month: int
    sector: str
    emission_tonnes: float


class DashboardTrendRecord(ApiModel):
    province_code: ProvinceCode
    date: date
    pm25: float | None
    pm10: float | None
    o3: float | None
    no2: float | None
    so2: float | None
    co: float | None

    pm1: float | None = None
    aod550: float | None = None
    o3_column: float | None = None
    no2_column: float | None = None
    so2_column: float | None = None
    co_column: float | None = None
    t2m: float | None = Field(default=None, alias="t2m")
    d2m: float | None = Field(default=None, alias="d2m")
    sp: float | None = None
    mslp: float | None = None
    u10: float | None = None
    v10: float | None = None


class ConcentrationScale(ApiModel):
    breakpoints: list[float]
    method: Literal["absolute_concentration"]
    sample_count: int
    reference_start: date
    reference_end: date


class MetricMetadata(ApiModel):
    unit: str
    quantity: str
    map_scale: ConcentrationScale | None = None


class DashboardMetadata(ApiModel):
    source: str
    generation: str
    start: str
    end: str
    snapshot_date: date | None
    metrics: dict[str, MetricMetadata]
    temporal_aggregation: str
    timezone: str
    minimum_spatial_coverage: float
    minimum_monthly_coverage: float
    note: str


class DashboardData(ApiModel):
    province_snapshots: list[ProvinceSnapshot]
    emission_records: list[EmissionRecord]
    emission_sectors: list[str]
    dashboard_trend_records: list[DashboardTrendRecord]
    metadata: DashboardMetadata | None = None
