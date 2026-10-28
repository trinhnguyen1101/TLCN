"""Manual Landing batch orchestration from immutable files to Silver/Gold."""

from __future__ import annotations

from datetime import timedelta

import pendulum
from airflow import DAG
from airflow.operators.empty import EmptyOperator
from airflow.operators.python import BranchPythonOperator, PythonOperator
from airflow.utils.trigger_rule import TriggerRule

from lakehouse_airflow import check_services, spark_task
from lakehouse_config import validate_landing_conf


DOC = """
Trigger this DAG with JSON such as:

```json
{
  "dataset": "waqi/historical",
  "batch_id": "waqi-history-20261028",
  "ingestion_date": "2026-10-28",
  "publish_gold": false
}
```

`publish_gold` defaults to false. Administrative datasets have no Gold adapter.
CAMS Gold additionally requires `gold.dataset_id`, `gold.start_date`,
`gold.end_date`, and optionally `gold.allow_validation`.
"""


def _validate(**context) -> dict:
    dag_run = context.get("dag_run")
    return validate_landing_conf(dag_run.conf if dag_run else None)


def _gold_branch(config: dict) -> str:
    return {
        "none": "no_gold",
        "native": "publish_native_gold",
        "cams": "publish_cams_gold",
        "cams_validation": "publish_cams_validation_gold",
    }[config["gold_kind"]]


CONFIG = "{{ ti.xcom_pull(task_ids='validate_run') }}"
DATASET = "{{ ti.xcom_pull(task_ids='validate_run')['dataset'] }}"
BATCH_ID = "{{ ti.xcom_pull(task_ids='validate_run')['batch_id'] }}"
INGESTION_DATE = "{{ ti.xcom_pull(task_ids='validate_run')['ingestion_date'] }}"
BRONZE_PATH = "{{ ti.xcom_pull(task_ids='validate_run')['bronze_path'] }}"
SILVER_JOB = "{{ ti.xcom_pull(task_ids='validate_run')['silver_job'] }}"
PY_FILES = "{{ ti.xcom_pull(task_ids='validate_run')['py_files'] }}"


with DAG(
    dag_id="landing_batch_to_gold",
    description="Manual Landing batch to Bronze, Silver and optional Gold",
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

    landing_to_bronze = spark_task(
        task_id="landing_to_bronze",
        application="/opt/spark/work-dir/jobs/bronze/landing_to_bronze.py",
        application_args=[
            "--dataset",
            DATASET,
            "--batch-id",
            BATCH_ID,
            "--ingestion-date",
            INGESTION_DATE,
        ],
        driver_memory="512m",
        pool="bronze_sync",
        retries=2,
    )
    bronze_to_silver = spark_task(
        task_id="bronze_to_silver",
        application=f"/opt/spark/work-dir/jobs/silver/{SILVER_JOB}",
        application_args=["--bronze-path", BRONZE_PATH],
        driver_memory="1g",
        py_files=PY_FILES,
        pool="iceberg_writer",
    )

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

    validate_run >> services >> landing_to_bronze >> bronze_to_silver >> choose_gold
    choose_gold >> [no_gold, publish_native_gold, publish_cams_gold, publish_cams_validation_gold]
    [no_gold, publish_native_gold, publish_cams_gold, publish_cams_validation_gold] >> complete
