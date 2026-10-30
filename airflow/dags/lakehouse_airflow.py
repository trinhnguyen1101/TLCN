"""Airflow-specific operators and runtime checks for the Lakehouse DAGs."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta
from urllib.request import urlopen

from airflow.exceptions import AirflowException
from airflow.providers.docker.operators.docker import DockerOperator
from airflow.utils.template import literal
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
RCLONE_IMAGE = os.getenv("LAKEHOUSE_RCLONE_IMAGE", "rclone/rclone:1.75.2")
DOCKER_URL = os.getenv("DOCKER_HOST", "tcp://docker-proxy:2375")
NETWORK = os.getenv("LAKEHOUSE_DOCKER_NETWORK", "lakehouse-net")

SPARK_MOUNTS = [
    Mount("/opt/spark/work-dir/jobs", "air-quality-airflow-spark-jobs", type="volume", read_only=True),
    Mount("/opt/spark/conf", "air-quality-airflow-spark-config", type="volume", read_only=True),
    Mount("/opt/spark/work-dir/lakehouse/silver", "air-quality-airflow-silver-definition", type="volume", read_only=True),
    Mount("/opt/spark/work-dir/lakehouse/gold", "air-quality-airflow-gold-definition", type="volume", read_only=True),
    Mount("/opt/spark/work-dir/landing", "air-quality-airflow-landing-data", type="volume", read_only=True),
    Mount("/opt/spark/work-dir/supabase-sync", "air-quality-airflow-supabase-sync", type="volume", read_only=True),
]

RCLONE_MOUNTS = [
    Mount("/opt/spark/work-dir/jobs", "air-quality-airflow-spark-jobs", type="volume", read_only=True),
    Mount("/data", "air-quality-airflow-supabase-sync", type="volume", read_only=False),
]


def _private_environment() -> dict[str, str]:
    names = (
        "MINIO_ROOT_USER",
        "MINIO_ROOT_PASSWORD",
        "AWS_CONNECTION_STRING",
        "AWS_SECRET_KEY",
    )
    environment = {
        name: os.environ[name] for name in names if os.environ.get(name)
    }
    # Iceberg S3FileIO uses AWS SDK v2, which requires an explicit region even
    # for the local MinIO endpoint. DockerOperator tasks do not inherit the
    # spark-master service environment.
    region = os.getenv("AWS_REGION", "us-east-1")
    environment["AWS_REGION"] = region
    environment["AWS_DEFAULT_REGION"] = os.getenv("AWS_DEFAULT_REGION", region)
    return environment


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
    command = spark_command(
        application=application,
        application_args=application_args,
        driver_memory=driver_memory,
        py_files=py_files,
    )
    return DockerOperator(
        task_id=task_id,
        command=command,
        **_spark_operator_kwargs(pool=pool, retries=retries),
    )


def spark_command(
    *,
    application: str,
    application_args: list[str],
    driver_memory: str,
    py_files: str | None = None,
) -> list[str]:
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
    return command


def _spark_operator_kwargs(*, pool: str, retries: int) -> dict:
    return {
        "image": SPARK_IMAGE,
        "docker_url": DOCKER_URL,
        # Pin the API so Docker SDK does not depend on proxy /version
        # negotiation. v1.45 is sufficient for these container operations and
        # is accepted by current Docker daemons and proxy v0.5.0.
        "api_version": os.getenv("LAKEHOUSE_DOCKER_API_VERSION", "1.45"),
        "network_mode": NETWORK,
        "mounts": SPARK_MOUNTS,
        "mount_tmp_dir": False,
        "auto_remove": "success",
        "force_pull": False,
        "private_environment": _private_environment(),
        "pool": pool,
        "retries": retries,
        "retry_delay": timedelta(minutes=10),
        "execution_timeout": timedelta(hours=8),
        "do_xcom_push": False,
    }


def mapped_spark_task(*, task_id: str, commands, pool: str, retries: int = 1):
    """Map one DockerOperator per complete spark-submit command."""
    return DockerOperator.partial(
        task_id=task_id,
        **_spark_operator_kwargs(pool=pool, retries=retries),
    ).expand(command=commands)


def check_supabase_s3_config() -> None:
    required = (
        "SUPABASE_S3_ENDPOINT",
        "SUPABASE_S3_REGION",
        "SUPABASE_S3_ACCESS_KEY_ID",
        "SUPABASE_S3_SECRET_ACCESS_KEY",
    )
    missing = [name for name in required if not os.getenv(name)]
    if missing:
        raise AirflowException(
            "Missing Supabase S3 settings for rclone: " + ", ".join(missing)
        )
    endpoint = os.environ["SUPABASE_S3_ENDPOINT"]
    if not endpoint.startswith("https://") or not endpoint.endswith("/storage/v1/s3"):
        raise AirflowException(
            "SUPABASE_S3_ENDPOINT must be the HTTPS endpoint ending in /storage/v1/s3"
        )


def _rclone_private_environment() -> dict[str, str]:
    return {
        "RCLONE_CONFIG_SUPABASE_TYPE": "s3",
        "RCLONE_CONFIG_SUPABASE_PROVIDER": "Other",
        "RCLONE_CONFIG_SUPABASE_ACCESS_KEY_ID": os.environ.get(
            "SUPABASE_S3_ACCESS_KEY_ID", ""
        ),
        "RCLONE_CONFIG_SUPABASE_SECRET_ACCESS_KEY": os.environ.get(
            "SUPABASE_S3_SECRET_ACCESS_KEY", ""
        ),
        "RCLONE_CONFIG_SUPABASE_ENDPOINT": os.environ.get(
            "SUPABASE_S3_ENDPOINT", ""
        ),
        "RCLONE_CONFIG_SUPABASE_REGION": os.environ.get("SUPABASE_S3_REGION", ""),
        "RCLONE_CONFIG_SUPABASE_FORCE_PATH_STYLE": "true",
        "RCLONE_CONFIG_SUPABASE_NO_CHECK_BUCKET": "true",
        "SUPABASE_S3_BUCKET": os.getenv("SUPABASE_S3_BUCKET", "raw-api"),
        "RCLONE_TRANSFERS": os.getenv("RCLONE_TRANSFERS", "8"),
        "RCLONE_CHECKERS": os.getenv("RCLONE_CHECKERS", "16"),
        "RCLONE_RETRIES": os.getenv("RCLONE_RETRIES", "5"),
        "RCLONE_LOW_LEVEL_RETRIES": os.getenv("RCLONE_LOW_LEVEL_RETRIES", "10"),
        "RCLONE_CONNECT_TIMEOUT": os.getenv("RCLONE_CONNECT_TIMEOUT", "15s"),
        "RCLONE_IO_TIMEOUT": os.getenv("RCLONE_IO_TIMEOUT", "5m"),
    }


def rclone_supabase_task(
    *, task_id: str, source: str, hour_prefixes: str, batch_id: str
) -> DockerOperator:
    if source not in {"waqi", "api_ninjas"}:
        raise ValueError(f"Unsupported Supabase source: {source}")
    destination = f"/data/{source}/{batch_id}"
    return DockerOperator(
        task_id=task_id,
        image=RCLONE_IMAGE,
        entrypoint=["/bin/sh"],
        command=[
            literal("/opt/spark/work-dir/jobs/bronze/rclone_supabase_day.sh"),
            source,
            hour_prefixes,
            destination,
        ],
        docker_url=DOCKER_URL,
        api_version=os.getenv("LAKEHOUSE_DOCKER_API_VERSION", "1.45"),
        network_mode=NETWORK,
        mounts=RCLONE_MOUNTS,
        user=os.getenv("LAKEHOUSE_DATA_USER", "1000:1000"),
        mount_tmp_dir=False,
        auto_remove="success",
        force_pull=False,
        private_environment=_rclone_private_environment(),
        pool="bronze_sync",
        retries=2,
        retry_delay=timedelta(minutes=5),
        execution_timeout=timedelta(hours=2),
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
        os.getenv("AIRFLOW_SUPABASE_MAX_MISSING_HOURS", "23")
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
