"""Transform one WAQI historical Bronze batch into ``nessie.silver``."""

from __future__ import annotations

import argparse
import os
import re
import unicodedata
from pathlib import PurePosixPath

from pyspark.sql import functions as F

from common import (
    TABLE_PREFIX,
    DataQualityError,
    assert_required_columns,
    bootstrap_schema,
    create_spark,
    deduplicate_or_fail,
    finish_run,
    load_bronze_batch,
    merge_dataframe,
    metadata_rows,
    normalize_column_names,
    register_dataset,
    sha256_json,
    start_run,
    trim_strings,
    utc_now,
    write_quality_issues,
)


PIPELINE = "waqi-bronze-to-silver"
CANONICAL_COLUMNS = ("pm25", "pm10", "o3", "no2", "so2", "co", "aqi")
DISPLAY_NAMES = {
    "pm25": "PM2.5 AQI",
    "pm10": "PM10 AQI",
    "o3": "Ozone AQI",
    "no2": "Nitrogen dioxide AQI",
    "so2": "Sulfur dioxide AQI",
    "co": "Carbon monoxide AQI",
    "aqi": "Overall AQI",
}


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bronze-path", required=True)
    parser.add_argument(
        "--schema-sql",
        default=os.environ.get(
            "SILVER_SCHEMA_SQL", "/opt/spark/work-dir/lakehouse/silver/silver.sql"
        ),
    )
    parser.add_argument("--source-version")
    return parser.parse_args()


def normalized_filename(source_file: str) -> str:
    value = unicodedata.normalize("NFC", source_file.strip().replace("\\", "/"))
    return "/".join(" ".join(part.split()).casefold() for part in PurePosixPath(value).parts)


def station_labels(source_file: str) -> tuple[str, str]:
    filename = PurePosixPath(source_file).name
    stem = re.sub(r"(?i),?\s*vietnam-air-quality\.csv$", "", filename).strip(" ,-_")
    if "_" in stem:
        location, station = stem.split("_", 1)
        return station.strip(), location.replace("-", " ").strip()
    label = stem.replace("-", " ").replace(",", " ")
    label = " ".join(label.split())
    return label, label


def variable_frame(spark):
    now = utc_now()
    rows = []
    for column in CANONICAL_COLUMNS:
        rows.append((
            sha256_json("silver-variable-v1", "waqi", column, "daily_aqi"),
            "waqi", column, DISPLAY_NAMES[column], "air_quality",
            "daily_aqi", "AQI", "AQI", None, column,
            "Daily air-quality index supplied by the WAQI historical CSV.", now,
        ))
    return spark.createDataFrame(rows, spark.table(f"{TABLE_PREFIX}.variable").schema)


def transform(spark, batch, run):
    csv_files = metadata_rows(batch, ["csv"])
    if not csv_files:
        raise ValueError("WAQI Bronze batch has no CSV files")

    variables = variable_frame(spark).cache()
    merge_dataframe(
        spark, variables, f"{TABLE_PREFIX}.variable",
        ["source_system", "source_variable", "measurement_kind"],
    )
    variable_ids = {
        row.source_variable: row.variable_id
        for row in variables.select("source_variable", "variable_id").collect()
    }

    source_frames = []
    station_specs = []
    input_rows = 0
    for meta in csv_files:
        source = spark.read.option("header", True).option("inferSchema", False).csv(meta.bronze_object)
        source = trim_strings(normalize_column_names(source))
        assert_required_columns(source, ["date"], meta.source_file)
        present = [name for name in CANONICAL_COLUMNS if name in source.columns]
        if not present:
            raise ValueError(f"{meta.source_file} has no supported AQI columns")
        source_station_key = normalized_filename(meta.source_file)
        station_name, location_label = station_labels(meta.source_file)
        station_id = sha256_json(
            "waqi-station-v1", run.dataset_id, source_station_key
        )
        station_specs.append({
            "source_file": meta.source_file,
            "source_file_sha256": meta.file_sha256,
            "source_station_key": source_station_key,
            "station_id": station_id,
            "station_name": station_name,
            "location_label": location_label,
            "present": set(present),
        })
        source = (
            source.withColumn("_source_file", F.lit(meta.source_file))
            .withColumn("_source_file_sha256", F.lit(meta.file_sha256))
            .withColumn("_source_station_key", F.lit(source_station_key))
            .withColumn("_station_id", F.lit(station_id))
            .withColumn("_raw_date", F.col("date"))
            .withColumn("_observation_date", F.to_date(F.col("date"), "yyyy/M/d"))
        )
        count = source.count()
        input_rows += count
        source_frames.append((source, present))

    invalid_date_frames = [
        frame.filter(F.col("_raw_date").isNull() | F.col("_observation_date").isNull()).select(
            "_source_file", "_raw_date"
        )
        for frame, _ in source_frames
    ]
    invalid_dates = invalid_date_frames[0]
    for frame in invalid_date_frames[1:]:
        invalid_dates = invalid_dates.unionByName(frame)
    invalid_date_rows = invalid_dates.limit(100).collect()
    if invalid_date_rows:
        write_quality_issues(spark, run, ({
            "source_file": row._source_file,
            "source_record_locator": None,
            "column_name": "date",
            "rule_id": "waqi_date_parse",
            "issue_type": "invalid_date",
            "severity": "fatal",
            "description": "WAQI date is not a valid yyyy/M/d value.",
            "original_value": row._raw_date,
        } for row in invalid_date_rows))
        raise DataQualityError("WAQI contains invalid yyyy/M/d dates")

    long_frames = []
    for frame, present in source_frames:
        pairs = []
        for name in present:
            pairs.extend([f"'{name}'", f"`{name}`"])
        stacked = frame.select(
            "_station_id", "_observation_date", "_source_file", "_source_file_sha256",
            F.expr(f"stack({len(present)}, {', '.join(pairs)}) as (source_variable, raw_value)"),
        )
        long_frames.append(stacked)
    long_data = long_frames[0]
    for frame in long_frames[1:]:
        long_data = long_data.unionByName(frame)

    numeric = long_data.withColumn("_numeric_value", F.col("raw_value").cast("double"))
    invalid_values = numeric.filter(
        F.col("raw_value").isNotNull()
        & (F.col("_numeric_value").isNull() | (F.col("_numeric_value") != F.floor(F.col("_numeric_value"))))
    )
    invalid_value_rows = invalid_values.limit(100).collect()
    if invalid_value_rows:
        write_quality_issues(spark, run, ({
            "source_file": row._source_file,
            "source_record_locator": f"csv:date={row._observation_date}",
            "column_name": row.source_variable,
            "rule_id": "waqi_integral_aqi",
            "issue_type": "invalid_measurement",
            "severity": "fatal",
            "description": "AQI value must be an integer and is never silently rounded.",
            "original_value": row.raw_value,
        } for row in invalid_value_rows))
        raise DataQualityError("WAQI contains non-integral or non-numeric AQI values")

    now = utc_now()
    observations = numeric.select(
        F.lit(run.dataset_id).alias("dataset_id"),
        F.col("_station_id").alias("station_id"),
        F.col("_observation_date").alias("observation_date"),
        F.create_map(*sum(([F.lit(k), F.lit(v)] for k, v in variable_ids.items()), [])).getItem(
            F.col("source_variable")
        ).alias("variable_id"),
        F.col("_numeric_value").cast("int").alias("aqi_value"),
        F.when(F.col("raw_value").isNull(), F.lit("source_blank")).alias("missing_reason"),
        F.when(F.col("raw_value").isNull(), F.lit("missing")).otherwise(F.lit("ok")).alias("qc_flag"),
        F.col("_source_file").alias("source_file"),
        F.col("_source_file_sha256").alias("source_file_sha256"),
        F.concat(F.lit("csv:date="), F.date_format(F.col("_observation_date"), "yyyy-MM-dd"))
        .alias("source_record_locator"),
        F.lit(run.run_id).alias("ingestion_run_id"),
        F.lit(now).cast("timestamp").alias("loaded_at"),
    )
    observation_keys = ["dataset_id", "station_id", "observation_date", "variable_id"]
    observations, duplicate_rows = deduplicate_or_fail(
        spark, observations, key_columns=observation_keys,
        compare_columns=["aqi_value", "missing_reason", "qc_flag"], run=run,
        rule_id="waqi_conflicting_duplicate",
    )

    date_ranges = {
        row.station_id: (row.first_seen, row.last_seen)
        for row in observations.groupBy("station_id").agg(
            F.min("observation_date").alias("first_seen"),
            F.max("observation_date").alias("last_seen"),
        ).collect()
    }
    station_rows = []
    source_rows = []
    availability_rows = []
    for spec in station_specs:
        first_seen, last_seen = date_ranges[spec["station_id"]]
        station_rows.append((
            spec["station_id"], spec["station_name"], spec["location_label"], None, None,
            None, None, None, "derived", None, None, first_seen, last_seen,
            run.run_id, run.run_id, now, now,
        ))
        source_rows.append((
            run.dataset_id, spec["source_station_key"], spec["station_id"], None,
            spec["station_name"], spec["location_label"], spec["source_file"],
            spec["source_file_sha256"], run.run_id, first_seen, last_seen, now,
        ))
        for column in CANONICAL_COLUMNS:
            dates = (
                observations.filter(
                    (F.col("station_id") == spec["station_id"])
                    & (F.col("variable_id") == variable_ids[column])
                    & F.col("aqi_value").isNotNull()
                ).agg(F.min("observation_date"), F.max("observation_date")).first()
                if column in spec["present"] else (None, None)
            )
            availability_rows.append((
                run.dataset_id, spec["station_id"], variable_ids[column], column,
                column in spec["present"], dates[0], dates[1], run.run_id, now,
            ))

    stations = spark.createDataFrame(station_rows, spark.table(f"{TABLE_PREFIX}.waqi_station").schema)
    station_sources = spark.createDataFrame(
        source_rows, spark.table(f"{TABLE_PREFIX}.waqi_station_source").schema
    )
    availability = spark.createDataFrame(
        availability_rows, spark.table(f"{TABLE_PREFIX}.waqi_station_variable").schema
    )
    merge_dataframe(spark, stations, f"{TABLE_PREFIX}.waqi_station", ["station_id"])
    merge_dataframe(
        spark, station_sources, f"{TABLE_PREFIX}.waqi_station_source",
        ["dataset_id", "source_station_key"],
    )
    merge_dataframe(
        spark, availability, f"{TABLE_PREFIX}.waqi_station_variable",
        ["dataset_id", "station_id", "variable_id"],
    )
    merge_dataframe(
        spark, observations, f"{TABLE_PREFIX}.waqi_daily_observation", observation_keys,
    )
    return input_rows, observations.count(), duplicate_rows


def main():
    args = parse_args()
    spark = create_spark(PIPELINE)
    run = None
    try:
        bootstrap_schema(spark, args.schema_sql)
        batch = load_bronze_batch(spark, args.bronze_path)
        if batch.source != "waqi" or batch.dataset_name != "historical":
            raise ValueError(f"Expected waqi/historical Bronze batch, got {batch.source}/{batch.dataset_name}")
        dataset_id = register_dataset(
            spark, batch, source_version=args.source_version,
            source_uri="https://aqicn.org/data-platform/register/",
            description="WAQI historical daily AQI CSV files.",
        )
        run = start_run(spark, batch, dataset_id, PIPELINE)
        if run.skipped:
            return
        input_rows, output_rows, duplicate_rows = transform(spark, batch, run)
        finish_run(
            spark, run, status="succeeded", input_rows=input_rows, output_rows=output_rows,
            duplicate_rows=duplicate_rows,
        )
    except Exception as exc:
        if run is not None and not run.skipped:
            finish_run(spark, run, status="failed", error_message=str(exc))
        raise
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
