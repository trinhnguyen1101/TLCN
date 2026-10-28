"""UTC hour-start slots; local VN day [00:00, next 00:00).

PDF end labels 01:00..00:00 map to these intervals. No truncation/rounding
of concentrations. Display AQI uses explicit project decimal half-up policy.
Daily gate 24/24 (and all 24 full O3 rolling windows) is project policy.
"""
from datetime import datetime, timedelta, timezone, time
from decimal import Decimal, ROUND_HALF_UP
import math
from .reference import BREAKPOINTS, INDICES, CATEGORIES, METHOD_VERSION, POLLUTANTS, PROFILES

UTC = timezone.utc
VN = timezone(timedelta(hours=7), "Asia/Ho_Chi_Minh")
HOUR = timedelta(hours=1)


def valid(value):
    try:
        return value is not None and not isinstance(value, bool) and math.isfinite(value) and value >= 0
    except (TypeError, ValueError, OverflowError):
        return False


def round_aqi(value):
    return int(Decimal(str(value)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def category(value):
    if value is None:
        return None, None, None
    for upper, code, label, color in CATEGORIES:
        if 0 <= value <= upper:
            return code, label, color
    raise ValueError("AQI outside display range")


def subindex(pollutant, concentration, basis="mean1h"):
    if pollutant not in POLLUTANTS:
        raise ValueError("Unsupported VN_AQI pollutant")
    if basis not in {"mean1h", "max1h", "nowcast12h", "mean24h", "max8h"} or (basis == "max8h" and pollutant != "o3"):
        raise ValueError("Unsupported averaging basis")
    key = "o3_8h" if pollutant == "o3" and basis == "max8h" else pollutant
    points = BREAKPOINTS[key]
    result = dict(pollutant=pollutant, basis=basis, concentration=concentration,
                  sub_index=None, raw_index=None, bp_low=None, bp_high=None,
                  index_low=None, index_high=None, status="not_calculable", missing_reason=None)
    if not valid(concentration):
        result["missing_reason"] = "missing_concentration" if concentration is None else "invalid_concentration"
        result["concentration"] = None
        return result
    # O3 8h >400 is not eligible, unlike terminal >= cutoffs for other bases.
    if key == "o3_8h" and concentration > points[-1]:
        result["missing_reason"] = "o3_8h_above_domain"
        return result
    if concentration >= points[-1]:
        low, high = len(points) - 2, len(points) - 1
        raw = float(INDICES[high])
    else:
        high = next(i for i in range(1, len(points)) if concentration <= points[i])
        low = high - 1
        raw = INDICES[low] + (INDICES[high] - INDICES[low]) * (
            concentration - points[low]) / (points[high] - points[low])
    result.update(sub_index=round_aqi(raw), raw_index=raw, bp_low=float(points[low]),
                  bp_high=float(points[high]), index_low=INDICES[low], index_high=INDICES[high],
                  status="valid", missing_reason=None)
    return result


def nowcast(slots):
    """Exactly 12 slots, newest first; missing slots keep their real age.

    PDF p4: w>0.5 normalized weighted mean; w=0.5 unnormalized sum
    of (1/2)^i*c_i, i=1..12. PDF p5: missing terms have zero weight.
    """
    if len(slots) != 12:
        raise ValueError("NowCast requires 12 fixed hourly slots")
    values = [v if valid(v) else None for v in slots]
    count = sum(v is not None for v in values)
    if sum(v is not None for v in values[:3]) < 2:
        return None, count, None, "insufficient_recent_pm_2_of_3"
    present = [v for v in values if v is not None]
    maximum = max(present)
    weight = max(0.5, min(present) / maximum) if maximum else 1.0
    if weight == 0.5:
        value = sum((0.5 ** (i + 1)) * v for i, v in enumerate(values) if v is not None)
    else:
        numerator = sum((weight ** i) * v for i, v in enumerate(values) if v is not None)
        denominator = sum(weight ** i for i, v in enumerate(values) if v is not None)
        value = numerator / denominator
    return value, count, weight, None


def check_hour(hour):
    if hour.tzinfo is None or hour.utcoffset() != timedelta(0) or hour.minute or hour.second or hour.microsecond:
        raise ValueError("An aligned, timezone-aware UTC hour is required")


def eligible(row, profile):
    if profile not in PROFILES:
        raise ValueError("Unknown applicability profile")
    return (row is not None and row.get("temporal_support") == "hourly_mean"
            and row.get("source_resolution_minutes") == 60 and row.get("unit") == "ug/m3"
            and row.get("measurement_kind", "concentration") == "concentration"
            and row.get("quality_status") == "ok" and valid(row.get("value"))
            and row.get("vertical_support") in ("surface", "model_surface", "model_level_60")
            and (profile != "station_reference" or (
                row.get("spatial_representation") == "station"
                and row.get("vertical_support") == "surface"
                and row.get("reference_eligible") is True)))


def aggregate_indices(components):
    good = [r for r in components if r["raw_index"] is not None]
    if not any(r["pollutant"] in ("pm25", "pm10") for r in good):
        return dict(aqi=None, dominant_pollutants=[], status="not_calculable",
                    missing_reason="requires_eligible_pm", category=None, category_label=None, color=None)
    raw = max(r["raw_index"] for r in good)
    value = round_aqi(raw)
    code, label, color = category(value)
    return dict(aqi=value, dominant_pollutants=sorted({r["pollutant"] for r in good
                if math.isclose(r["raw_index"], raw, rel_tol=0, abs_tol=1e-10)}),
                status="valid", missing_reason=None, category=code, category_label=label, color=color)


def hourly(hour, readings, profile="area_estimate"):
    """readings maps (UTC hour_start, pollutant) to a semantic measurement dict."""
    check_hour(hour)
    components = []
    for pollutant in POLLUTANTS:
        pm = pollutant in ("pm25", "pm10")
        hours = [hour - HOUR * i for i in range(12 if pm else 1)]
        rows = [readings.get((h, pollutant)) for h in hours]
        values = [r["value"] if eligible(r, profile) else None for r in rows]
        if pm:
            concentration, count, weight, reason = nowcast(values)
        else:
            concentration, count, weight, reason = values[0], int(values[0] is not None), None, None
        result = subindex(pollutant, concentration, "nowcast12h" if pm else "mean1h")
        if concentration is None:
            result["missing_reason"] = ("ineligible_temporal_unit_qc_or_profile" if any(r is not None and not eligible(r, profile) for r in rows)
                                        else reason or "missing_concentration")
        result.update(input_count=count, expected_count=len(hours), completeness=count / len(hours),
                      weight=weight, window_start=min(hours), window_end=hour + HOUR)
        components.append(result)
    overall = aggregate_indices(components)
    overall.update(method_version=METHOD_VERSION, applicability_profile=profile)
    return components, overall


def local_day_bounds(day):
    start = datetime.combine(day, time(), VN).astimezone(UTC)
    return start, start + timedelta(days=1)


def rolling8(hour, readings, profile):
    rows = [readings.get((hour - i * HOUR, "o3")) for i in range(8)]
    values = [r["value"] for r in rows if eligible(r, profile)]
    return (sum(values) / 8 if len(values) == 8 else None), len(values)


def daily(day, readings, profile="area_estimate"):
    start, end = local_day_bounds(day)
    hours = [start + i * HOUR for i in range(24)]
    components = []
    for pollutant in POLLUTANTS:
        rows = [readings.get((h, pollutant)) for h in hours]
        values = [r["value"] for r in rows if eligible(r, profile)]
        count = len(values)
        pm = pollutant in ("pm25", "pm10")
        concentration = (sum(values) / 24 if pm else max(values)) if count == 24 else None
        component = subindex(pollutant, concentration, "mean24h" if pm else "max1h")
        component.update(input_count=count, expected_count=24, completeness=count/24,
                         weight=None, window_start=start, window_end=end)
        if count < 24:
            component["missing_reason"] = "project_daily_requires_24_hourly_means"
        components.append(component)
        if pollutant == "o3":
            windows = [rolling8(h, readings, profile)[0] for h in hours]
            valid_windows = [v for v in windows if v is not None]
            concentration8 = max(valid_windows) if len(valid_windows) == 24 else None
            c8 = subindex("o3", concentration8, "max8h")
            c8.update(input_count=len(valid_windows), expected_count=24, completeness=len(valid_windows)/24,
                      weight=None, window_start=start - 7 * HOUR, window_end=end)
            if len(valid_windows) < 24:
                c8["missing_reason"] = "project_o3_requires_24_complete_8h_windows"
            components.append(c8)
    # O3 daily: max of basis subindices (verified by worked example, PDF p9).
    # If 8h is unknown, suppress 1h as a daily O3 candidate (conservative gate).
    selected = [c for c in components if c["pollutant"] != "o3"]
    ozone = [c for c in components if c["pollutant"] == "o3"]
    if all(c["input_count"] == 24 for c in ozone):
        selected.extend(c for c in ozone if c["raw_index"] is not None)
    overall = aggregate_indices(selected)
    overall.update(method_version=METHOD_VERSION, applicability_profile=profile)
    return components, overall


def affected_hours(changed_hour):
    check_hour(changed_hour)
    return dict(pm_nowcast_end_exclusive=changed_hour + 12 * HOUR,
                o3_rolling_end_exclusive=changed_hour + 8 * HOUR)
