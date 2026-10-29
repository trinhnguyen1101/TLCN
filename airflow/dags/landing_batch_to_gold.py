"""Manual orchestration for every immutable Landing dataset through Silver/Gold."""

from __future__ import annotations

from datetime import timedelta

import pendulum
from airflow import DAG
from airflow.operators.empty import EmptyOperator
from airflow.operators.python import BranchPythonOperator, PythonOperator
from airflow.utils.task_group import TaskGroup
from airflow.utils.trigger_rule import TriggerRule

from lakehouse_airflow import check_services, spark_task
from lakehouse_config import validate_landing_all_conf


DOC = """
Trigger this DAG once to process every dataset currently stored under Landing:

```json
{
  "batch_id": "landing-full-20261029",
  "ingestion_date": "2026-10-29",
  "publish_gold": false
}
```

The Graph contains two TaskGroups. Each expands to the four top-level Landing
folders: `cams`, `climate_trace`, `reference`, and `waqi`. The `reference`
folder expands once more because it contains two independent datasets.

`publish_gold` defaults to false. When true, Native Gold is published after all
five Silver jobs succeed and CAMS Gold additionally requires `gold.dataset_id`,
`gold.start_date`, `gold.end_date`, and optionally `gold.allow_validation`.

The `landing_to_bronze` and `bronze_to_silver` task logs emit one
`FILE_PROGRESS` line per file. Search the task log for `FILE_PROGRESS` to see
the exact source path, destination/object path, ordinal, size and SHA-256 while
the batch is running.
"""


def _validate(**context) -> dict:
    dag_run = context.get("dag_run")
    return validate_landing_all_conf(dag_run.conf if dag_run else None)


def _gold_branch(config: dict) -> str:
    return "publish_native_gold" if config["publish_gold"] else "no_gold"


def _cams_gold_branch(config: dict) -> str:
    return {
        "cams": "publish_cams_gold",
        "cams_validation": "publish_cams_validation_gold",
    }[config["gold_kind"]]


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
    description="One manual run for all Landing datasets through Silver and optional Gold",
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
    choose_cams_gold = BranchPythonOperator(
        task_id="choose_cams_gold_path",
        python_callable=_cams_gold_branch,
        op_kwargs={"config": CONFIG},
    )
    publish_cams_gold = spark_task(
        task_id="publish_cams_gold",
        application="/opt/spark/work-dir/jobs/gold/run.py",
        application_args=[
            "--schema",
            "gold",
            "--silver-schema",
            "silver",
            "--adapter",
            "cams",
            "--dataset-id",
            "{{ ti.xcom_pull(task_ids='validate_run')['gold_dataset_id'] }}",
            "--start-date",
            "{{ ti.xcom_pull(task_ids='validate_run')['gold_start_date'] }}",
            "--end-date",
            "{{ ti.xcom_pull(task_ids='validate_run')['gold_end_date'] }}",
        ],
        driver_memory="2g",
        pool="iceberg_writer",
    )
    publish_cams_validation_gold = spark_task(
        task_id="publish_cams_validation_gold",
        application="/opt/spark/work-dir/jobs/gold/run.py",
        application_args=[
            "--schema",
            "gold",
            "--silver-schema",
            "silver",
            "--adapter",
            "cams",
            "--dataset-id",
            "{{ ti.xcom_pull(task_ids='validate_run')['gold_dataset_id'] }}",
            "--start-date",
            "{{ ti.xcom_pull(task_ids='validate_run')['gold_start_date'] }}",
            "--end-date",
            "{{ ti.xcom_pull(task_ids='validate_run')['gold_end_date'] }}",
            "--allow-validation",
        ],
        driver_memory="2g",
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
    publish_native_gold >> choose_cams_gold
    choose_cams_gold >> [publish_cams_gold, publish_cams_validation_gold]
    [publish_cams_gold, publish_cams_validation_gold] >> complete
