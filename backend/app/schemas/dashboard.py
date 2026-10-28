"""API contract matching the dashboard's existing JSON field names."""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

# Province identifiers come from the selected source, not the demo seed.
ProvinceCode = str
AirQualityStatus = Literal["Tốt", "Trung bình", "Kém", "Xấu", "Rất xấu", "Nguy hại"]


class ApiModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, allow_inf_nan=False)


class MetricQuality(ApiModel):
    quality_status: str | None = None
    missing_reason: str | None = None
    observation_time: datetime | None = None
    coverage: float | None = None


class ProvinceSnapshot(ApiModel):
    metric_quality: dict[str,MetricQuality] = Field(default_factory=dict)
    aqi_status: str | None = None
    province_code: ProvinceCode
    province_name: str
    aqi: int | None
    status: AirQualityStatus | None
    pm25: float | None
    pm10: float | None
    source: str | None = None
    series_id: str | None = None
    location_id: str | None = None
    observation_time: datetime | None = None
    source_resolution_minutes: int | None = None
    temporal_support: str | None = None
    applicability_profile: str | None = None
    quality_status: str | None = None
    aqi_missing_reason: str | None = None
    coverage: float | None = None
    aqi_method_version: str | None = None
    aqi_origin: str | None = None
    dominant_pollutants: list[str] | None = None
    published_release_id: str | None = None
    pm1: float | None = None
    o3: float | None = None
    no2: float | None = None
    so2: float | None = None
    co: float | None = None
    o3_column: float | None = None
    no2_column: float | None = None
    so2_column: float | None = None
    co_column: float | None = None


class EmissionRecord(ApiModel):
    province_code: ProvinceCode
    province_name: str
    year: int
    month: int
    sector: str
    emission_tonnes: float


class DashboardTrendRecord(ApiModel):
    metric_sample_counts: dict[str, int] | None = None
    aqi: int | None = None
    province_code: ProvinceCode
    date: date | datetime
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
    version: str | None = None
    statistic: str | None = None
    reference_kind: str | None = None
    note: str | None = None
    breakpoints: list[float]
    method: Literal["absolute_concentration"]
    sample_count: int
    reference_start: date | datetime
    reference_end: date | datetime


class MetricMetadata(ApiModel):
    unit: str
    quantity: str
    map_scale: ConcentrationScale | None = None


class DashboardMetadata(ApiModel):
    published_timeline_id: str | None = None
    compatibility_id: str | None = None
    published_release_ids: list[str] = Field(default_factory=list)
    missing_scopes: list[dict] = Field(default_factory=list)
    published_release_id: str | None = None
    source: str
    generation: str
    start: str
    end: str
    snapshot_date: date | datetime | None
    metrics: dict[str, MetricMetadata]
    temporal_aggregation: str
    timezone: str
    minimum_spatial_coverage: float | None
    minimum_monthly_coverage: float | None
    note: str
    query_start: datetime | None = None
    query_end: datetime | None = None
    available_years: list[int] = Field(default_factory=list)
    observation_start: str | None = None
    observation_end: str | None = None


class DashboardData(ApiModel):
    province_snapshots: list[ProvinceSnapshot]
    emission_records: list[EmissionRecord]
    emission_sectors: list[str]
    dashboard_trend_records: list[DashboardTrendRecord]
    metadata: DashboardMetadata | None = None


class AdminDashboardTrendRecord(DashboardTrendRecord):
    aqi: float | None = None


class PriorityArea(ApiModel):
    province_code: ProvinceCode
    province_name: str
    pm25_average: float | None
    year_over_year_percent: float | None
    exceedance_days: int | None
    total_emissions: float | None
    main_emission_sector: str | None
    trend: Literal["up", "slight-up", "steady", "down"] | None


class AnnualProvinceSummary(ApiModel):
    province_code: ProvinceCode
    province_name: str
    year: int
    pm25_average: float | None
    aqi_average: float | None
    year_over_year_percent: float | None
    exceedance_days: int | None


class AdminDashboardData(ApiModel):
    province_snapshots: list[ProvinceSnapshot]
    emission_records: list[EmissionRecord]
    emission_sectors: list[str]
    dashboard_trend_records: list[AdminDashboardTrendRecord]
    priority_areas: list[PriorityArea]
    annual_province_summaries: list[AnnualProvinceSummary]
    metadata: DashboardMetadata | None = None
