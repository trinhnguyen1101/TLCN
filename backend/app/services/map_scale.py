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


def dashboard_concentration_scale(metric, observations):
    """Standalone gas display quartiles in physical units, never AQI breakpoints."""
    if metric in ('pm1','pm25','pm10'):
        return monthly_concentration_scale(observations)
    valid=[(instant,value) for instant,value in observations if value is not None and isfinite(value)]
    if not valid:
        return None
    values=sorted({value for _,value in valid})
    if len(values)<4:
        return None
    cuts=[values[int((len(values)-1)*fraction)] for fraction in (.25,.5,.75)]
    if len(set(cuts))!=3:
        return None
    return ConcentrationScale(breakpoints=cuts,method='absolute_concentration',sample_count=len(valid),
        reference_start=min(instant for instant,_ in valid),reference_end=max(instant for instant,_ in valid),
        version='selected-window-quartiles-v1',statistic='province_time_values',reference_kind='selected_window_distribution',
        note='Quartile concentration display for the selected window; not AQI or health thresholds.')
