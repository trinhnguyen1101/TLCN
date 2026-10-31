"""Pure configuration helpers shared by the Lakehouse Airflow DAGs.

This module deliberately has no Airflow dependency so validation and window
semantics can be tested without starting the scheduler.
"""

from __future__ import annotations

import re
import hashlib
from copy import deepcopy
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import PurePosixPath
from urllib.parse import parse_qs, urlsplit


SAFE_COMPONENT = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
DATASET_ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
UTC = timezone.utc
MAX_AIRFLOW_MAP_LENGTH = 1024
DEFAULT_GOLD_CHUNK_DAYS = 14


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

LANDING_FULL_RUN = {
    "cams": "CAMS/EAC4",
    "climate_trace": "climate_trace/climate_trace_vietnam",
    "reference_admin": "reference/vietnam_administrative_divisions",
    "reference_provinces": "reference/vietnamese-provinces-database",
    "waqi": "waqi/historical",
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


def _integer(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field} must be a JSON integer")
    return value


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


def validate_landing_all_conf(conf: dict | None) -> dict:
    """Validate one manual run that ingests every current Landing dataset."""
    conf = conf or {}
    batch_id = str(conf.get("batch_id", ""))
    if not SAFE_COMPONENT.fullmatch(batch_id):
        raise ValueError("batch_id must contain only letters, digits, _ or -")
    ingestion_date = _date(conf.get("ingestion_date"), "ingestion_date").isoformat()
    publish_gold = _boolean(conf.get("publish_gold", False), "publish_gold")

    datasets = {}
    for key, dataset in LANDING_FULL_RUN.items():
        suffix = key.replace("_", "-")
        child_batch_id = f"{batch_id}-{suffix}"
        if not SAFE_COMPONENT.fullmatch(child_batch_id):
            raise ValueError(
                "batch_id is too long after adding per-dataset suffixes"
            )
        datasets[key] = validate_landing_conf({
            "dataset": dataset,
            "batch_id": child_batch_id,
            "ingestion_date": ingestion_date,
            "publish_gold": False,
        })

    result = {
        "batch_id": batch_id,
        "ingestion_date": ingestion_date,
        "publish_gold": publish_gold,
        "datasets": datasets,
    }
    if not publish_gold:
        return result

    # Native Gold publishes WAQI historical and Climate TRACE together. CAMS
    # additionally needs the explicit scope required by its existing adapter.
    cams = validate_landing_conf({
        "dataset": "CAMS/EAC4",
        "batch_id": datasets["cams"]["batch_id"],
        "ingestion_date": ingestion_date,
        "publish_gold": True,
        "gold": conf.get("gold"),
    })
    result.update(
        gold_dataset_id=cams["gold_dataset_id"],
        gold_start_date=cams["gold_start_date"],
        gold_end_date=cams["gold_end_date"],
        gold_kind=cams["gold_kind"],
    )
    gold = conf["gold"]
    chunk_days = _integer(
        gold.get("chunk_days", DEFAULT_GOLD_CHUNK_DAYS), "gold.chunk_days"
    )
    if not 1 <= chunk_days <= 31:
        raise ValueError("gold.chunk_days must be between 1 and 31")

    start = date.fromisoformat(cams["gold_start_date"])
    end = date.fromisoformat(cams["gold_end_date"])
    chunks = []
    cursor = start
    while cursor < end:
        stop = min(cursor + timedelta(days=chunk_days), end)
        chunks.append({
            "start_date": cursor.isoformat(),
            "end_date": stop.isoformat(),
        })
        cursor = stop
    if len(chunks) > MAX_AIRFLOW_MAP_LENGTH:
        raise ValueError(
            f"Gold scope creates {len(chunks)} mapped tasks; increase "
            f"gold.chunk_days so it creates at most {MAX_AIRFLOW_MAP_LENGTH}"
        )
    result.update(gold_chunk_days=chunk_days, gold_chunks=chunks)
    return result


def resolve_landing_full_conf(
    conf: dict | None, *, defaults: dict, run_id: str, logical_date: datetime
) -> dict:
    """Resolve a UI trigger without requiring editable JSON.

    Identity derives from the DagRun, so retry/clear reuses the same Bronze
    paths, while a new trigger gets distinct immutable batch identities.
    Explicit configuration remains available for automated callers.
    """
    if not run_id or logical_date.tzinfo is None:
        raise ValueError("A stable DagRun ID and timezone-aware logical date are required")
    if conf is not None and not isinstance(conf, dict):
        raise ValueError("DagRun configuration must be a JSON object")
    config = deepcopy(defaults)
    config["batch_id"] = "landing-full-" + hashlib.sha256(run_id.encode()).hexdigest()[:24]
    config["ingestion_date"] = logical_date.astimezone(UTC).date().isoformat()
    overrides = conf or {}
    for key, value in overrides.items():
        if key == "gold" and isinstance(value, dict):
            config["gold"].update(deepcopy(value))
        else:
            config[key] = deepcopy(value)
    return validate_landing_all_conf(config)


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
        # Supabase stores objects under UTC hour prefixes.  A Vietnam calendar
        # day crosses two UTC dates, so rclone must receive the exact 24
        # prefixes instead of copying either UTC date folder wholesale.
        "rclone_hour_prefixes": ",".join(
            (start + timedelta(hours=offset)).strftime("%Y/%m/%d/%H")
            for offset in range(24)
        ),
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
