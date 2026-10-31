"""Opt-in Spark/MinIO/Iceberg integration check on at most eight real GRIB times.

Run with spark-submit in the Compose Spark container (see ../README.md).
Writes a small, uniquely identified validation Bronze batch and Silver dataset;
does not backfill production. Validation artifacts are retained for inspection.
"""

import argparse
import hashlib
import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import eccodes as ec
import numpy as np

JOBS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(JOBS / "silver"))
sys.path.insert(0, str(JOBS / "bronze"))
import landing_to_bronze as bronze
import cams_bronze_to_silver as cams
from common import create_spark, load_bronze_batch, start_run


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=Path("/opt/spark/work-dir/landing/CAMS/EAC4"))
    parser.add_argument("--timesteps", type=int, default=3, choices=range(1, 9))
    parser.add_argument("--bronze-path", help="Reuse an existing cams-validation-* batch instead of creating one")
    args = parser.parse_args()
    batch_id = "cams-validation-" + uuid4().hex[:12]
    source_version = "EAC4-validation-" + batch_id
    ingestion_date = datetime.now(timezone.utc).date().isoformat()
    bronze_path = f"s3a://lakehouse/bronze/cams/eac4/ingestion_date={ingestion_date}/batch_id={batch_id}"
    expected_hashes = {}
    if args.bronze_path:
        spark = create_spark("cams-integration-existing-batch")
        try:
            batch = load_bronze_batch(spark, args.bronze_path)
            assert batch.batch_id.startswith("cams-validation-"), "Only isolated validation batches may be replayed"
            assert (batch.source, batch.dataset_name) == ("cams", "eac4")
            batch_id = batch.batch_id
            source_version = "EAC4-validation-" + batch_id
            bronze_path = batch.bronze_path
            expected_hashes = {r.source_file: r.file_sha256 for r in batch.metadata.collect()}
        finally:
            spark.stop()
    source_files = [] if args.bronze_path else sorted(args.source_dir.glob("*.grib"))
    assert args.bronze_path or len(source_files) == 20, "Integration requires all 20 real EAC4 files"
    original_stats = {p: (p.stat().st_size, p.stat().st_mtime_ns) for p in source_files}
    native = {}
    with tempfile.TemporaryDirectory(prefix="cams-validation-") as work:
        work = Path(work)
        sample_dir = work / "CAMS" / "EAC4"
        sample_dir.mkdir(parents=True)
        for path in source_files:
            with path.open("rb") as stream, (sample_dir / path.name).open("wb") as output:
                for _ in range(args.timesteps):
                    handle = ec.codes_grib_new_from_file(stream)
                    assert handle is not None
                    try:
                        # Exact message bytes; no re-encoding of native source values.
                        output.write(ec.codes_get_message(handle))
                    finally:
                        ec.codes_release(handle)
        if not args.bronze_path:
            expected_hashes = {p.name: digest(p) for p in sample_dir.iterdir()}
            with patch.object(sys, "argv", ["landing_to_bronze.py", "--dataset", "CAMS/EAC4",
                              "--landing-root", str(work), "--batch-id", batch_id,
                              "--ingestion-date", ingestion_date]):
                bronze.main()
        with patch.object(sys, "argv", ["cams_bronze_to_silver.py", "--bronze-path", bronze_path,
                          "--source-version", source_version]):
            cams.main()

        spark = create_spark("cams-integration-verification")
        try:
            batch = load_bronze_batch(spark, bronze_path)
            runs = spark.table("nessie.silver.ingestion_run").filter(f"bronze_batch_id='{batch_id}'").collect()
            assert len(runs) == 1 and runs[0].status == "succeeded"
            run_row = runs[0]
            assert run_row.pipeline_version == cams.PIPELINE_VERSION
            dataset_id = run_row.dataset_id
            run = SimpleNamespace(dataset_id=dataset_id, run_id=run_row.run_id)
            legacy_snapshots = {
                name: spark.sql(f"SELECT snapshot_id FROM nessie.silver.{name}.snapshots").collect()
                for name in ("cams_cube", "cams_cube_source")
            }
            schema = spark.table(cams.CUBE_TABLE).schema
            assert set(schema.fieldNames()) == set(cams.CUBE_COLUMNS)
            assert all(schema[c].dataType.simpleString() == "array<float>" for c in cams.FIELD_SPECS)
            ddl = spark.sql(f"SHOW CREATE TABLE {cams.CUBE_TABLE}").first()[0]
            assert "years(valid_time)" in ddl or "year(valid_time)" in ddl

            def snapshot():
                return spark.table(cams.CUBE_TABLE).filter(f"dataset_id='{dataset_id}'").orderBy("valid_time").collect()

            rows = snapshot()
            assert len(rows) == args.timesteps
            assert len({(r.dataset_id, r.valid_time, r.grid_id) for r in rows}) == len(rows)
            lineage = spark.table(cams.SOURCE_TABLE).filter(f"dataset_id='{dataset_id}'").collect()
            assert len(lineage) == 20
            assert len({r.column_name for r in lineage}) == 20
            assert all(r.standard_unit == cams.CONTRACTS[r.column_name][2] for r in lineage)
            assert all(r.native_unit == cams.CONTRACTS[r.column_name][0] and r.quality_status == "validated"
                       for r in lineage)
            for row in lineage:
                if row.column_name in cams.GASES:
                    assert row.standard_scale is None and row.standard_offset is None
                    assert json.loads(row.conversion_metadata)["coefficients"]["source"] == "grib_pv_l60"
            for meta in batch.metadata.collect():
                target = work / ("bronze-" + meta.source_file)
                cams.copy_bronze_file_to_local(spark, meta.bronze_object, str(target))
                assert digest(target) == expected_hashes[meta.source_file] == meta.file_sha256
                with target.open("rb") as stream:
                    for index in range(args.timesteps):
                        message = cams.read_message(ec, stream, set(), meta.source_file)
                        assert message is not None
                        native.setdefault(index, {})[cams.PARAM_TO_COLUMN[int(message[0]["paramId"])]] = message
                    assert cams.read_message(ec, stream, set(), meta.source_file) is None
            cells = len(native[0]["sp"][3])
            coordinates = native[0]["sp"][4]
            grid = spark.table("nessie.silver.cams_grid_point").filter(
                f"grid_id='{rows[0].grid_id}'"
            ).orderBy("grid_point_id").collect()
            assert len(grid) == cells
            assert [(r.latitude, r.longitude) for r in grid] == list(zip(*coordinates))
            max_relative_error = 0.
            output_arrays = output_values = valid_values = null_values = invalid_values = pm_zero_values = 0
            for index, row in enumerate(rows):
                fields = native[index]
                for column in cams.FIELD_SPECS:
                    values = row[column]
                    assert values is not None and len(values) == cells
                    output_arrays += 1
                    output_values += len(values)
                    null_values += sum(v is None for v in values)
                    invalid_values += sum(v is not None and not np.isfinite(v) for v in values)
                    valid_values += sum(v is not None and np.isfinite(v) for v in values)
                # Spark collect returns timestamps in the Python process timezone.
                source_time = fields["sp"][1].astimezone(timezone.utc).replace(tzinfo=None)
                assert row.valid_time == source_time
                if index:
                    assert (row.valid_time - rows[index - 1].valid_time).total_seconds() == 3600
                metadata = fields["co"][0]
                pv = metadata["pv"]
                for point in range(cells):
                    sp = fields["sp"][3][point]
                    t = fields["t_model"][3][point]
                    q = fields["q_model"][3][point]
                    pressure = ((pv[59] + pv[120] * sp) + (pv[60] + pv[121] * sp)) / 2
                    density = pressure / (287.05 * t * (1 + ((1 - .621981) / .621981) * q))
                    for column in cams.FIELD_SPECS:
                        value = fields[column][3][point]
                        if column in cams.GASES:
                            expected = value * density * 1e9
                        else:
                            _, _, _, scale, offset = cams.CONTRACTS[column]
                            expected = value * scale + offset
                        actual = row[column][point]
                        assert np.isfinite(actual)
                        assert np.isclose(actual, expected, rtol=1e-6, atol=2e-6), (column, point, actual, expected)
                        if column in ("pm1", "pm2p5", "pm10") and value == 0.:
                            assert actual == 0., "Valid zero PM must remain zero, not missing"
                            pm_zero_values += 1
                        if expected:
                            max_relative_error = max(max_relative_error, abs(actual / expected - 1))
            expected_input = args.timesteps * cells * 20
            input_messages = sum(len(fields) for fields in native.values())
            input_values = sum(len(message[3]) for fields in native.values() for message in fields.values())
            assert input_messages == args.timesteps * 20
            assert input_values == output_values == valid_values == expected_input
            assert null_values == invalid_values == 0
            assert (run_row.input_rows, run_row.output_rows, run_row.invalid_rows) == (expected_input, args.timesteps, 0)
            # Exercise real MERGE, including updates after an interrupted run.
            assert cams.transform(spark, batch, run) == (expected_input, args.timesteps, 0)
            after = snapshot()
            payload = lambda items: [tuple(r[c] for c in ("dataset_id", "valid_time", "grid_id", *cams.FIELD_SPECS)) for r in items]
            assert payload(rows) == payload(after), "MERGE duplicated or reconverted values"
            skipped = start_run(spark, batch, dataset_id, cams.PIPELINE, pipeline_version=cams.PIPELINE_VERSION)
            assert skipped.skipped and skipped.run_id == run.run_id
            for meta in batch.metadata.collect():
                target = work / ("after-" + meta.source_file)
                cams.copy_bronze_file_to_local(spark, meta.bronze_object, str(target))
                assert digest(target) == expected_hashes[meta.source_file], "Bronze was changed"
            assert original_stats == {p: (p.stat().st_size, p.stat().st_mtime_ns) for p in source_files}
            for name, before in legacy_snapshots.items():
                assert before == spark.sql(f"SELECT snapshot_id FROM nessie.silver.{name}.snapshots").collect()
            print("CAMS_INTEGRATION_RESULT=" + json.dumps(dict(
                batch_id=batch_id, bronze_path=bronze_path, dataset_id=dataset_id,
                timesteps=args.timesteps, grid_points=cells, input_grib_messages=input_messages,
                input_scalar_values=input_values, output_cube_rows=len(after), output_arrays=output_arrays,
                output_scalar_values=output_values, valid_values=int(valid_values), null_values=int(null_values),
                source_files=20, duplicates=0, invalid_values=int(invalid_values), filtered_values=0,
                valid_pm_zero_values=pm_zero_values, legacy_snapshots_unchanged=True,
                bronze_sha256_unchanged=True, merge_retry_identical=True, successful_run_skipped=True,
                max_float32_relative_error=max_relative_error,
            )), flush=True)
        finally:
            spark.stop()


if __name__ == "__main__":
    main()
