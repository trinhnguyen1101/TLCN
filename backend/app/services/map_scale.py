"""Descriptive concentration bands; these are not AQI or health thresholds."""
from datetime import date
from math import isfinite

from app.schemas.dashboard import ConcentrationScale

# Shared absolute µg/m³ bands for comparing PM1/PM2.5/PM10 monthly concentrations.
# Application display convention, not regulatory or health thresholds.
PM_CONCENTRATION_BREAKPOINTS = (25.0, 50.0, 100.0)


def monthly_concentration_scale(observations: list[tuple[date, float | None]]) -> ConcentrationScale | None:
    valid = [(date, value) for date, value in observations if value is not None and isfinite(value)]
    if not valid:
        return None
    return ConcentrationScale(
        breakpoints=list(PM_CONCENTRATION_BREAKPOINTS),
        method="absolute_concentration", sample_count=len(valid),
        reference_start=min(date for date, _ in valid),
        reference_end=max(date for date, _ in valid),
    )
