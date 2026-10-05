"""Transform one CAMS EAC4 GRIB Bronze batch into ``nessie.silver``."""

from __future__ import annotations

import argparse
import math
import os
import tempfile
from datetime import datetime, timezone

from pyspark.sql import functions as F

from common import (
    TABLE_PREFIX,
    DataQualityError,
    bootstrap_schema,
    create_spark,
    deduplicate_or_fail,
    finish_run,
    load_bronze_batch,
    merge_dataframe,
    metadata_rows,
    register_dataset,
    sha256_json,
    start_run,
    utc_now,
    write_quality_issues,
)


PIPELINE = "cams-eac4-bronze-to-silver"
CAMS_CHUNK_ROWS = 100_000
GRIB_KEYS = (
    "paramId", "shortName", "name", "units", "typeOfLevel", "level", "stepType",
    "dataType", "md5GridSection", "gridType", "Ni", "Nj",
    "iDirectionIncrementInDegrees", "jDirectionIncrementInDegrees",
    "validityDate", "validityTime", "numberOfMissing",
)


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bronze-path", required=True)
    parser.add_argument(
        "--schema-sql",
        default=os.environ.get(
            "SILVER_SCHEMA_SQL", "/opt/spark/work-dir/lakehouse/silver/silver.sql"
        ),
    )
    parser.add_argument("--source-version", default="EAC4")
    return parser.parse_args()


def ec_value(eccodes, handle, key):
    return eccodes.codes_get(handle, key) if eccodes.codes_is_defined(handle, key) else None


def measurement_contract(metadata):
    unit = metadata["units"]
    short_name = metadata["shortName"]
    if unit == "kg m**-3":
        return "mass_concentration", "ug m**-3", lambda value: value * 1_000_000_000.0
    if unit == "kg m**-2":
        return "column_mass", "mg m**-2", lambda value: value * 1_000_000.0
    if unit == "K":
        return "temperature", "degC", lambda value: value - 273.15
    if unit == "Pa":
        return "pressure", "hPa", lambda value: value / 100.0
    if unit == "m s**-1":
        return "wind_component", "m s**-1", lambda value: value
    if unit in {"~", "1"} or short_name.startswith("aod"):
        return "optical_depth", "1", lambda value: value
    return "native_measurement", None, lambda value: None


def source_variable(metadata):
    return (
        f"paramId={metadata['paramId']};shortName={metadata['shortName']};"
        f"level={metadata['typeOfLevel']}:{metadata['level']};"
        f"stepType={metadata['stepType']};dataType={metadata['dataType']}"
    )


def valid_time(metadata):
    day = str(int(metadata["validityDate"]))
    clock = f"{int(metadata['validityTime']):04d}"
    return datetime.strptime(day + clock, "%Y%m%d%H%M").replace(tzinfo=timezone.utc)


def copy_bronze_file_to_local(spark, bronze_object, local_path):
    source = spark._jvm.org.apache.hadoop.fs.Path(bronze_object)
    target = spark._jvm.org.apache.hadoop.fs.Path(local_path)
    fs = source.getFileSystem(spark.sparkContext._jsc.hadoopConfiguration())
    fs.copyToLocalFile(False, source, target, True)


def variable_row(spark, metadata, created_at):
    kind, standard_unit, _ = measurement_contract(metadata)
    native_name = source_variable(metadata)
    variable_id = sha256_json("silver-variable-v1", "cams", native_name, kind)
    row = [(
        variable_id, "cams", native_name, str(metadata["name"]), "atmospheric",
        kind, str(metadata["units"]), standard_unit, int(metadata["paramId"]),
        str(metadata["shortName"]),
        f"CAMS GRIB {metadata['typeOfLevel']} level {metadata['level']}; "
        f"stepType={metadata['stepType']}; dataType={metadata['dataType']}.",
        created_at,
    )]
    return variable_id, spark.createDataFrame(row, spark.table(f"{TABLE_PREFIX}.variable").schema)


def reject_cross_file_conflicts(spark, incoming, run, keys):
    scope = incoming.agg(
        F.min("valid_time").alias("min_time"), F.max("valid_time").alias("max_time")
    ).first()
    variable_ids = [row.variable_id for row in incoming.select("variable_id").distinct().collect()]
    existing = spark.table(f"{TABLE_PREFIX}.cams_observation").filter(
        (F.col("dataset_id") == run.dataset_id)
        & (F.col("ingestion_run_id") == run.run_id)
        & F.col("valid_time").between(scope.min_time, scope.max_time)
        & F.col("variable_id").isin(variable_ids)
    )
    if existing.limit(1).count() == 0:
        return incoming, 0
    left = incoming.alias("new")
    right = existing.alias("old")
    condition = None
    for key in keys:
        part = F.col(f"new.{key}").eqNullSafe(F.col(f"old.{key}"))
        condition = part if condition is None else condition & part
    matched = left.join(right, condition, "inner")
    conflicts = matched.filter(
        (~F.col("new.value_native").eqNullSafe(F.col("old.value_native")))
        | (~F.col("new.value_standard").eqNullSafe(F.col("old.value_standard")))
    ).limit(1).count()
    if conflicts:
        write_quality_issues(spark, run, [{
            "rule_id": "cams_cross_file_conflicting_duplicate",
            "issue_type": "conflicting_duplicate", "severity": "fatal",
            "description": "The same CAMS logical key has different values in this Bronze batch.",
        }])
        raise DataQualityError("CAMS conflicting duplicate detected across GRIB files")
    duplicate_count = matched.count()
    return incoming.join(existing.select(*keys), list(keys), "left_anti"), duplicate_count


def merge_observation_chunk(spark, rows, run):
    if not rows:
        return 0, 0
    observation_frame = spark.createDataFrame(
        rows, spark.table(f"{TABLE_PREFIX}.cams_observation").schema
    )
    keys = ["dataset_id", "valid_time", "grid_id", "grid_point_id", "variable_id"]
    observation_frame, duplicates = deduplicate_or_fail(
        spark, observation_frame, key_columns=keys,
        compare_columns=["value_native", "value_standard", "qc_flag"], run=run,
        rule_id="cams_conflicting_duplicate",
    )
    observation_frame, prior_duplicates = reject_cross_file_conflicts(
        spark, observation_frame, run, keys
    )
    output_rows = observation_frame.count()
    if output_rows:
        merge_dataframe(
            spark, observation_frame, f"{TABLE_PREFIX}.cams_observation", keys
        )
    return output_rows, duplicates + prior_duplicates


def transform_file(spark, local_path, meta, run, seen_grids):
    import eccodes

    now = utc_now()
    observations = []
    local_variables = set()
    local_grids = set()
    message_count = 0
    input_rows = output_rows = duplicates = 0
    with open(local_path, "rb") as handle:
        while True:
            grib = eccodes.codes_grib_new_from_file(handle)
            if grib is None:
                break
            message_count += 1
            try:
                metadata = {key: ec_value(eccodes, grib, key) for key in GRIB_KEYS}
                required = (
                    "paramId", "shortName", "units", "typeOfLevel", "level", "stepType",
                    "dataType", "md5GridSection", "gridType", "Ni", "Nj", "validityDate",
                    "validityTime",
                )
                missing = [key for key in required if metadata[key] is None]
                if missing:
                    raise DataQualityError(f"GRIB message {message_count} missing metadata: {missing}")
                if int(metadata.get("numberOfMissing") or 0) != 0:
                    write_quality_issues(spark, run, [{
                        "source_file": meta.source_file,
                        "source_record_locator": f"grib:message={message_count}",
                        "column_name": "values", "rule_id": "cams_missing_grid_values",
                        "issue_type": "missing_measurement", "severity": "fatal",
                        "description": "cams_observation.value_native is required; missing GRIB values were not zero-filled.",
                    }])
                    raise DataQualityError("CAMS GRIB contains missing grid values")

                md5_grid = str(metadata["md5GridSection"]).lower()
                grid_id = sha256_json("cams-grid-v1", md5_grid)
                ni, nj = int(metadata["Ni"]), int(metadata["Nj"])
                values = eccodes.codes_get_array(grib, "values")
                if len(values) != ni * nj:
                    raise DataQualityError(
                        f"GRIB message {message_count}: {len(values)} values != Ni*Nj {ni * nj}"
                    )
                if grid_id not in local_grids:
                    latitudes = eccodes.codes_get_array(grib, "latitudes")
                    longitudes = eccodes.codes_get_array(grib, "longitudes")
                    if len(latitudes) != len(values) or len(longitudes) != len(values):
                        raise DataQualityError("GRIB coordinate/value arrays have inconsistent lengths")
                    if any(not -90.0 <= float(value) <= 90.0 for value in latitudes):
                        raise DataQualityError("CAMS latitude outside [-90, 90]")
                    if any(not -180.0 <= float(value) <= 180.0 for value in longitudes):
                        raise DataQualityError("CAMS longitude outside [-180, 180]")
                    signature = (
                        str(metadata["gridType"]), nj, ni,
                        tuple(round(float(value), 10) for value in latitudes),
                        tuple(round(float(value), 10) for value in longitudes),
                    )
                    old_signature = seen_grids.get(grid_id)
                    if old_signature is not None and old_signature != signature:
                        raise DataQualityError("One md5GridSection maps to conflicting grid coordinates")
                    seen_grids[grid_id] = signature
                    grid = (
                        grid_id, md5_grid, str(metadata["gridType"]), nj, ni,
                        float(metadata["jDirectionIncrementInDegrees"])
                        if metadata["jDirectionIncrementInDegrees"] is not None else None,
                        float(metadata["iDirectionIncrementInDegrees"])
                        if metadata["iDirectionIncrementInDegrees"] is not None else None,
                        min(float(value) for value in longitudes),
                        min(float(value) for value in latitudes),
                        max(float(value) for value in longitudes),
                        max(float(value) for value in latitudes),
                        4326, run.dataset_id, run.run_id, now,
                    )
                    grid_points = [
                        (grid_id, index, index // ni, index % ni, float(latitudes[index]),
                         float(longitudes[index]))
                        for index in range(len(values))
                    ]
                    grid_frame = spark.createDataFrame(
                        [grid], spark.table(f"{TABLE_PREFIX}.cams_grid").schema
                    )
                    point_frame = spark.createDataFrame(
                        grid_points, spark.table(f"{TABLE_PREFIX}.cams_grid_point").schema
                    )
                    merge_dataframe(spark, grid_frame, f"{TABLE_PREFIX}.cams_grid", ["grid_id"])
                    merge_dataframe(
                        spark, point_frame, f"{TABLE_PREFIX}.cams_grid_point",
                        ["grid_id", "grid_point_id"],
                    )
                    local_grids.add(grid_id)

                native_name = source_variable(metadata)
                kind, _, convert = measurement_contract(metadata)
                variable_id = sha256_json("silver-variable-v1", "cams", native_name, kind)
                if variable_id not in local_variables:
                    _, variable = variable_row(spark, metadata, now)
                    merge_dataframe(
                        spark, variable, f"{TABLE_PREFIX}.variable",
                        ["source_system", "source_variable", "measurement_kind"],
                    )
                    local_variables.add(variable_id)
                timestamp = valid_time(metadata)
                for index, raw_value in enumerate(values):
                    native_value = float(raw_value)
                    if not math.isfinite(native_value):
                        raise DataQualityError("CAMS contains a non-finite native value")
                    standard_value = convert(native_value)
                    observations.append((
                        run.dataset_id, timestamp, grid_id, index, variable_id, native_value,
                        standard_value, "ok", meta.source_file, meta.file_sha256, run.run_id, now,
                    ))
                input_rows += len(values)
                if len(observations) >= CAMS_CHUNK_ROWS:
                    chunk_output, chunk_duplicates = merge_observation_chunk(
                        spark, observations, run
                    )
                    output_rows += chunk_output
                    duplicates += chunk_duplicates
                    observations.clear()
            finally:
                eccodes.codes_release(grib)

    if message_count == 0:
        raise DataQualityError(f"No GRIB messages found in {meta.source_file}")
    chunk_output, chunk_duplicates = merge_observation_chunk(spark, observations, run)
    output_rows += chunk_output
    duplicates += chunk_duplicates
    return input_rows, output_rows, duplicates


def transform(spark, batch, run):
    grib_files = metadata_rows(batch, ["grib", "grib2", "grb", "grb2"])
    if not grib_files:
        raise ValueError("CAMS Bronze batch has no GRIB files")
    input_rows = output_rows = duplicates = 0
    seen_grids = {}
    with tempfile.TemporaryDirectory(prefix="cams-silver-") as temp_dir:
        for index, meta in enumerate(grib_files):
            local_path = os.path.join(temp_dir, f"input-{index}.grib")
            copy_bronze_file_to_local(spark, meta.bronze_object, local_path)
            file_input, file_output, file_duplicates = transform_file(
                spark, local_path, meta, run, seen_grids
            )
            input_rows += file_input
            output_rows += file_output
            duplicates += file_duplicates
            os.remove(local_path)
    return input_rows, output_rows, duplicates


def main():
    args = parse_args()
    spark = create_spark(PIPELINE)
    run = None
    try:
        bootstrap_schema(spark, args.schema_sql)
        batch = load_bronze_batch(spark, args.bronze_path)
        if batch.source != "cams" or batch.dataset_name != "eac4":
            raise ValueError(f"Expected cams/eac4 Bronze batch, got {batch.source}/{batch.dataset_name}")
        dataset_id = register_dataset(
            spark, batch, source_version=args.source_version,
            source_uri="https://ads.atmosphere.copernicus.eu/",
            description="CAMS EAC4 atmospheric reanalysis at native GRIB grid resolution.",
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
