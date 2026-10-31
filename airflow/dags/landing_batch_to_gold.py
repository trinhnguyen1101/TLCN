"""Manual orchestration for every immutable Landing dataset through Silver/Gold."""

from __future__ import annotations

from datetime import timedelta

import pendulum
from airflow import DAG
from airflow.operators.empty import EmptyOperator
from airflow.operators.python import BranchPythonOperator, PythonOperator
from airflow.utils.task_group import TaskGroup
from airflow.utils.trigger_rule import TriggerRule

from lakehouse_airflow import (
    check_services,
    mapped_spark_task,
    spark_command,
    spark_task,
)
from lakehouse_config import resolve_landing_full_conf


# Edit this configuration to change the scope of a normal UI Trigger.
# Dates are Vietnam reporting dates; end_date is exclusive. This processes
# the complete current hourly archive, not the three-hour validation pilot.
DEFAULT_FULL_RUN_CONF = {
    "publish_gold": True,
    "gold": {
        "dataset_id": "5ca22d69be491cfe59e338e641c6b2238fbfb9555358ae440e0ce1e05c4c5f5f",
        "start_date": "2003-01-01",
        "end_date": "2026-01-02",
        "chunk_days": 14,
        "allow_validation": False,
    },
}


DOC = """
Click Trigger DAG with empty/default configuration to process all five
populated registered Landing datasets through Bronze, Silver and Gold.
No JSON editing is required. DEFAULT_FULL_RUN_CONF in this file defines
the hourly CAMS dataset, 2003-01-01 through 2026-01-02 (exclusive), and
14-day Gold chunks. ERA5 is empty and live providers use their separate DAG.
Silver reads the full source archive; the dates bound Gold only.

Batch IDs and UTC ingestion dates derive from the DagRun and remain stable
on task retry/clear. A new trigger creates a new batch. Explicit DagRun
configuration overrides these defaults, including publish_gold=false.

The Graph contains two TaskGroups. Each expands to the four top-level Landing
folders: `cams`, `climate_trace`, `reference`, and `waqi`. The `reference`
folder expands once more because it contains two independent datasets.

`publish_gold` defaults to true for this DAG. Native Gold is published after all
five Silver jobs succeed. CAMS Gold uses the configured hourly source identity
and scope. The full CAMS date range is
automatically split into mapped Gold tasks; no external backfill script is
required.

The `landing_to_bronze` and `bronze_to_silver` task logs emit one
`FILE_PROGRESS` line per file. Search the task log for `FILE_PROGRESS` to see
the exact source path, destination/object path, ordinal, size and SHA-256 while
the batch is running.
"""


def _validate(**context) -> dict:
    dag_run = context.get("dag_run")
    return resolve_landing_full_conf(
        dag_run.conf if dag_run else None,
        defaults=DEFAULT_FULL_RUN_CONF,
        run_id=dag_run.run_id if dag_run else context["run_id"],
        logical_date=dag_run.logical_date if dag_run else context["logical_date"],
    )


def _gold_branch(config: dict) -> str:
    return "publish_native_gold" if config["publish_gold"] else "no_gold"


def _cams_gold_commands(config: dict) -> list[list[str]]:
    validation_args = (
        ["--allow-validation"] if config["gold_kind"] == "cams_validation" else []
    )
    return [
        spark_command(
            application="/opt/spark/work-dir/jobs/gold/run.py",
            application_args=[
                "--schema",
                "gold",
                "--silver-schema",
                "silver",
                "--adapter",
                "cams",
                "--dataset-id",
                config["gold_dataset_id"],
                "--start-date",
                chunk["start_date"],
                "--end-date",
                chunk["end_date"],
                *validation_args,
            ],
            driver_memory="2g",
        )
        for chunk in config["gold_chunks"]
    ]


def _dataset_value(key: str, field: str) -> str:
    return f"{{{{ ti.xcom_pull(task_ids='validate_run')['datasets']['{key}']['{field}'] }}}}"


CONFIG = "{{ ti.xcom_pull(task_ids='validate_run') }}"
DATASET_KEYS = (
    "cams", "climate_trace", "reference_admin", "reference_provinces", "waqi",
)


def _landing_task(task_id: str, key: str):
    return spark_task(
        task_id=task_id,
        application="/opt/spark/work-dir/jobs/bronze/landing_to_bronze.py",
        application_args=[
            "--dataset", _dataset_value(key, "dataset"),
            "--batch-id", _dataset_value(key, "batch_id"),
            "--ingestion-date", _dataset_value(key, "ingestion_date"),
        ],
        driver_memory="512m",
        pool="bronze_sync",
        retries=2,
    )


def _silver_task(task_id: str, key: str):
    return spark_task(
        task_id=task_id,
        application="/opt/spark/work-dir/jobs/silver/" + _dataset_value(key, "silver_job"),
        application_args=["--bronze-path", _dataset_value(key, "bronze_path")],
        driver_memory="1g",
        py_files=_dataset_value(key, "py_files"),
        pool="iceberg_writer",
    )


with DAG(
    dag_id="landing_batch_to_gold",
    description="Trigger to process all five populated Landing datasets through Bronze, Silver and Gold",
    doc_md=DOC,
    schedule=None,
    start_date=pendulum.datetime(2026, 1, 1, tz="Asia/Ho_Chi_Minh"),
    catchup=False,
    max_active_runs=1,
    render_template_as_native_obj=True,
    default_args={"owner": "lakehouse", "retries": 0},
    tags=["lakehouse", "landing", "batch"],
) as dag:
    validate_run = PythonOperator(
        task_id="validate_run",
        python_callable=_validate,
    )
    services = PythonOperator(
        task_id="check_lakehouse_services",
        python_callable=check_services,
        retries=2,
        retry_delay=timedelta(minutes=2),
    )
    with TaskGroup(
        group_id="landing_to_bronze",
        tooltip="All four top-level folders under data/landing",
    ):
        landing_tasks = {
            "cams": _landing_task("cams", "cams"),
            "climate_trace": _landing_task("climate_trace", "climate_trace"),
            "waqi": _landing_task("waqi", "waqi"),
        }
        with TaskGroup(
            group_id="reference",
            tooltip="Two independent datasets under data/landing/reference",
        ):
            landing_tasks["reference_admin"] = _landing_task(
                "administrative_divisions", "reference_admin"
            )
            landing_tasks["reference_provinces"] = _landing_task(
                "vietnamese_provinces_database", "reference_provinces"
            )

    with TaskGroup(
        group_id="bronze_to_silver",
        tooltip="Dataset-specific Silver adapters for all Landing folders",
    ):
        silver_tasks = {
            "cams": _silver_task("cams", "cams"),
            "climate_trace": _silver_task("climate_trace", "climate_trace"),
            "waqi": _silver_task("waqi", "waqi"),
        }
        with TaskGroup(
            group_id="reference",
            tooltip="Two administrative-reference Silver adapters",
        ):
            silver_tasks["reference_admin"] = _silver_task(
                "administrative_divisions", "reference_admin"
            )
            silver_tasks["reference_provinces"] = _silver_task(
                "vietnamese_provinces_database", "reference_provinces"
            )

    for key in DATASET_KEYS:
        landing_tasks[key].doc_md = """
        Copies and verifies this immutable Landing dataset. Search the log for
        `FILE_PROGRESS` to follow every copied or reused file.
        """
        silver_tasks[key].doc_md = """
        Runs the dataset-specific Silver adapter. Search the log for
        `FILE_PROGRESS` to see the Bronze objects selected by the adapter.
        """

    all_silver_complete = EmptyOperator(task_id="all_silver_complete")
    choose_gold = BranchPythonOperator(
        task_id="choose_gold_path",
        python_callable=_gold_branch,
        op_kwargs={"config": CONFIG},
    )
    no_gold = EmptyOperator(task_id="no_gold")

    publish_native_gold = spark_task(
        task_id="publish_native_gold",
        application="/opt/spark/work-dir/jobs/gold/native_sources.py",
        application_args=["--schema", "gold"],
        driver_memory="2g",
        pool="iceberg_writer",
    )
    build_cams_gold_commands = PythonOperator(
        task_id="build_cams_gold_commands",
        python_callable=_cams_gold_commands,
        op_kwargs={"config": CONFIG},
    )
    publish_cams_gold_chunks = mapped_spark_task(
        task_id="publish_cams_gold_chunks",
        commands=build_cams_gold_commands.output,
        pool="iceberg_writer",
    )
    complete = EmptyOperator(
        task_id="landing_pipeline_complete",
        trigger_rule=TriggerRule.NONE_FAILED_MIN_ONE_SUCCESS,
    )

    validate_run >> services >> list(landing_tasks.values())
    for key in DATASET_KEYS:
        landing_tasks[key] >> silver_tasks[key] >> all_silver_complete
    all_silver_complete >> choose_gold
    choose_gold >> [no_gold, publish_native_gold]
    no_gold >> complete
    publish_native_gold >> build_cams_gold_commands >> publish_cams_gold_chunks
    publish_cams_gold_chunks >> complete
