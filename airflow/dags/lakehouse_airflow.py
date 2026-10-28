"""Airflow-specific operators and runtime checks for the Lakehouse DAGs."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta
from urllib.request import urlopen

from airflow.exceptions import AirflowException
from airflow.providers.docker.operators.docker import DockerOperator
from docker.types import Mount

from lakehouse_config import (
    SHA256,
    expected_utc_hours,
    parse_supabase_jdbc,
    validate_missing_hour_limit,
)


LOG = logging.getLogger(__name__)
SPARK_IMAGE = os.getenv(
    "LAKEHOUSE_SPARK_IMAGE", "air-quality-spark:3.5.4-iceberg-1.7.1"
)
DOCKER_URL = os.getenv("DOCKER_HOST", "tcp://docker-proxy:2375")
NETWORK = os.getenv("LAKEHOUSE_DOCKER_NETWORK", "lakehouse-net")

SPARK_MOUNTS = [
    Mount("/opt/spark/work-dir/jobs", "air-quality-airflow-spark-jobs", type="volume", read_only=True),
    Mount("/opt/spark/conf", "air-quality-airflow-spark-config", type="volume", read_only=True),
    Mount("/opt/spark/work-dir/lakehouse/silver", "air-quality-airflow-silver-definition", type="volume", read_only=True),
    Mount("/opt/spark/work-dir/lakehouse/gold", "air-quality-airflow-gold-definition", type="volume", read_only=True),
    Mount("/opt/spark/work-dir/landing", "air-quality-airflow-landing-data", type="volume", read_only=True),
]


def _private_environment() -> dict[str, str]:
    names = (
        "MINIO_ROOT_USER",
        "MINIO_ROOT_PASSWORD",
        "AWS_CONNECTION_STRING",
        "AWS_SECRET_KEY",
        "AWS_REGION",
        "AWS_DEFAULT_REGION",
    )
    return {name: os.environ[name] for name in names if os.environ.get(name)}


def spark_task(
    *,
    task_id: str,
    application: str,
    application_args: list[str],
    driver_memory: str,
    pool: str,
    py_files: str | None = None,
    retries: int = 1,
) -> DockerOperator:
    command = [
        "/opt/spark/bin/spark-submit",
        "--master",
        "local[1]",
        "--driver-memory",
        driver_memory,
        "--conf",
        "spark.sql.shuffle.partitions=4",
    ]
    if py_files:
        command.extend(["--py-files", py_files])
    command.extend([application, *application_args])
    return DockerOperator(
        task_id=task_id,
        image=SPARK_IMAGE,
        command=command,
        docker_url=DOCKER_URL,
        # Pin the API so Docker SDK does not depend on proxy /version
        # negotiation. v1.45 is sufficient for these container operations and
        # is accepted by current Docker daemons and proxy v0.5.0.
        api_version=os.getenv("LAKEHOUSE_DOCKER_API_VERSION", "1.45"),
        network_mode=NETWORK,
        mounts=SPARK_MOUNTS,
        mount_tmp_dir=False,
        auto_remove="success",
        force_pull=False,
        private_environment=_private_environment(),
        pool=pool,
        retries=retries,
        retry_delay=timedelta(minutes=10),
        execution_timeout=timedelta(hours=8),
        do_xcom_push=False,
    )


def check_services() -> None:
    endpoints = {
        "Docker API proxy": "http://docker-proxy:2375/_ping",
        "MinIO": "http://minio:9000/minio/health/live",
        "Nessie": "http://nessie:19120/api/v2/config",
        "Trino": "http://trino:8080/v1/info",
    }
    failures = []
    for name, endpoint in endpoints.items():
        try:
            with urlopen(endpoint, timeout=10) as response:
                if response.status >= 300:
                    failures.append(f"{name}: HTTP {response.status}")
        except Exception as exc:  # network errors need the endpoint in task log
            failures.append(f"{name}: {type(exc).__name__}: {exc}")
    if failures:
        raise AirflowException("Service checks failed: " + "; ".join(failures))


def audit_supabase_collection_runs(window: dict) -> dict:
    """Check daily collection coverage without fabricating missing hours."""
    import psycopg2

    jdbc = os.environ.get("AWS_CONNECTION_STRING", "")
    settings = parse_supabase_jdbc(jdbc)
    start = datetime.fromisoformat(window["window_start_utc"].replace("Z", "+00:00"))
    end = datetime.fromisoformat(window["window_end_utc"].replace("Z", "+00:00"))
    expected = expected_utc_hours(start, end)
    if len(expected) != 24:
        raise AirflowException(f"Expected a 24-hour Vietnam daily window, got {len(expected)}")
    max_missing = validate_missing_hour_limit(
        os.getenv("AIRFLOW_SUPABASE_MAX_MISSING_HOURS", "1")
    )

    query = """
        SELECT source, scheduled_hour_utc, status, attempt_number,
               manifest_object_path, manifest_sha256
        FROM public.collection_runs
        WHERE source IN ('waqi', 'api_ninjas')
          AND scheduled_hour_utc >= %s
          AND scheduled_hour_utc < %s
          AND status IN ('succeeded', 'partial')
        ORDER BY source, scheduled_hour_utc, attempt_number DESC
    """
    with psycopg2.connect(
        **settings,
        sslmode="require",
        connect_timeout=15,
        options="-c default_transaction_read_only=on",
    ) as connection:
        with connection.cursor() as cursor:
            cursor.execute(query, (start, end))
            rows = cursor.fetchall()

    summary = {}
    for source in ("waqi", "api_ninjas"):
        by_hour = {}
        for row_source, hour, status, attempt, manifest_path, manifest_sha in rows:
            if row_source != source:
                continue
            normalized = hour.astimezone(start.tzinfo)
            # Query ordering makes the highest eligible attempt win.
            by_hour.setdefault(
                normalized,
                (status, attempt, manifest_path, manifest_sha),
            )
        missing = sorted(expected - set(by_hour))
        invalid = [
            hour
            for hour, (_, _, path, digest) in by_hour.items()
            if not path or not SHA256.fullmatch(str(digest))
        ]
        if invalid:
            raise AirflowException(
                f"Supabase audit failed for {source}: "
                f"invalid_manifests={[value.isoformat() for value in sorted(invalid)]}"
            )
        if len(missing) > max_missing:
            raise AirflowException(
                f"Supabase audit failed for {source}: eligible_hours={len(by_hour)}/24, "
                f"missing_hours={[value.isoformat() for value in missing]}, "
                f"allowed_missing_hours={max_missing}"
            )
        if missing:
            LOG.warning(
                "Supabase coverage warning source=%s eligible_hours=%d/24 "
                "missing_hours=%s allowed_missing_hours=%d; pipeline continues without fabricated rows",
                source,
                len(by_hour),
                [value.isoformat() for value in missing],
                max_missing,
            )
        partial = sum(value[0] == "partial" for value in by_hour.values())
        summary[source] = {
            "eligible_hours": len(by_hour),
            "partial_hours": partial,
            "missing_hours": [value.isoformat() for value in missing],
            "coverage_ratio": len(by_hour) / 24,
        }
        LOG.info(
            "Supabase audit source=%s eligible_hours=%d/24 partial=%d missing=%d",
            source,
            len(by_hour),
            partial,
            len(missing),
        )
    return summary
