"""Source-independent management view derived from observed dashboard values."""
import calendar
from collections import defaultdict

from app.schemas.dashboard import (
    AdminDashboardData,
    AdminDashboardTrendRecord,
    AnnualProvinceSummary,
    DashboardData,
    PriorityArea,
)


def _mean(values):
    values = [value for value in values if value is not None]
    return sum(values) / len(values) if values else None


def project_admin_dashboard(data: DashboardData) -> AdminDashboardData:
    """Project any source into admin data without inventing missing metrics."""
    provinces = {item.province_code: item.province_name for item in data.province_snapshots}
    grouped = defaultdict(list)
    for record in data.dashboard_trend_records:
        grouped[(record.province_code, record.date.year)].append(record)
    annual = []
    for (code, year), records in sorted(grouped.items()):
        annual.append(AnnualProvinceSummary(
            province_code=code,
            province_name=provinces.get(code, code),
            year=year,
            pm25_average=_mean([record.pm25 for record in records]),
            aqi_average=None,
            year_over_year_percent=None,
            exceedance_days=None,
        ))
    summary_by_key = {(item.province_code, item.year): item for item in annual}
    for item in annual:
        previous = summary_by_key.get((item.province_code, item.year - 1))
        if previous and previous.pm25_average not in (None, 0) and item.pm25_average is not None:
            item.year_over_year_percent = (item.pm25_average - previous.pm25_average) / previous.pm25_average * 100

    latest_year = max((year for _, year in grouped), default=None)
    latest_by_code = {code: item for (code, year), item in summary_by_key.items() if year == latest_year}
    areas = []
    for code, current in latest_by_code.items():
        if current.pm25_average is None:
            continue
        yoy = current.year_over_year_percent
        trend = None if yoy is None else "up" if yoy >= 8 else "slight-up" if yoy > 2 else "down" if yoy <= -2 else "steady"
        areas.append(PriorityArea(
            province_code=code, province_name=current.province_name,
            pm25_average=current.pm25_average, year_over_year_percent=yoy,
            exceedance_days=None, total_emissions=None, main_emission_sector=None, trend=trend,
        ))
    return AdminDashboardData(
        province_snapshots=data.province_snapshots,
        emission_records=data.emission_records,
        emission_sectors=data.emission_sectors,
        dashboard_trend_records=[AdminDashboardTrendRecord(**row.model_dump(exclude_unset=True)) for row in data.dashboard_trend_records],
        priority_areas=areas,
        # A bounded observation window is not an annual average.
        annual_province_summaries=[item for item in annual if len(grouped[(item.province_code, item.year)]) == (
            (366 if calendar.isleap(item.year) else 365) * 8 if data.metadata and data.metadata.temporal_aggregation == "3_hourly"
            else (366 if calendar.isleap(item.year) else 365) if data.metadata and data.metadata.temporal_aggregation == "daily_mean"
            else 12
        )],
        metadata=data.metadata,
    )
