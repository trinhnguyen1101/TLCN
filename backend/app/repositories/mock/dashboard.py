"""Deterministic demo data, not scientific observations or live monitoring.

Keep the original frontend seed, ordering and formulas so existing filters,
comparisons, map readings and exports return the same results.
"""

from datetime import date
from functools import cached_property
from math import cos, floor, pi

from app.schemas.dashboard import (
    AirQualityStatus,
    DashboardData,
    DashboardTrendRecord,
    EmissionRecord,
    ProvinceCode,
    ProvinceSnapshot,
)

PROVINCE_SEED: tuple[tuple[ProvinceCode, str, int, int, int], ...] = (
    ("01", "Hà Nội", 145, 48, 71),
    ("24", "Bắc Ninh", 132, 43, 67),
    ("22", "Quảng Ninh", 93, 29, 51),
    ("48", "Đà Nẵng", 62, 17, 34),
    ("79", "TP. Hồ Chí Minh", 108, 34, 58),
)
EMISSION_SEED = (
    ("Manufacturing", 760),
    ("Power", 615),
    ("Transport", 490),
    ("Residential", 285),
)


def get_status(aqi: int) -> AirQualityStatus:
    if aqi <= 50:
        return "Tốt"
    if aqi <= 100:
        return "Trung bình"
    if aqi <= 150:
        return "Kém"
    return "Xấu"


def _build_dashboard_data() -> DashboardData:
    provinces = []
    emissions = []
    trends = []
    for province_index, (code, name, aqi, base_pm25, pm10) in enumerate(PROVINCE_SEED):
        provinces.append(ProvinceSnapshot(
            province_code=code, province_name=name, aqi=aqi,
            status=get_status(aqi), pm25=base_pm25, pm10=pm10,
        ))
        for sector_index, (sector, base_emission) in enumerate(EMISSION_SEED):
            emissions.append(EmissionRecord(
                province_code=code, province_name=name, year=2026, month=6,
                sector=sector,
                emission_tonnes=base_emission - province_index * 54
                + (120 if sector_index == 0 and code == "01" else 0),
            ))
        for year in (2025, 2026):
            for month_index in range(12):
                # Match JavaScript Math.round (ties towards +infinity), not
                # Python round (ties-to-even), to preserve original readings.
                seasonal = floor(cos((month_index / 12) * pi * 2) * 7 + 0.5)
                pm25 = max(8, base_pm25 - 13 + seasonal
                           + (4 if year == 2026 else 0) - province_index)
                trends.append(DashboardTrendRecord(
                    province_code=code, date=date(year, month_index + 1, 15),
                    pm25=pm25, pm10=pm25 + 20,
                    o3=35 + ((month_index + province_index) % 7) * 3,
                    no2=20 + ((month_index * 2 + province_index) % 9),
                    so2=7 + ((month_index + province_index) % 5),
                    co=5 + ((month_index + province_index) % 4),
                ))
    return DashboardData(
        province_snapshots=provinces,
        emission_records=emissions,
        emission_sectors=[sector for sector, _ in EMISSION_SEED],
        dashboard_trend_records=trends,
    )


class MockDashboardRepository:
    """Only this provider generates and caches illustrative data."""

    @cached_property
    def _snapshot(self) -> DashboardData:
        return _build_dashboard_data()

    def get_dashboard(self) -> DashboardData:
        # Prevent callers from mutating the cached demo data for later requests.
        return self._snapshot.model_copy(deep=True)
