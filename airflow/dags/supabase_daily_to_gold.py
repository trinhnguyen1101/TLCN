"""Daily Supabase cloud sync to local Bronze, Silver and provider Gold."""

from __future__ import annotations

import os
from datetime import date, timedelta

import pendulum
from airflow import DAG
from airflow.operators.empty import EmptyOperator
from airflow.operators.python import PythonOperator

from lakehouse_airflow import (
    audit_supabase_collection_runs,
    check_services,
    check_supabase_s3_config,
    rclone_supabase_task,
    spark_task,
)
from lakehouse_config import daily_window


def _start_date():
    value = os.getenv("AIRFLOW_SUPABASE_START_DATE", "2026-10-27")
    parsed = date.fromisoformat(value)
    return pendulum.datetime(parsed.year, parsed.month, parsed.day, 0, 30, tz="Asia/Ho_Chi_Minh")


def _resolve_window(**context) -> dict:
    return daily_window(context["data_interval_end"])


WINDOW = "resolve_daily_window"


def xcom(key: str) -> str:
    return "{{ ti.xcom_pull(task_ids='" + WINDOW + "')['" + key + "'] }}"


with DAG(
    dag_id="supabase_daily_to_gold",
    description="Daily Supabase WAQI/API Ninjas sync to provider Gold",
    schedule="30 0 * * *",
    start_date=_start_date(),
    catchup=True,
    max_active_runs=1,
    render_template_as_native_obj=True,
    default_args={"owner": "lakehouse", "retries": 0},
    tags=["lakehouse", "supabase", "daily"],
) as dag:
    resolve_window = PythonOperator(
        task_id=WINDOW,
        python_callable=_resolve_window,
    )
    services = PythonOperator(
        task_id="check_lakehouse_services",
        python_callable=check_services,
        retries=2,
        retry_delay=timedelta(minutes=2),
    )
    s3_config = PythonOperator(
        task_id="check_supabase_s3_config",
        python_callable=check_supabase_s3_config,
    )
    audit = PythonOperator(
        task_id="audit_supabase_collection_runs",
        python_callable=audit_supabase_collection_runs,
        op_kwargs={"window": "{{ ti.xcom_pull(task_ids='resolve_daily_window') }}"},
        retries=6,
        retry_delay=timedelta(minutes=15),
        execution_timeout=timedelta(hours=2),
    )

    waqi_rclone = rclone_supabase_task(
        task_id="waqi_rclone_daily_folder",
        source="waqi",
        hour_prefixes=xcom("rclone_hour_prefixes"),
        batch_id=xcom("waqi_batch_id"),
    )
    ninja_rclone = rclone_supabase_task(
        task_id="ninjas_rclone_daily_folder",
        source="api_ninjas",
        hour_prefixes=xcom("rclone_hour_prefixes"),
        batch_id=xcom("api_ninjas_batch_id"),
    )

    waqi_bronze = spark_task(
        task_id="waqi_supabase_to_bronze",
        application="/opt/spark/work-dir/jobs/bronze/supabase_to_bronze.py",
        application_args=[
            "--source",
            "waqi",
            "--window-start",
            xcom("window_start_utc"),
            "--window-end",
            xcom("window_end_utc"),
            "--batch-id",
            xcom("waqi_batch_id"),
            "--ingestion-date",
            xcom("ingestion_date"),
            "--staging-root",
            "/opt/spark/work-dir/supabase-sync/waqi/" + xcom("waqi_batch_id"),
        ],
        driver_memory="1g",
        pool="bronze_sync",
        retries=2,
    )
    ninja_bronze = spark_task(
        task_id="ninjas_supabase_to_bronze",
        application="/opt/spark/work-dir/jobs/bronze/supabase_to_bronze.py",
        application_args=[
            "--source",
            "api_ninjas",
            "--window-start",
            xcom("window_start_utc"),
            "--window-end",
            xcom("window_end_utc"),
            "--batch-id",
            xcom("api_ninjas_batch_id"),
            "--ingestion-date",
            xcom("ingestion_date"),
            "--staging-root",
            "/opt/spark/work-dir/supabase-sync/api_ninjas/"
            + xcom("api_ninjas_batch_id"),
        ],
        driver_memory="1g",
        pool="bronze_sync",
        retries=2,
    )

    waqi_silver = spark_task(
        task_id="waqi_bronze_to_silver",
        application="/opt/spark/work-dir/jobs/silver/supabase_bronze_to_silver.py",
        application_args=[
            "--source",
            "waqi",
            "--bronze-path",
            xcom("waqi_bronze_path"),
        ],
        driver_memory="1g",
        py_files="/opt/spark/work-dir/jobs/silver/common.py",
        pool="iceberg_writer",
    )
    ninja_silver = spark_task(
        task_id="ninjas_bronze_to_silver",
        application="/opt/spark/work-dir/jobs/silver/supabase_bronze_to_silver.py",
        application_args=[
            "--source",
            "api_ninjas",
            "--bronze-path",
            xcom("api_ninjas_bronze_path"),
        ],
        driver_memory="1g",
        py_files="/opt/spark/work-dir/jobs/silver/common.py",
        pool="iceberg_writer",
    )

    waqi_gold = spark_task(
        task_id="waqi_silver_to_gold",
        application="/opt/spark/work-dir/jobs/gold/supabase_live.py",
        application_args=[
            "--source",
            "waqi",
            "--schema",
            "gold",
            "--silver-schema",
            "silver",
            "--start-date",
            xcom("business_date"),
            "--end-date",
            xcom("end_date"),
            "--channel",
            "provider_air_quality",
        ],
        driver_memory="2g",
        pool="iceberg_writer",
    )
    ninja_gold = spark_task(
        task_id="ninjas_silver_to_gold",
        application="/opt/spark/work-dir/jobs/gold/supabase_live.py",
        application_args=[
            "--source",
            "api_ninjas",
            "--schema",
            "gold",
            "--silver-schema",
            "silver",
            "--start-date",
            xcom("business_date"),
            "--end-date",
            xcom("end_date"),
            "--channel",
            "provider_air_quality",
        ],
        driver_memory="2g",
        pool="iceberg_writer",
    )
    complete = EmptyOperator(task_id="supabase_pipeline_complete")

    resolve_window >> services >> s3_config >> audit >> [waqi_rclone, ninja_rclone]
    waqi_rclone >> waqi_bronze
    ninja_rclone >> ninja_bronze
    waqi_bronze >> waqi_silver
    [waqi_silver, ninja_bronze] >> ninja_silver
    ninja_silver >> waqi_gold >> ninja_gold >> complete
