"""Pure configuration helpers shared by the Lakehouse Airflow DAGs.

This module deliberately has no Airflow dependency so validation and window
semantics can be tested without starting the scheduler.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import PurePosixPath
from urllib.parse import parse_qs, urlsplit


SAFE_COMPONENT = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
DATASET_ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
UTC = timezone.utc


@dataclass(frozen=True)
class LandingDataset:
    silver_job: str
    py_files: tuple[str, ...] = ("/opt/spark/work-dir/jobs/silver/common.py",)
    gold_kind: str | None = None


LANDING_DATASETS = {
    "reference/vietnam_administrative_divisions": LandingDataset(
        "admin_bronze_to_silver.py"
    ),
    "reference/vietnamese-provinces-database": LandingDataset(
        "admin_bronze_to_silver.py"
    ),
    "waqi/historical": LandingDataset(
        "waqi_bronze_to_silver.py", gold_kind="native"
    ),
    "climate_trace/climate_trace_vietnam": LandingDataset(
        "climate_trace_bronze_to_silver.py", gold_kind="native"
    ),
    "CAMS/EAC4": LandingDataset(
        "cams_bronze_to_silver.py",
        py_files=(
            "/opt/spark/work-dir/jobs/silver/common.py",
            "/opt/spark/work-dir/jobs/silver/cams_physics.py",
        ),
        gold_kind="cams",
    ),
}


def _date(value: object, field: str) -> date:
    try:
        parsed = date.fromisoformat(str(value))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be YYYY-MM-DD") from exc
    if parsed.isoformat() != str(value):
        raise ValueError(f"{field} must be canonical YYYY-MM-DD")
    return parsed


def _boolean(value: object, field: str) -> bool:
    if isinstance(value, bool):
        return value
    raise ValueError(f"{field} must be a JSON boolean")


def bronze_path(dataset: str, ingestion_date: str, batch_id: str) -> str:
    parts = PurePosixPath(dataset).parts
    source = parts[0].lower()
    name = "/".join(part.lower() for part in parts[1:])
    return (
        f"s3a://lakehouse/bronze/{source}/{name}/"
        f"ingestion_date={ingestion_date}/batch_id={batch_id}"
    )


def validate_landing_conf(conf: dict | None) -> dict:
    conf = conf or {}
    dataset = conf.get("dataset")
    if dataset not in LANDING_DATASETS:
        allowed = ", ".join(sorted(LANDING_DATASETS))
        raise ValueError(f"dataset must be one of: {allowed}")

    batch_id = str(conf.get("batch_id", ""))
    if not SAFE_COMPONENT.fullmatch(batch_id):
        raise ValueError("batch_id must contain only letters, digits, _ or -")
    ingestion_date = _date(conf.get("ingestion_date"), "ingestion_date").isoformat()
    publish_gold = _boolean(conf.get("publish_gold", False), "publish_gold")
    spec = LANDING_DATASETS[dataset]

    result = {
        "dataset": dataset,
        "batch_id": batch_id,
        "ingestion_date": ingestion_date,
        "bronze_path": bronze_path(dataset, ingestion_date, batch_id),
        "silver_job": spec.silver_job,
        "py_files": ",".join(spec.py_files),
        "publish_gold": publish_gold,
        "gold_kind": spec.gold_kind or "none",
    }

    if not publish_gold:
        result["gold_kind"] = "none"
        return result
    if spec.gold_kind is None:
        raise ValueError(f"{dataset} has no Gold adapter; set publish_gold=false")
    if spec.gold_kind == "native":
        return result

    gold = conf.get("gold")
    if not isinstance(gold, dict):
        raise ValueError("CAMS Gold publication requires a gold object")
    dataset_id = str(gold.get("dataset_id", ""))
    if not DATASET_ID.fullmatch(dataset_id):
        raise ValueError("gold.dataset_id has an invalid format")
    start = _date(gold.get("start_date"), "gold.start_date")
    end = _date(gold.get("end_date"), "gold.end_date")
    if start >= end:
        raise ValueError("gold date scope must be nonempty and end-exclusive")
    allow_validation = _boolean(
        gold.get("allow_validation", False), "gold.allow_validation"
    )
    result.update(
        gold_dataset_id=dataset_id,
        gold_start_date=start.isoformat(),
        gold_end_date=end.isoformat(),
        gold_kind="cams_validation" if allow_validation else "cams",
    )
    return result


def daily_window(data_interval_end: datetime) -> dict:
    """Normalize Airflow's 00:30 interval to a Vietnam calendar day."""
    if data_interval_end.tzinfo is None:
        raise ValueError("data_interval_end must be timezone-aware")
    try:
        from zoneinfo import ZoneInfo

        vietnam = ZoneInfo("Asia/Ho_Chi_Minh")
    except Exception as exc:  # pragma: no cover - system tzdata failure
        raise RuntimeError("Asia/Ho_Chi_Minh timezone is unavailable") from exc
    local_end = data_interval_end.astimezone(vietnam)
    window_end_local = local_end.replace(hour=0, minute=0, second=0, microsecond=0)
    window_start_local = window_end_local - timedelta(days=1)
    start = window_start_local.astimezone(UTC)
    end = window_end_local.astimezone(UTC)
    stamp_start = start.strftime("%Y%m%dT%H%M%SZ")
    stamp_end = end.strftime("%Y%m%dT%H%M%SZ")
    ingestion_date = window_end_local.date().isoformat()

    result = {
        "business_date": window_start_local.date().isoformat(),
        "end_date": window_end_local.date().isoformat(),
        "window_start_utc": start.isoformat().replace("+00:00", "Z"),
        "window_end_utc": end.isoformat().replace("+00:00", "Z"),
        "ingestion_date": ingestion_date,
    }
    for source, dataset in (("waqi", "live"), ("api_ninjas", "province_air_quality")):
        batch_id = f"{source}_{stamp_start}_{stamp_end}"
        result[f"{source}_batch_id"] = batch_id
        result[f"{source}_bronze_path"] = (
            f"s3a://lakehouse/bronze/{source}/{dataset}/"
            f"ingestion_date={ingestion_date}/batch_id={batch_id}"
        )
    return result


def parse_supabase_jdbc(jdbc: str) -> dict:
    if not jdbc.startswith("jdbc:postgresql://"):
        raise ValueError("AWS_CONNECTION_STRING must be a PostgreSQL JDBC URL")
    parsed = urlsplit(jdbc[5:])
    parameters = parse_qs(parsed.query, strict_parsing=True)
    try:
        user = parameters["user"][0]
        password = parameters["password"][0]
    except (KeyError, IndexError) as exc:
        raise ValueError("Supabase JDBC URL must include user and password") from exc
    if not parsed.hostname or not parsed.path.lstrip("/"):
        raise ValueError("Supabase JDBC URL is missing host or database")
    return {
        "host": parsed.hostname,
        "port": parsed.port or 5432,
        "dbname": parsed.path.lstrip("/"),
        "user": user,
        "password": password,
    }


def expected_utc_hours(window_start: datetime, window_end: datetime) -> set[datetime]:
    if window_start.tzinfo is None or window_end.tzinfo is None:
        raise ValueError("audit window must be timezone-aware")
    start = window_start.astimezone(UTC)
    end = window_end.astimezone(UTC)
    if start >= end or start.minute or start.second or start.microsecond:
        raise ValueError("audit window must be a nonempty exact-hour interval")
    hours = set()
    current = start
    while current < end:
        hours.add(current)
        current += timedelta(hours=1)
    return hours


def validate_missing_hour_limit(value: object) -> int:
    try:
        limit = int(str(value))
    except (TypeError, ValueError) as exc:
        raise ValueError("AIRFLOW_SUPABASE_MAX_MISSING_HOURS must be an integer") from exc
    if not 0 <= limit <= 23:
        raise ValueError("AIRFLOW_SUPABASE_MAX_MISSING_HOURS must be between 0 and 23")
    return limit
