"""Read-only audit of completed Bronze -> Silver batches and replay snapshots.

Pass --bronze-path once per dataset. This script never runs transformations or
changes lakehouse tables. --snapshot-output/--compare refer to local JSON files.
"""

import argparse
import csv
import hashlib
import json
import math
import sys
import tempfile
from datetime import datetime
from pathlib import Path

JOBS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(JOBS / "silver"))
sys.path.insert(0, str(JOBS / "bronze"))

from pyspark.sql import functions as F
import admin_bronze_to_silver as admin
import cams_bronze_to_silver as cams
import climate_trace_bronze_to_silver as climate
import waqi_bronze_to_silver as waqi
from common import create_spark, finite_number, load_bronze_batch, sha256_json, _valid_source_file
from landing_to_bronze import remote_sha256


def unique(frame, keys):
    assert not frame.groupBy(*keys).count().filter("count > 1").limit(1).count(), keys
    for key in keys:
        assert not frame.filter(F.col(key).isNull()).limit(1).count(), key
    return frame.count()


def present_in(frame, column, target, target_column):
    missing = frame.filter(F.col(column).isNotNull()).select(column).distinct().join(
        target.select(F.col(target_column).alias(column)).distinct(), column, "left_anti"
    )
    assert not missing.limit(1).count(), f"Missing reference: {column} -> {target_column}"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bronze-path", action="append", required=True)
    parser.add_argument("--snapshot-output", type=Path)
    parser.add_argument("--compare", type=Path)
    args = parser.parse_args()
    spark = create_spark("silver-five-dataset-audit")
    state = {"batches": {}, "snapshots": {}}
    try:
        # Execute real Spark expressions: NaN equality and INT saturation differ
        # from Python, so these regressions must be exercised on Spark itself.
        values = [None, float("nan"), float("inf"), -float("inf"), -1., 0., 24., 1.5, 2147483647., 2147483648.]
        checks = spark.createDataFrame(list(enumerate(values)), "id INT, value DOUBLE").select(
            "id", finite_number(F.col("value")).alias("finite"),
            waqi.valid_aqi_value(F.col("value")).alias("aqi"),
        ).orderBy("id").collect()
        assert [r.finite for r in checks] == [False] * 4 + [True] * 6
        assert [r.aqi for r in checks] == [False] * 5 + [True, True, False, True, False]
        for value in (None, "", ".", "..", "/file", "x/../file", "x//file", "x/./file", "x\\file"):
            assert not _valid_source_file(value), value
        assert _valid_source_file("json/đơn vị.geojson")

        with tempfile.TemporaryDirectory(prefix="silver-audit-") as folder:
            folder = Path(folder)
            for bronze_path in args.bronze_path:
                batch = load_bronze_batch(spark, bronze_path)
                key = f"{batch.source}/{batch.dataset_name}"
                assert key not in state["batches"], "Pass only one batch per dataset"
                if batch.source == "reference":
                    module = admin
                    version = admin.source_contract(spark, batch, None)[0]
                elif batch.source == "waqi":
                    module, version = waqi, None
                elif batch.source == "climate_trace":
                    module, version = climate, None
                elif key == "cams/eac4":
                    module = cams
                    version = "EAC4-validation-" + batch.batch_id if batch.batch_id.startswith("cams-validation-") else "EAC4"
                else:
                    raise AssertionError(f"Unsupported dataset: {key}")
                dataset_id = sha256_json("silver-dataset-v1", batch.source, batch.dataset_name, version or "")
                pipeline_version = getattr(module, "PIPELINE_VERSION", "1.0.0")
                runs = spark.table("nessie.silver.ingestion_run").filter(
                    (F.col("dataset_id") == dataset_id) & (F.col("bronze_batch_id") == batch.batch_id)
                    & (F.col("pipeline_name") == module.PIPELINE) & (F.col("pipeline_version") == pipeline_version)
                ).orderBy(F.desc("started_at")).collect()
                assert runs and runs[0].status == "succeeded", f"No successful current run: {key}"
                run = runs[0]
                assert run.finished_at >= run.started_at
                assert sum(r.status == "succeeded" for r in runs) == 1
                meta_rows = batch.metadata.collect()
                hashes = {}
                for index, meta in enumerate(meta_rows):
                    path = spark._jvm.org.apache.hadoop.fs.Path(meta.bronze_object)
                    fs = path.getFileSystem(spark.sparkContext._jsc.hadoopConfiguration())
                    assert fs.getFileStatus(path).getLen() == meta.file_size
                    actual = remote_sha256(spark, fs, path)
                    assert actual == meta.file_sha256, meta.source_file
                    hashes[meta.source_file] = actual
                    if (index + 1) % 500 == 0:
                        print(f"AUDIT {key}: verified SHA-256 {index + 1}/{len(meta_rows)}", flush=True)

                def local(meta):
                    target = folder / (hashlib.sha256(meta.source_file.encode()).hexdigest() + ".data")
                    cams.copy_bronze_file_to_local(spark, meta.bronze_object, str(target))
                    return target

                tables = {}
                expected_input = 0
                expected_output = 0
                if batch.source == "reference":
                    if batch.dataset_name == admin.OPEN_ADMIN_DATASET:
                        expected = {}
                        for suffix in ("all-province.json", "all-ward.json"):
                            meta = next(m for m in meta_rows if m.source_file.endswith(suffix))
                            for item in json.loads(local(meta).read_text()):
                                code = str(item["code"]["id"] or item["id"])
                                expected[code] = (item["name"]["local"].strip(),
                                                  item["parent"]["id"] if item["parent"] else None)
                                expected_input += 1
                    else:
                        meta = next(m for m in meta_rows if m.source_file.endswith("json/full_json_generated_data_vn_units.json"))
                        expected = {}
                        for province in json.loads(local(meta).read_text()):
                            expected[str(province["Code"])] = (province["Name"].strip(), None)
                            expected_input += 1 + len(province["Wards"])
                            for ward in province["Wards"]:
                                expected[str(ward["Code"])] = (ward["Name"].strip(), str(ward["ProvinceCode"]))
                    sources = spark.table("nessie.silver.admin_unit_source").filter(F.col("dataset_id") == dataset_id)
                    units = spark.table("nessie.silver.admin_unit").join(
                        sources.select("admin_unit_version_id").distinct(), "admin_unit_version_id"
                    )
                    actual = {r.admin_code: (r.name_vi, r.parent_code) for r in units.collect()}
                    assert actual == expected
                    assert len(actual) == unique(units, ["admin_unit_version_id"])
                    present_in(units, "parent_admin_unit_version_id", units, "admin_unit_version_id")
                    tables["admin_unit"] = units
                    tables["admin_unit_source"] = sources
                    boundaries = spark.table("nessie.silver.admin_boundary").filter(F.col("dataset_id") == dataset_id)
                    boundary_files = {m.source_file for m in meta_rows if m.file_format.lower() == "geojson"}
                    if boundary_files:
                        boundary_count = unique(boundaries, ["boundary_id"])
                        assert {r.source_file for r in boundaries.select("source_file").distinct().collect()} == boundary_files
                        assert boundary_count == len(boundary_files), "This batch expects one feature per GeoJSON file"
                        present_in(boundaries, "admin_unit_version_id", units, "admin_unit_version_id")
                        expected_input += boundary_count
                        tables["admin_boundary"] = boundaries
                    expected_output = expected_input - run.duplicate_rows
                elif batch.source == "waqi":
                    expected = {}
                    for meta in meta_rows:
                        if meta.file_format.lower() != "csv":
                            continue
                        station_id = sha256_json("waqi-station-v1", dataset_id, waqi.normalized_filename(meta.source_file))
                        with local(meta).open(encoding="utf-8-sig", newline="") as stream:
                            reader = csv.DictReader(stream)
                            reader.fieldnames = [name.strip() for name in reader.fieldnames]
                            for item in reader:
                                expected_input += 1
                                day = datetime.strptime(item["date"].strip(), "%Y/%m/%d").date()
                                for variable in waqi.CANONICAL_COLUMNS:
                                    if variable not in item:
                                        continue
                                    raw = (item[variable] or "").strip()
                                    value = int(raw) if raw else None
                                    variable_id = sha256_json("silver-variable-v1", "waqi", variable, "daily_aqi")
                                    record_key = (station_id, day, variable_id)
                                    assert record_key not in expected or expected[record_key] == value
                                    expected[record_key] = value
                    observations = spark.table("nessie.silver.waqi_daily_observation").filter(F.col("dataset_id") == dataset_id)
                    count = unique(observations, ["dataset_id", "station_id", "observation_date", "variable_id"])
                    assert count == len(expected)
                    for row in observations.toLocalIterator():
                        value = expected[(row.station_id, row.observation_date, row.variable_id)]
                        assert row.aqi_value == value
                        assert (row.qc_flag, row.missing_reason) == (("missing", "source_blank") if value is None else ("ok", None))
                    expected_output = len(expected)
                    tables = {name: spark.table("nessie.silver." + name).filter(F.col("dataset_id") == dataset_id)
                              for name in ("waqi_daily_observation", "waqi_station_source", "waqi_station_variable")}
                    stations = spark.table("nessie.silver.waqi_station")
                    present_in(observations, "station_id", stations, "station_id")
                    present_in(observations, "variable_id", spark.table("nessie.silver.variable"), "variable_id")
                    assert stations.filter("timezone IS NULL OR timezone <> 'Asia/Ho_Chi_Minh'").count() == 0
                elif batch.source == "climate_trace":
                    aggregate_count = source_count = 0
                    quantities = {}
                    for meta in meta_rows:
                        if meta.file_format.lower() != "csv":
                            continue
                        with local(meta).open(encoding="utf-8-sig", newline="") as stream:
                            for item in csv.DictReader(stream):
                                expected_input += 1
                                if "source_id" in item:
                                    source_count += 1
                                    record_key = ("climate_trace:" + item["source_id"], int(item["year"]), item["gas"].lower())
                                    value = float(item["annual_emissions_quantity"])
                                    assert record_key not in quantities or quantities[record_key] == value
                                    quantities[record_key] = value
                                else:
                                    aggregate_count += 1
                    tables = {name: spark.table("nessie.silver." + name).filter(F.col("dataset_id") == dataset_id)
                              for name in ("emission_aggregate", "emission_source", "emission_source_observation")}
                    aggregates = tables["emission_aggregate"]
                    observations = tables["emission_source_observation"]
                    assert unique(aggregates, ["aggregate_id"]) == aggregate_count
                    assert unique(observations, ["dataset_id", "source_id", "year_label", "variable_id"]) == len(quantities)
                    assert source_count - len(quantities) == run.duplicate_rows
                    variables = spark.table("nessie.silver.variable")
                    gases = {r.variable_id: r.source_variable for r in variables.filter("source_system='climate_trace'").collect()}
                    for row in observations.toLocalIterator():
                        expected = quantities[(row.source_id, row.year_label, gases[row.variable_id])]
                        assert row.emission_quantity_native == expected and math.isfinite(expected)
                    for frame in (aggregates, observations):
                        assert not frame.filter(~finite_number(F.col("emission_quantity_native"))).count()
                        assert not frame.filter(F.col("emission_quantity_standard").isNotNull()).count()
                        present_in(frame, "variable_id", variables, "variable_id")
                        assert not frame.filter("period_end < period_start").count()
                    present_in(observations, "source_id", tables["emission_source"], "source_id")
                    expected_output = aggregate_count + len(quantities)
                else:
                    frame = spark.table(cams.CUBE_TABLE).filter(F.col("dataset_id") == dataset_id)
                    count = unique(frame, ["dataset_id", "valid_time", "grid_id"])
                    for row in frame.toLocalIterator():
                        for column in cams.FIELD_SPECS:
                            values = row[column]
                            assert values is not None
                            expected_input += len(values)
                            assert all(value is not None and math.isfinite(value) for value in values)
                    expected_output = count
                    tables = {"cams_cube_standard": frame,
                              "cams_cube_standard_source": spark.table(cams.SOURCE_TABLE).filter(F.col("dataset_id") == dataset_id)}

                assert (run.input_rows, run.output_rows) == (expected_input, expected_output), key
                counts = {name: frame.count() for name, frame in tables.items()}
                dimension_keys = {
                    "admin_unit_source": ["admin_unit_version_id", "dataset_id", "source_admin_code", "source_record_locator"],
                    "waqi_station_source": ["dataset_id", "source_station_key"],
                    "waqi_station_variable": ["dataset_id", "station_id", "variable_id"],
                    "emission_source": ["source_id"],
                    "cams_cube_standard_source": ["dataset_id", "bronze_batch_id", "column_name"],
                }
                for name, frame in tables.items():
                    if name in dimension_keys:
                        unique(frame, dimension_keys[name])
                    if "source_file" in frame.columns:
                        lineage = frame.select("source_file", "source_file_sha256").distinct()
                        metadata = batch.metadata.select("source_file", F.col("file_sha256").alias("source_file_sha256"))
                        assert not lineage.join(metadata, ["source_file", "source_file_sha256"], "left_anti").count()
                    snapshots = spark.sql(f"SELECT snapshot_id FROM nessie.silver.{name}.snapshots ORDER BY committed_at, snapshot_id").collect()
                    state["snapshots"][name] = [r.snapshot_id for r in snapshots]
                state["batches"][key] = dict(
                    batch_id=batch.batch_id, run_id=run.run_id, pipeline_version=run.pipeline_version,
                    input_records_or_scalars=expected_input, output_records=expected_output,
                    duplicate_rows=run.duplicate_rows, file_hashes=hashes, table_counts=counts,
                )
                print("SILVER_AUDIT=" + json.dumps({"dataset": key, "sha256_files": len(hashes),
                      "input": expected_input, "output": expected_output, "tables": counts}), flush=True)
        if args.compare:
            before = json.loads(args.compare.read_text())
            assert before == state, "Replay changed file hashes, run identity, counts or fact snapshots"
            print("SILVER_REPLAY_IDENTICAL=true", flush=True)
        if args.snapshot_output:
            args.snapshot_output.write_text(json.dumps(state, sort_keys=True, indent=2))
        print("SILVER_AUDIT_OK=" + str(len(state["batches"])), flush=True)
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
