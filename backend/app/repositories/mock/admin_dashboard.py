"""Management dashboard demo additions kept on the backend mock source."""

from collections import defaultdict

from app.schemas.dashboard import (
    AdminDashboardData,
    AdminDashboardTrendRecord,
    AnnualProvinceSummary,
    DashboardData,
    EmissionRecord,
    PriorityArea,
)

PRIORITY_SEED = {
    "01": (35.1, 16.7, 42, 3850, "Manufacturing", "up"),
    "24": (32.1, 11.2, 36, 2940, "Manufacturing", "up"),
    "79": (27.1, 5.3, 24, 3120, "Transport", "slight-up"),
    "22": (24.0, 2.0, 20, 2680, "Power", "steady"),
    "48": (18.1, -6.2, 8, 1050, "Transport", "down"),
}

EMISSION_PROFILES = {
    "01": (("Manufacturing", 1600), ("Power", 950), ("Transport", 900), ("Residential", 400)),
    "24": (("Manufacturing", 1400), ("Power", 750), ("Transport", 520), ("Residential", 270)),
    "22": (("Power", 1250), ("Manufacturing", 750), ("Transport", 430), ("Residential", 250)),
    "48": (("Transport", 460), ("Manufacturing", 260), ("Power", 190), ("Residential", 140)),
    "79": (("Transport", 1350), ("Manufacturing", 800), ("Power", 520), ("Residential", 450)),
}

ANNUAL_SEED = {
    ("01", 2025): (29.7, 95, 9, 34), ("24", 2025): (28.1, 90, 8, 32),
    ("22", 2025): (23.5, 75, 4, 18), ("48", 2025): (18.9, 60, -3, 15),
    ("79", 2025): (25.0, 80, 4, 24), ("01", 2026): (35.0, 112, 18, 42),
    ("24", 2026): (32.0, 102, 14, 38), ("22", 2026): (24.0, 77, 2, 20),
    ("48", 2026): (18.0, 58, -5, 12), ("79", 2026): (27.0, 86, 8, 28),
}


def _mean(values):
    values = [value for value in values if value is not None]
    return sum(values) / len(values) if values else None


def make_admin_dashboard(data: DashboardData) -> AdminDashboardData:
    provinces = {item.province_code: item.province_name for item in data.province_snapshots}
    trends = []
    for record in data.dashboard_trend_records:
        values = record.model_dump()
        # The explicitly illustrative mock source uses the same AQI mapping as
        # the original demo dashboard. Real sources keep AQI unavailable.
        values["aqi"] = round(record.pm25 * 3.2) if record.pm25 is not None else None
        trends.append(AdminDashboardTrendRecord(**values))

    emissions = []
    for code, profile in EMISSION_PROFILES.items():
        if code not in provinces:
            continue
        for year in (2025, 2026):
            for month in range(1, 13):
                for sector, annual_tonnes in profile:
                    emissions.append(EmissionRecord(
                        province_code=code,
                        province_name=provinces[code],
                        year=year,
                        month=month,
                        sector=sector,
                        emission_tonnes=annual_tonnes * (1 if year == 2026 else .93) / 12,
                    ))

    priority_areas = [
        PriorityArea(province_code=code, province_name=provinces[code],
                    pm25_average=pm25, year_over_year_percent=yoy,
                    exceedance_days=days, total_emissions=emissions_total,
                    main_emission_sector=sector, trend=trend)
        for code, (pm25, yoy, days, emissions_total, sector, trend) in PRIORITY_SEED.items()
        if code in provinces
    ]
    annual_summaries = [
        AnnualProvinceSummary(province_code=code, province_name=provinces[code], year=year,
                              pm25_average=pm25, aqi_average=aqi,
                              year_over_year_percent=yoy, exceedance_days=days)
        for (code, year), (pm25, aqi, yoy, days) in ANNUAL_SEED.items()
        if code in provinces
    ]
    return AdminDashboardData(
        province_snapshots=data.province_snapshots,
        emission_records=emissions,
        emission_sectors=data.emission_sectors,
        dashboard_trend_records=trends,
        priority_areas=priority_areas,
        annual_province_summaries=annual_summaries,
        metadata=data.metadata,
    )


def project_admin_dashboard(data: DashboardData) -> AdminDashboardData:
    """Project any source into admin data without inventing missing metrics."""
    grouped = defaultdict(list)
    for record in data.dashboard_trend_records:
        grouped[(record.province_code, record.date.year)].append(record)
    annual = []
    for (code, year), records in sorted(grouped.items()):
        annual.append(AnnualProvinceSummary(
            province_code=code,
            province_name=next((p.province_name for p in data.province_snapshots if p.province_code == code), code),
            year=year,
            pm25_average=_mean([record.pm25 for record in records]),
            aqi_average=_mean([None for _ in records]),
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
    previous_by_code = {code: item for (code, year), item in summary_by_key.items() if year == (latest_year - 1 if latest_year else -1)}
    areas = []
    for code, current in latest_by_code.items():
        if current.pm25_average is None:
            continue
        previous = previous_by_code.get(code)
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
        dashboard_trend_records=[AdminDashboardTrendRecord(**row.model_dump()) for row in data.dashboard_trend_records],
        priority_areas=areas,
        annual_province_summaries=annual,
        metadata=data.metadata,
    )
