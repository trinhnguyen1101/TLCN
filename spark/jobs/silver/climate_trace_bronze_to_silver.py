"""Transform one Climate TRACE Bronze batch into ``nessie.silver``."""

from __future__ import annotations

import argparse
import os

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


PIPELINE = "climate-trace-bronze-to-silver"


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


def read_sources(spark, batch):
    aggregates = []
    point_sources = []
    input_rows = 0
    for meta in metadata_rows(batch, ["csv"]):
        frame = spark.read.option("header", True).option("inferSchema", False).csv(meta.bronze_object)
        frame = trim_strings(normalize_column_names(frame))
        frame = (
            frame.withColumn("_source_file", F.lit(meta.source_file))
            .withColumn("_source_file_sha256", F.lit(meta.file_sha256))
        )
        count = frame.count()
        input_rows += count
        if "source_id" in frame.columns:
            assert_required_columns(
                frame,
                ["source_id", "country", "year", "gas", "latitude", "longitude", "sector",
                 "subsector", "source_type", "annual_emissions_quantity"],
                meta.source_file,
            )
            point_sources.append(frame)
        else:
            assert_required_columns(
                frame,
                ["country", "aggregation", "year", "gas", "sector", "subsector",
                 "emissionsQuantity"],
                meta.source_file,
            )
            if "data_month" not in frame.columns:
                frame = frame.withColumn("data_month", F.lit(None).cast("string"))
            aggregates.append(frame)
    if not aggregates or not point_sources:
        raise ValueError("Climate TRACE batch must contain aggregate and point-source CSV files")
    aggregate = aggregates[0]
    for frame in aggregates[1:]:
        aggregate = aggregate.unionByName(frame, allowMissingColumns=True)
    point_source = point_sources[0]
    for frame in point_sources[1:]:
        point_source = point_source.unionByName(frame, allowMissingColumns=True)
    return aggregate, point_source, input_rows


def fail_invalid(spark, run, frame, rule_id, description, columns):
    rows = frame.select(*columns).limit(100).collect()
    if not rows:
        return
    write_quality_issues(spark, run, ({
        "source_file": row.asDict().get("_source_file") or row.asDict().get("source_file"),
        "source_record_locator": row.asDict().get("_locator") or row.asDict().get("source_record_locator"),
        "rule_id": rule_id,
        "issue_type": "invalid_value",
        "severity": "fatal",
        "description": description,
        "raw_record_json": str(row.asDict()),
    } for row in rows))
    raise DataQualityError(description)


def variable_frame(spark, gases):
    now = utc_now()
    rows = []
    for gas in gases:
        rows.append((
            sha256_json("silver-variable-v1", "climate_trace", gas, "emission_quantity"),
            "climate_trace", gas, f"{gas.upper()} emissions", "emission",
            "emission_quantity", None, None, None, gas,
            "Climate TRACE native emissions quantity; source CSV has no explicit unit metadata.", now,
        ))
    return spark.createDataFrame(rows, spark.table(f"{TABLE_PREFIX}.variable").schema)


def transform(spark, batch, run):
    aggregate_raw, source_raw, input_rows = read_sources(spark, batch)
    gases = sorted({
        row.gas for row in aggregate_raw.select(F.lower("gas").alias("gas")).union(
            source_raw.select(F.lower("gas").alias("gas"))
        ).where(F.col("gas").isNotNull()).distinct().collect()
    })
    variables = variable_frame(spark, gases)
    merge_dataframe(
        spark, variables, f"{TABLE_PREFIX}.variable",
        ["source_system", "source_variable", "measurement_kind"],
    )
    variable_ids = {row.source_variable: row.variable_id for row in variables.collect()}
    variable_map = F.create_map(
        *sum(([F.lit(key), F.lit(value)] for key, value in variable_ids.items()), [])
    )
    now = utc_now()

    aggregate_typed = (
        aggregate_raw.withColumn("gas", F.lower("gas"))
        .withColumn("aggregation", F.lower("aggregation"))
        .withColumn("_year", F.col("year").cast("int"))
        .withColumn("_quantity", F.col("emissionsQuantity").cast("double"))
        .withColumn(
            "_period_type", F.when(F.col("data_month").isNotNull(), "month").otherwise("year")
        )
        .withColumn(
            "_period_start",
            F.when(
                F.col("data_month").isNotNull(),
                F.to_date(F.concat(F.col("data_month"), F.lit("-01")), "yyyy-MM-dd"),
            ).otherwise(F.make_date(F.col("_year"), F.lit(1), F.lit(1))),
        )
        .withColumn(
            "_period_end",
            F.when(F.col("data_month").isNotNull(), F.last_day(F.col("_period_start")))
            .otherwise(F.make_date(F.col("_year"), F.lit(12), F.lit(31))),
        )
        .withColumn(
            "_locator",
            F.concat_ws(
                ";", F.concat(F.lit("csv:country="), F.col("country")),
                F.concat(F.lit("period="), F.coalesce(F.col("data_month"), F.col("year"))),
                F.concat(F.lit("gas="), F.col("gas")),
                F.concat(F.lit("level="), F.col("aggregation")),
                F.concat(F.lit("sector="), F.coalesce(F.col("sector"), F.lit("<TOTAL>"))),
                F.concat(F.lit("subsector="), F.coalesce(F.col("subsector"), F.lit("<NONE>"))),
            ),
        )
    )
    invalid_aggregate = aggregate_typed.filter(
        F.col("country").isNull() | F.col("gas").isNull() | F.col("_year").isNull()
        | F.col("_quantity").isNull() | F.isnan("_quantity")
        | F.col("_period_start").isNull() | F.col("_period_end").isNull()
        | (~F.col("aggregation").isin("totals", "sectors", "subsectors"))
        | ((F.col("aggregation") == "totals") & (F.col("sector").isNotNull() | F.col("subsector").isNotNull()))
        | ((F.col("aggregation") == "sectors") & (F.col("sector").isNull() | F.col("subsector").isNotNull()))
        | ((F.col("aggregation") == "subsectors") & (F.col("sector").isNull() | F.col("subsector").isNull()))
        | (F.col("_period_end") < F.col("_period_start"))
    )
    fail_invalid(
        spark, run, invalid_aggregate, "climate_trace_aggregate_contract",
        "Climate TRACE aggregate hierarchy, period, or numeric value is invalid.",
        ["_source_file", "_locator", "country", "year", "data_month", "gas", "aggregation",
         "sector", "subsector", "emissionsQuantity"],
    )

    aggregates = aggregate_typed.select(
        F.lit(None).cast("string").alias("aggregate_id"),
        F.lit(run.dataset_id).alias("dataset_id"),
        F.upper("country").alias("country_code"),
        F.col("_period_type").alias("period_type"),
        F.col("_period_start").alias("period_start"),
        F.col("_period_end").alias("period_end"),
        F.when(F.col("_period_end") > F.lit(batch.ingestion_date), F.lit("partial"))
        .otherwise(F.lit("actual")).alias("period_status"),
        F.col("aggregation").alias("aggregation_level"),
        F.col("sector"), F.col("subsector"),
        variable_map.getItem(F.col("gas")).alias("variable_id"),
        F.col("_quantity").alias("emission_quantity_native"),
        F.lit(None).cast("double").alias("emission_quantity_standard"),
        F.col("_source_file").alias("source_file"),
        F.col("_source_file_sha256").alias("source_file_sha256"),
        F.col("_locator").alias("source_record_locator"),
        F.lit(run.run_id).alias("ingestion_run_id"),
        F.lit(now).cast("timestamp").alias("loaded_at"),
    )
    aggregate_id_udf = F.udf(
        lambda dataset_id, country, period_type, period_start, level, sector, subsector, variable_id:
            sha256_json(
                "emission-aggregate-v1", dataset_id, country, period_type, period_start,
                level, sector if sector is not None else "<TOTAL>",
                subsector if subsector is not None else "<NONE>", variable_id,
            ),
        "string",
    )
    aggregates = aggregates.withColumn(
        "aggregate_id",
        aggregate_id_udf(
            "dataset_id", "country_code", "period_type", "period_start", "aggregation_level",
            "sector", "subsector", "variable_id",
        ),
    )
    aggregates, aggregate_duplicates = deduplicate_or_fail(
        spark, aggregates, key_columns=["aggregate_id"],
        compare_columns=[
            "period_end", "period_status", "emission_quantity_native",
            "emission_quantity_standard",
        ], run=run, rule_id="climate_trace_aggregate_conflicting_duplicate",
    )

    sources_typed = (
        source_raw.withColumn("gas", F.lower("gas"))
        .withColumn("_year", F.col("year").cast("int"))
        .withColumn("_latitude", F.col("latitude").cast("double"))
        .withColumn("_longitude", F.col("longitude").cast("double"))
        .withColumn("_quantity", F.col("annual_emissions_quantity").cast("double"))
        .withColumn("_source_id", F.concat(F.lit("climate_trace:"), F.col("source_id")))
        .withColumn(
            "_locator",
            F.concat_ws(
                ";", F.concat(F.lit("csv:source_id="), F.col("source_id")),
                F.concat(F.lit("year="), F.col("year")),
                F.concat(F.lit("gas="), F.col("gas")),
            ),
        )
    )
    invalid_sources = sources_typed.filter(
        F.col("source_id").isNull() | F.col("country").isNull() | F.col("gas").isNull()
        | F.col("sector").isNull() | F.col("subsector").isNull() | F.col("source_type").isNull()
        | F.col("_year").isNull() | F.col("_quantity").isNull() | F.isnan("_quantity")
        | F.col("_latitude").isNull() | F.col("_longitude").isNull()
        | (~F.col("_latitude").between(-90.0, 90.0))
        | (~F.col("_longitude").between(-180.0, 180.0))
    )
    fail_invalid(
        spark, run, invalid_sources, "climate_trace_source_contract",
        "Climate TRACE source identity, coordinates, hierarchy, year, or quantity is invalid.",
        ["_source_file", "_locator", "source_id", "country", "year", "gas", "latitude",
         "longitude", "sector", "subsector", "annual_emissions_quantity"],
    )

    source_observations = sources_typed.select(
        F.lit(run.dataset_id).alias("dataset_id"),
        F.col("_source_id").alias("source_id"),
        F.col("_year").alias("year_label"),
        F.make_date(F.col("_year"), F.lit(1), F.lit(1)).alias("period_start"),
        F.make_date(F.col("_year"), F.lit(12), F.lit(31)).alias("period_end"),
        F.when(
            F.make_date(F.col("_year"), F.lit(12), F.lit(31)) > F.lit(batch.ingestion_date),
            F.lit("partial"),
        ).otherwise(F.lit("actual")).alias("period_status"),
        variable_map.getItem(F.col("gas")).alias("variable_id"),
        F.col("_quantity").alias("emission_quantity_native"),
        F.lit(None).cast("double").alias("emission_quantity_standard"),
        F.col("_source_file").alias("source_file"),
        F.col("_source_file_sha256").alias("source_file_sha256"),
        F.col("_locator").alias("source_record_locator"),
        F.lit(run.run_id).alias("ingestion_run_id"),
        F.lit(now).cast("timestamp").alias("loaded_at"),
    )
    observation_keys = ["dataset_id", "source_id", "year_label", "variable_id"]
    source_observations, source_duplicates = deduplicate_or_fail(
        spark, source_observations, key_columns=observation_keys,
        compare_columns=[
            "period_start", "period_end", "period_status", "emission_quantity_native",
            "emission_quantity_standard",
        ], run=run, rule_id="climate_trace_source_conflicting_duplicate",
    )

    source_entities = sources_typed.groupBy("_source_id").agg(
        F.countDistinct(
            F.to_json(F.struct(
                "source_id", "country", "_latitude", "_longitude", "sector", "subsector",
                "source_type", "asset_type",
            ))
        ).alias("_variants"),
        F.first("source_id").alias("source_native_id"),
        F.first(F.upper("country")).alias("country_code"),
        F.first("_latitude").alias("latitude"),
        F.first("_longitude").alias("longitude"),
        F.first("sector").alias("sector"),
        F.first("subsector").alias("subsector"),
        F.first("source_type").alias("source_type"),
        F.first("asset_type").alias("asset_type"),
        F.min("_year").alias("first_seen_year"),
        F.max("_year").alias("last_seen_year"),
        F.first("_source_file").alias("source_file"),
        F.first("_source_file_sha256").alias("source_file_sha256"),
        F.first("_locator").alias("source_record_locator"),
    )
    conflicting_entities = source_entities.filter(F.col("_variants") > 1)
    fail_invalid(
        spark, run, conflicting_entities, "climate_trace_source_metadata_conflict",
        "One Climate TRACE source_id has conflicting source metadata.",
        ["_source_id", "_variants", "source_file", "source_record_locator"],
    )
    emission_sources = source_entities.select(
        F.col("_source_id").alias("source_id"),
        F.lit("climate_trace").alias("source_system"),
        "source_native_id", "country_code", "latitude", "longitude", "sector", "subsector",
        "source_type", "asset_type",
        F.lit(None).cast("string").alias("admin_unit_version_id"),
        F.lit(None).cast("string").alias("admin_code"),
        F.lit(run.dataset_id).alias("dataset_id"),
        "first_seen_year", "last_seen_year", "source_file", "source_file_sha256",
        "source_record_locator", F.lit(run.run_id).alias("last_seen_run_id"),
        F.lit(now).cast("timestamp").alias("updated_at"),
    )

    merge_dataframe(spark, aggregates, f"{TABLE_PREFIX}.emission_aggregate", ["aggregate_id"])
    merge_dataframe(spark, emission_sources, f"{TABLE_PREFIX}.emission_source", ["source_id"])
    merge_dataframe(
        spark, source_observations, f"{TABLE_PREFIX}.emission_source_observation", observation_keys,
    )
    return (
        input_rows,
        aggregates.count() + source_observations.count(),
        aggregate_duplicates + source_duplicates,
    )


def main():
    args = parse_args()
    spark = create_spark(PIPELINE)
    run = None
    try:
        bootstrap_schema(spark, args.schema_sql)
        batch = load_bronze_batch(spark, args.bronze_path)
        if batch.source != "climate_trace" or batch.dataset_name != "climate_trace_vietnam":
            raise ValueError(
                f"Expected climate_trace/climate_trace_vietnam, got {batch.source}/{batch.dataset_name}"
            )
        dataset_id = register_dataset(
            spark, batch, source_version=args.source_version,
            source_uri="https://climatetrace.org/",
            description="Climate TRACE Vietnam aggregate and point-source emissions.",
        )
        run = start_run(spark, batch, dataset_id, PIPELINE)
        if run.skipped:
            return
        input_rows, output_rows, duplicates = transform(spark, batch, run)
        finish_run(
            spark, run, status="succeeded", input_rows=input_rows, output_rows=output_rows,
            duplicate_rows=duplicates,
        )
    except Exception as exc:
        if run is not None and not run.skipped:
            finish_run(spark, run, status="failed", error_message=str(exc))
        raise
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
