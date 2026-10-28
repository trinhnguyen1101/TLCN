"""Pure provider-AQI row builders shared by the Supabase Gold adapter.

Provider indices are historical observations, not concentrations and not
outputs of the project's VN_AQI engine. The analytical hour is a storage slot;
the source observation/schedule/collection clocks remain independent fields.
"""
from datetime import timedelta, timezone
import json
import math


HOUR = timedelta(hours=1)
POLLUTANTS = ("pm25", "pm10", "co", "no2", "so2", "o3")
SCHEMES = {
    "waqi": "waqi-provider-reported-v1",
    "api_ninjas": "api-ninjas-provider-reported-v1",
}
PROFILES = {"waqi": "station_reference", "api_ninjas": "proxy_estimate"}


def utc(value):
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def aligned_hour(value):
    value = utc(value)
    return value.replace(minute=0, second=0, microsecond=0)


def provider_status(value, missing_reason=None):
    if value is None:
        return "not_calculable", missing_reason or "provider_value_missing"
    if isinstance(value, bool) or not math.isfinite(float(value)) or float(value) < 0:
        raise ValueError("Provider AQI must be a finite nonnegative number")
    return "valid", None


def overall_fact(*, source, release_id, series_id, hour_start, provider_aqi,
                 observed_at, scheduled_at, collected_at, observation_time_kind,
                 dominant_pollutants, input_run_id, input_snapshots):
    scheme = SCHEMES[source]
    status, reason = provider_status(provider_aqi)
    value = int(provider_aqi) if provider_aqi is not None else None
    if provider_aqi is not None and float(provider_aqi) != value:
        raise ValueError("Overall provider AQI must be integral; refusing to round")
    lineage = json.dumps({"silver_snapshots": input_snapshots, "input_run_ids": [input_run_id]}, sort_keys=True)
    return dict(
        release_id=release_id, series_id=series_id, aqi=value,
        dominant_pollutants=sorted(set(dominant_pollutants or [])), status=status,
        missing_reason=reason, category=None, category_label=None, color=None,
        method_version=scheme, applicability_profile=PROFILES[source],
        input_lineage_json=lineage, aqi_origin="provider", aqi_provider=source,
        provider_aqi_scheme=scheme, observed_at_utc=utc(observed_at),
        scheduled_at_utc=utc(scheduled_at), collected_at_utc=utc(collected_at),
        observation_time_kind=observation_time_kind, hour_start_utc=aligned_hour(hour_start),
    )


def pollutant_fact(*, source, release_id, series_id, pollutant, hour_start,
                   provider_sub_index, missing_reason, observed_at, scheduled_at,
                   collected_at, observation_time_kind, input_run_id, input_snapshots):
    if pollutant not in POLLUTANTS:
        raise ValueError("Unsupported provider AQI pollutant")
    scheme = SCHEMES[source]
    status, reason = provider_status(provider_sub_index, missing_reason)
    integral = (int(provider_sub_index) if provider_sub_index is not None
                and float(provider_sub_index).is_integer() else None)
    hour = aligned_hour(hour_start)
    lineage = json.dumps({"silver_snapshots": input_snapshots, "input_run_ids": [input_run_id]}, sort_keys=True)
    return dict(
        release_id=release_id, series_id=series_id, pollutant=pollutant,
        basis="provider_snapshot_slot", concentration=None, sub_index=integral,
        raw_index=float(provider_sub_index) if provider_sub_index is not None else None,
        bp_low=None, bp_high=None, index_low=None, index_high=None,
        input_count=1 if provider_sub_index is not None else 0, expected_count=1,
        completeness=1.0 if provider_sub_index is not None else 0.0, weight=None,
        # These are analytical slot bounds, not a claimed source measurement interval.
        window_start=hour, window_end=hour + HOUR, status=status, missing_reason=reason,
        method_version=scheme, applicability_profile=PROFILES[source],
        input_lineage_json=lineage, aqi_origin="provider", aqi_provider=source,
        provider_aqi_scheme=scheme,
        provider_sub_index=float(provider_sub_index) if provider_sub_index is not None else None,
        observed_at_utc=utc(observed_at), scheduled_at_utc=utc(scheduled_at),
        collected_at_utc=utc(collected_at), observation_time_kind=observation_time_kind,
        hour_start_utc=hour,
    )
