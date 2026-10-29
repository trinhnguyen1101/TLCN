"""Load aligned CAMS EAC4 GRIB fields into a compact Iceberg grid cube."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import tempfile
from contextlib import ExitStack
from datetime import datetime, timezone

from common import (
    SILVER_TZ,
    TABLE_PREFIX,
    DataQualityError,
    bootstrap_schema,
    create_spark,
    finish_run,
    load_bronze_batch,
    merge_dataframe,
    metadata_rows,
    report_file_progress,
    register_dataset,
    sha256_json,
    start_run,
    utc_now,
    write_quality_issues,
)
from cams_physics import (
    CONTRACTS, GASES, aligned_coefficient_metadata, coefficient_provenance, normalize_fields,
)


PIPELINE = "cams-eac4-bronze-to-silver"
PIPELINE_VERSION = "4.0.0"
CUBE_TABLE = f"{TABLE_PREFIX}.cams_cube_standard"
SOURCE_TABLE = f"{TABLE_PREFIX}.cams_cube_standard_source"
CAMS_CHUNK_TIMESTEPS = 512
CAMS_INPUT_PARTITIONS = 16

# Match the native GRIB parameter, not the filename, to the fixed cube column.
# One aligned time/grid record has exactly one message from every field.
FIELD_SPECS = {
    "aod550": (210207, "aod550"),
    "co": (210123, "co"),
    "co_column": (210127, "tcco"),
    "d2m": (168, "2d"),
    "mslp": (151, "msl"),
    "no2": (210121, "no2"),
    "no2_column": (210125, "tcno2"),
    "o3": (210203, "go3"),
    "o3_column": (210206, "gtco3"),
    "pm10": (210074, "pm10"),
    "pm1": (210072, "pm1"),
    "pm2p5": (210073, "pm2p5"),
    "q_model": (133, "q"),
    "so2": (210122, "so2"),
    "so2_column": (210126, "tcso2"),
    "sp": (134, "sp"),
    "t2m": (167, "2t"),
    "t_model": (130, "t"),
    "u10": (165, "10u"),
    "v10": (166, "10v"),
}
MODEL_LEVEL_FIELDS = {"co", "no2", "o3", "so2", "q_model", "t_model"}
CUBE_COLUMNS = (
    "dataset_id", "valid_time", "grid_id", *FIELD_SPECS,
    "bronze_batch_id", "ingestion_run_id", "loaded_at",
)
PARAM_TO_COLUMN = {param_id: column for column, (param_id, _) in FIELD_SPECS.items()}
GRIB_KEYS = (
    "paramId", "shortName", "name", "units", "typeOfLevel", "level",
    "stepType", "dataType", "md5GridSection", "gridType", "Ni", "Nj",
    "iDirectionIncrementInDegrees", "jDirectionIncrementInDegrees",
    "validityDate", "validityTime", "numberOfMissing",
    "dataDate", "dataTime", "step", "NV",
)
REQUIRED_KEYS = (
    "paramId", "shortName", "name", "units", "typeOfLevel", "level",
    "stepType", "dataType", "md5GridSection", "gridType", "Ni", "Nj",
    "validityDate", "validityTime",
    "dataDate", "dataTime", "step", "numberOfMissing",
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
    """Validate identity AND source unit; gas scale is spatially/time dependent."""
    column = PARAM_TO_COLUMN.get(int(metadata["paramId"]))
    if column is None or str(metadata["shortName"]) != FIELD_SPECS[column][1]:
        raise DataQualityError("Unexpected CAMS paramId/shortName")
    native, kind, unit, scale, offset = CONTRACTS[column]
    if metadata["units"] != native and not (column == "aod550" and metadata["units"] == "1"):
        raise DataQualityError(f"{column}: unexpected source unit {metadata['units']!r}; expected {native!r}")
    return kind, unit, scale, offset


def source_variable(metadata):
    return (
        f"paramId={metadata['paramId']};shortName={metadata['shortName']};"
        f"level={metadata['typeOfLevel']}:{metadata['level']};"
        f"stepType={metadata['stepType']};dataType={metadata['dataType']}"
    )


def valid_time(metadata):
    day = str(int(metadata["validityDate"]))
    clock = f"{int(metadata['validityTime']):04d}"
    source_utc = datetime.strptime(day + clock, "%Y%m%d%H%M").replace(tzinfo=timezone.utc)
    if source_utc.minute or source_utc.hour % 3:
        raise DataQualityError("EAC4 analysis requires 3-hour UTC timestamps")
    if metadata["dataType"] != "an" or metadata["stepType"] != "instant" or float(metadata["step"]) != 0:
        raise DataQualityError("Expected instantaneous EAC4 analysis at forecast step 0")
    if (int(metadata["dataDate"]), int(metadata["dataTime"])) != (
        int(metadata["validityDate"]), int(metadata["validityTime"])
    ):
        raise DataQualityError("Analysis reference time differs from valid time")
    return source_utc.astimezone(SILVER_TZ)


def copy_bronze_file_to_local(spark, bronze_object, local_path):
    source = spark._jvm.org.apache.hadoop.fs.Path(bronze_object)
    target = spark._jvm.org.apache.hadoop.fs.Path(local_path)
    fs = source.getFileSystem(spark.sparkContext._jsc.hadoopConfiguration())
    fs.copyToLocalFile(False, source, target, True)


def read_message(eccodes, handle, seen_grids, source_file):
    grib = eccodes.codes_grib_new_from_file(handle)
    if grib is None:
        return None
    try:
        metadata = {key: ec_value(eccodes, grib, key) for key in GRIB_KEYS}
        if eccodes.codes_is_defined(grib, "pv"):
            metadata["pv"] = [float(x) for x in eccodes.codes_get_array(grib, "pv")]
        missing = [key for key in REQUIRED_KEYS if metadata[key] is None]
        if missing:
            raise DataQualityError(f"{source_file}: missing GRIB metadata {missing}")
        if int(metadata.get("numberOfMissing") or 0):
            raise DataQualityError(f"{source_file}: GRIB field contains missing grid values")

        grid_id = sha256_json("cams-grid-v1", str(metadata["md5GridSection"]).lower())
        ni, nj = int(metadata["Ni"]), int(metadata["Nj"])
        raw_values = eccodes.codes_get_array(grib, "values")
        if len(raw_values) != ni * nj:
            raise DataQualityError(f"{source_file}: grid size and value count disagree")
        # Preserve decoded precision until physics and unit conversions finish.
        values = [float(value) for value in raw_values]
        if any(not math.isfinite(value) for value in values):
            raise DataQualityError(f"{source_file}: non-finite native value")

        coordinates = None
        if grid_id not in seen_grids:
            latitudes = [float(x) for x in eccodes.codes_get_array(grib, "latitudes")]
            longitudes = [float(x) for x in eccodes.codes_get_array(grib, "longitudes")]
            if len(latitudes) != len(values) or len(longitudes) != len(values):
                raise DataQualityError(f"{source_file}: coordinate/value count mismatch")
            if any(not -90 <= x <= 90 for x in latitudes):
                raise DataQualityError(f"{source_file}: latitude outside [-90, 90]")
            if any(not -180 <= x <= 180 for x in longitudes):
                raise DataQualityError(f"{source_file}: longitude outside [-180, 180]")
            coordinates = latitudes, longitudes
        return metadata, valid_time(metadata), grid_id, values, coordinates
    finally:
        eccodes.codes_release(grib)


def register_grid(spark, metadata, grid_id, coordinates, run):
    latitudes, longitudes = coordinates
    ni, nj = int(metadata["Ni"]), int(metadata["Nj"])
    now = utc_now()
    grid = [(
        grid_id, str(metadata["md5GridSection"]).lower(), str(metadata["gridType"]),
        nj, ni,
        float(metadata["jDirectionIncrementInDegrees"])
        if metadata["jDirectionIncrementInDegrees"] is not None else None,
        float(metadata["iDirectionIncrementInDegrees"])
        if metadata["iDirectionIncrementInDegrees"] is not None else None,
        min(longitudes), min(latitudes), max(longitudes), max(latitudes),
        4326, run.dataset_id, run.run_id, now,
    )]
    points = [
        (grid_id, index, index // ni, index % ni, latitudes[index], longitudes[index])
        for index in range(len(latitudes))
    ]
    merge_dataframe(
        spark,
        spark.createDataFrame(grid, spark.table(f"{TABLE_PREFIX}.cams_grid").schema),
        f"{TABLE_PREFIX}.cams_grid", ["grid_id"],
    )
    merge_dataframe(
        spark,
        spark.createDataFrame(points, spark.table(f"{TABLE_PREFIX}.cams_grid_point").schema),
        f"{TABLE_PREFIX}.cams_grid_point", ["grid_id", "grid_point_id"],
    )


def register_sources(spark, files, first_messages, run, batch):
    now = utc_now()
    variable_rows = []
    source_rows = []
    for column in FIELD_SPECS:
        metadata = first_messages[column][0]
        file_meta = files[column]["meta"]
        kind, standard_unit, scale, offset = measurement_contract(metadata)
        native_name = source_variable(metadata)
        variable_id = sha256_json("silver-variable-v1", "cams", native_name, kind)
        variable_rows.append((
            variable_id, "cams", native_name, str(metadata["name"]), "atmospheric",
            kind, str(metadata["units"]), standard_unit, int(metadata["paramId"]),
            str(metadata["shortName"]),
            f"CAMS GRIB {metadata['typeOfLevel']} level {metadata['level']}; "
            f"stepType={metadata['stepType']}; dataType={metadata['dataType']}.",
            now,
        ))
        source_rows.append((
            run.dataset_id, batch.batch_id, column, variable_id,
            int(metadata["paramId"]), str(metadata["shortName"]), str(metadata["units"]),
            standard_unit, scale, offset, file_meta.source_file, file_meta.file_sha256,
            run.run_id, now,
            "mmr_rho_l60_virtual_temperature_v1" if column in GASES else "native_scale_offset_v1",
            json.dumps({
                "pipeline_version": PIPELINE_VERSION, "model_level": 60 if column in MODEL_LEVEL_FIELDS else None,
                "coefficients": json.loads(coefficient_provenance(aligned_coefficient_metadata(first_messages))[0])
                if column in GASES else None,
                "density_inputs": ["sp:Pa", "t_model:K", "q_model:kg/kg"] if column in GASES else None,
                "rd_j_kg_k": 287.05 if column in GASES else None,
                "epsilon": 0.621981 if column in GASES else None,
                "source_time": {key: metadata[key] for key in (
                    "dataDate", "dataTime", "step", "validityDate", "validityTime", "dataType", "stepType")},
                "quality_policy": "fail_on_invalid; use only succeeded ingestion_run",
            }, sort_keys=True),
            "validated",
        ))
    merge_dataframe(
        spark,
        spark.createDataFrame(variable_rows, spark.table(f"{TABLE_PREFIX}.variable").schema),
        f"{TABLE_PREFIX}.variable",
        ["source_system", "source_variable", "measurement_kind"],
    )
    merge_dataframe(
        spark,
        spark.createDataFrame(source_rows, spark.table(SOURCE_TABLE).schema),
        SOURCE_TABLE,
        ["dataset_id", "bronze_batch_id", "column_name"],
    )


def ensure_cube_schema(spark):
    """Validate standard arrays, reusing the additive model-field migration."""
    table = CUBE_TABLE
    fields = {field.name: field.dataType.simpleString() for field in spark.table(table).schema.fields}
    missing = set(FIELD_SPECS).difference(fields)
    if missing.difference(MODEL_LEVEL_FIELDS):
        raise DataQualityError(f"CAMS cube schema is missing original fields: {sorted(missing)}")
    for column in FIELD_SPECS:
        if column in fields and fields[column] != "array<float>":
            raise DataQualityError(f"CAMS cube {column} must be ARRAY<FLOAT>, got {fields[column]}")
    if missing:
        columns = ", ".join(f"`{column}` ARRAY<FLOAT>" for column in FIELD_SPECS if column in missing)
        spark.sql(f"ALTER TABLE {table} ADD COLUMNS ({columns})")


def align_grid_messages(messages, grid_coordinates, aligned_grids):
    """Align horizontal grids even when GRIB sections include different vertical metadata."""
    metadata, timestamp, grid_id, values, coordinates = messages[next(iter(FIELD_SPECS))]
    if len({message[1] for message in messages.values()}) != 1:
        raise DataQualityError("CAMS GRIB fields have different times")
    if coordinates is None:
        coordinates = grid_coordinates.get(grid_id)
    if coordinates is None:
        raise DataQualityError("Missing coordinates for a new CAMS grid")
    if grid_id in grid_coordinates and grid_coordinates[grid_id] != coordinates:
        raise DataQualityError("CAMS grid coordinates changed for the same grid ID")
    shape = (int(metadata["Ni"]), int(metadata["Nj"]))
    for other_metadata, _, other_grid_id, other_values, other_coordinates in messages.values():
        if (int(other_metadata["Ni"]), int(other_metadata["Nj"])) != shape or len(other_values) != len(values):
            raise DataQualityError("CAMS field grid shape mismatch")
        if other_coordinates is not None:
            if other_coordinates != coordinates:
                raise DataQualityError("CAMS grid coordinates conflict")
        elif aligned_grids.get(other_grid_id) != grid_id:
            raise DataQualityError("CAMS field has no verified horizontal grid alignment")
        if other_grid_id in aligned_grids and aligned_grids[other_grid_id] != grid_id:
            raise DataQualityError("CAMS GRIB grid section changed its horizontal alignment")
    grid_coordinates[grid_id] = coordinates
    for message in messages.values():
        aligned_grids[message[2]] = grid_id
    return metadata, timestamp, grid_id, coordinates


def merge_cube_chunk(spark, rows):
    if not rows:
        return 0
    # ALTER TABLE appends new columns after lineage columns on an existing table.
    # Match tuple order explicitly so a migrated table cannot swap variable arrays.
    schema = spark.table(CUBE_TABLE).select(*CUBE_COLUMNS).schema
    source = spark.createDataFrame(
        spark.sparkContext.parallelize(rows, CAMS_INPUT_PARTITIONS), schema
    )
    merge_dataframe(
        spark, source, CUBE_TABLE,
        ["dataset_id", "valid_time", "grid_id"],
    )
    return len(rows)


def transform(spark, batch, run):
    import eccodes

    grib_files = metadata_rows(batch, ["grib", "grib2", "grb", "grb2"])
    if len(grib_files) != len(FIELD_SPECS):
        raise DataQualityError(
            f"CAMS cube requires {len(FIELD_SPECS)} GRIB files, got {len(grib_files)}"
        )

    seen_grids = set()
    grid_shapes = {}
    grid_coordinates = {}
    aligned_grids = {}
    input_rows = output_rows = 0
    last_time = None
    chunk = []
    with tempfile.TemporaryDirectory(prefix="cams-cube-") as temp_dir, ExitStack() as stack:
        files = {}
        first_messages = {}
        for index, meta in enumerate(grib_files):
            report_file_progress(
                "Bronze -> Silver",
                meta,
                index=index + 1,
                total=len(grib_files),
                action="DOWNLOAD/READ GRIB",
            )
            if meta.bronze_object != f"{batch.bronze_path}/files/{meta.source_file}":
                raise DataQualityError(f"{meta.source_file}: source object is outside its declared Bronze batch")
            local_path = os.path.join(temp_dir, f"input-{index}.grib")
            copy_bronze_file_to_local(spark, meta.bronze_object, local_path)
            with open(local_path, "rb") as checksum_input:
                digest = hashlib.sha256()
                for block in iter(lambda: checksum_input.read(1024 * 1024), b""):
                    digest.update(block)
            if digest.hexdigest() != meta.file_sha256 or os.path.getsize(local_path) != meta.file_size:
                raise DataQualityError(f"{meta.source_file}: Bronze file SHA-256/size mismatch")
            handle = stack.enter_context(open(local_path, "rb"))
            message = read_message(eccodes, handle, seen_grids, meta.source_file)
            if message is None:
                raise DataQualityError(f"{meta.source_file}: empty GRIB file")
            metadata = message[0]
            param_id = int(metadata["paramId"])
            column = PARAM_TO_COLUMN.get(param_id)
            if column is None or str(metadata["shortName"]) != FIELD_SPECS[column][1]:
                raise DataQualityError(
                    f"{meta.source_file}: unexpected GRIB paramId/shortName "
                    f"{param_id}/{metadata['shortName']}"
                )
            if column in files:
                raise DataQualityError(f"Two CAMS GRIB files map to {column}")
            if column in MODEL_LEVEL_FIELDS and (
                str(metadata["typeOfLevel"]) != "hybrid" or int(metadata["level"]) != 60
            ):
                raise DataQualityError(f"{meta.source_file}: {column} requires hybrid model level 60")
            if column not in MODEL_LEVEL_FIELDS and (
                metadata["typeOfLevel"] != "surface" or int(metadata["level"]) != 0
            ):
                raise DataQualityError(f"{meta.source_file}: {column} requires surface level 0")
            measurement_contract(metadata)
            coefficient_id = coefficient_provenance(metadata)[1] if column in MODEL_LEVEL_FIELDS else None
            files[column] = {
                "meta": meta,
                "handle": handle,
                "source_variable": source_variable(metadata),
                "unit": str(metadata["units"]),
                "coefficient_id": coefficient_id,
            }
            first_messages[column] = message
        if set(files) != set(FIELD_SPECS):
            raise DataQualityError(f"CAMS fields missing: {sorted(set(FIELD_SPECS) - set(files))}")

        register_sources(spark, files, first_messages, run, batch)
        messages = first_messages
        while True:
            if all(message is None for message in messages.values()):
                break
            if any(message is None for message in messages.values()):
                raise DataQualityError("CAMS GRIB files have different message counts")
            metadata, timestamp, grid_id, coordinates = align_grid_messages(
                messages, grid_coordinates, aligned_grids
            )
            shape = (int(metadata["Ni"]), int(metadata["Nj"]))
            if grid_id in grid_shapes and grid_shapes[grid_id] != shape:
                raise DataQualityError("CAMS grid shape changed for the same grid ID")
            if last_time is not None and timestamp <= last_time:
                raise DataQualityError("CAMS GRIB times must be strictly increasing")
            last_time = timestamp

            if grid_id not in grid_shapes:
                register_grid(spark, metadata, grid_id, coordinates, run)
                grid_shapes[grid_id] = shape
            seen_grids.update(message[2] for message in messages.values())
            for column, message in messages.items():
                metadata = message[0]
                if (int(metadata["Ni"]), int(metadata["Nj"])) != shape:
                    raise DataQualityError(f"CAMS grid shape differs for {column}")
                if source_variable(metadata) != files[column]["source_variable"] or str(
                    metadata["units"]
                ) != files[column]["unit"]:
                    raise DataQualityError(f"CAMS GRIB metadata changed for {column}")
                if column in MODEL_LEVEL_FIELDS and coefficient_provenance(metadata)[1] != files[column]["coefficient_id"]:
                    raise DataQualityError(f"CAMS L60 coefficients changed for {column} at {timestamp}")

            try:
                normalized = normalize_fields(messages)
            except ValueError as exc:
                raise DataQualityError(f"CAMS normalization failed at {timestamp}, grid={grid_id}: {exc}") from exc

            now = utc_now()
            chunk.append((
                run.dataset_id, timestamp, grid_id,
                *(normalized[column] for column in FIELD_SPECS),
                batch.batch_id, run.run_id, now,
            ))
            input_rows += sum(len(messages[column][3]) for column in FIELD_SPECS)
            if len(chunk) >= CAMS_CHUNK_TIMESTEPS:
                output_rows += merge_cube_chunk(spark, chunk)
                print(f"CAMS cube committed {output_rows} time/grid rows", flush=True)
                chunk.clear()

            next_messages = {}
            for column in FIELD_SPECS:
                file = files[column]
                message = read_message(eccodes, file["handle"], seen_grids, file["meta"].source_file)
                next_messages[column] = message
            messages = next_messages

        output_rows += merge_cube_chunk(spark, chunk)
        print(f"CAMS cube committed {output_rows} time/grid rows (complete)", flush=True)
        # ecCodes/CFFI can retain a C FILE* until the Python stream itself is
        # released. Drop these references before temporary cleanup on Windows.
        stack.close()
        for file in files.values():
            file.clear()
        files.clear()
        handle = file = None
    return input_rows, output_rows, 0


def main():
    args = parse_args()
    spark = create_spark(PIPELINE)
    run = None
    try:
        bootstrap_schema(spark, args.schema_sql)
        batch = load_bronze_batch(spark, args.bronze_path)
        if batch.source != "cams" or batch.dataset_name != "eac4":
            raise ValueError(
                f"Expected cams/eac4 Bronze batch, got {batch.source}/{batch.dataset_name}"
            )
        ensure_cube_schema(spark)
        dataset_id = register_dataset(
            spark, batch, source_version=args.source_version,
            source_uri="https://ads.atmosphere.copernicus.eu/",
            description="CAMS EAC4 atmospheric reanalysis at native GRIB grid resolution.",
        )
        run = start_run(
            spark, batch, dataset_id, PIPELINE, pipeline_version=PIPELINE_VERSION
        )
        if run.skipped:
            return
        input_rows, output_rows, duplicates = transform(spark, batch, run)
        finish_run(
            spark, run, status="succeeded", input_rows=input_rows,
            output_rows=output_rows, duplicate_rows=duplicates,
        )
    except Exception as exc:
        if run is not None and not run.skipped:
            write_quality_issues(spark, run, [{
                "rule_id": "cams_normalization_failed", "severity": "fatal",
                "description": str(exc), "normalized_value": None,
            }])
            finish_run(spark, run, status="failed", error_message=str(exc))
        raise
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
