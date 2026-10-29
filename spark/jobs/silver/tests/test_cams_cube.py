"""Driver regression tests without a Spark JVM: python -m unittest discover -s spark/jobs/silver/tests."""

import copy
import hashlib
import importlib.util
import re
import sys
import types
import unittest
from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cams_physics import CONTRACTS, L60_A, L60_B, normalize_fields

# Isolate Spark-dependent orchestration imports; exercise the real CAMS driver
# functions below. No PySpark installation or running lakehouse is required.
common = types.ModuleType("common")
common.SILVER_TZ = timezone(timedelta(hours=7))
common.TABLE_PREFIX = "nessie.silver"
common.DataQualityError = type("DataQualityError", (RuntimeError,), {})
for name in (
    "bootstrap_schema", "create_spark", "finish_run", "load_bronze_batch",
    "merge_dataframe", "metadata_rows", "report_file_progress", "register_dataset",
    "start_run", "utc_now", "write_quality_issues",
):
    setattr(common, name, Mock())
common.sha256_json = lambda namespace, *parts: ":".join((namespace, *map(str, parts)))
spec = importlib.util.spec_from_file_location(
    "cams_under_test", Path(__file__).resolve().parents[1] / "cams_bronze_to_silver.py"
)
cams = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, {"common": common}):
    spec.loader.exec_module(cams)


def messages():
    result = {}
    for index, (column, (param_id, short_name)) in enumerate(cams.FIELD_SPECS.items()):
        model = column in cams.MODEL_LEVEL_FIELDS
        metadata = {
            "paramId": param_id, "shortName": short_name, "name": column,
            "Ni": 2, "Nj": 1, "typeOfLevel": "hybrid" if model else "surface",
            "level": 60 if model else 0, "units": CONTRACTS[column][0],
            "stepType": "instant", "dataType": "an",
            "dataDate": 20030101, "dataTime": 0, "step": 0,
            "validityDate": 20030101, "validityTime": 0,
            "NV": 122 if model else 0,
        }
        if model:
            metadata["pv"] = list(L60_A) + list(L60_B)
        values = {
            "K": [300., 290.], "Pa": [101325., 90000.],
            "kg m**-3": [1e-9, 2e-9], "kg m**-2": [1e-6, 2e-6],
            "kg kg**-1": [.01, .02] if column == "q_model" else [2e-8, 3e-8],
            "m s**-1": [-2., 3.], "~": [.1, .2],
        }[metadata["units"]]
        result[column] = (
            metadata, datetime(2003, 1, 1, tzinfo=timezone.utc),
            "hybrid-grid" if model else "surface-grid", values,
            ([10.0, 10.0], [105.0, 105.75]),
        )
    return result


class FakeTable:
    def __init__(self, columns):
        self.columns = list(columns)
        self.schema = types.SimpleNamespace(fields=[
            types.SimpleNamespace(name=name, dataType=types.SimpleNamespace(simpleString=lambda: "array<float>"))
            for name in columns
        ])

    def select(self, *columns):
        return FakeTable(columns)


class FakeSpark:
    def __init__(self, columns):
        self.frame = FakeTable(columns)
        self.statements = []
        self.sparkContext = types.SimpleNamespace(parallelize=lambda rows, partitions: rows)

    def table(self, name):
        return self.frame

    def sql(self, statement):
        self.statements.append(statement)
        self.frame = FakeTable(self.frame.columns + re.findall(r"`(\w+)` ARRAY<FLOAT>", statement))

    def createDataFrame(self, rows, schema):
        return [dict(zip((field.name for field in schema.fields), row)) for row in rows]


class CamsCubeTests(unittest.TestCase):
    def test_aligns_surface_and_hybrid_sections_by_ordered_coordinates(self):
        coordinates, aligned = {}, {}
        _, _, grid_id, _ = cams.align_grid_messages(messages(), coordinates, aligned)
        self.assertEqual(grid_id, "surface-grid")
        self.assertEqual(aligned["hybrid-grid"], grid_id)
        subsequent = {column: (*message[:4], None) for column, message in messages().items()}
        self.assertEqual(cams.align_grid_messages(subsequent, coordinates, aligned)[2], grid_id)

    def test_rejects_different_coordinate_order(self):
        source = messages()
        source["co"] = (*source["co"][:4], ([10.0, 10.0], [105.75, 105.0]))
        with self.assertRaisesRegex(cams.DataQualityError, "coordinates conflict"):
            cams.align_grid_messages(source, {}, {})

    def test_rejects_different_times(self):
        source = messages()
        value = source["co"]
        source["co"] = (value[0], value[1] + timedelta(hours=3), *value[2:])
        with self.assertRaisesRegex(cams.DataQualityError, "different times"):
            cams.align_grid_messages(source, {}, {})

    def test_rejects_unverified_grid(self):
        source = messages()
        source["co"] = (*source["co"][:4], None)
        with self.assertRaisesRegex(cams.DataQualityError, "no verified horizontal"):
            cams.align_grid_messages(source, {}, {})

    def test_gas_concentration_and_humidity_remain_distinct(self):
        for column in cams.GASES:
            self.assertEqual(
                cams.measurement_contract(messages()[column][0]),
                ("mass_concentration", "ug/m3", None, None),
            )
        self.assertEqual(
            cams.measurement_contract(messages()["q_model"][0]),
            ("specific_humidity", "kg/kg", 1.0, 0.0),
        )

    def test_migration_adds_only_missing_arrays_and_can_be_repeated(self):
        old_columns = [name for name in cams.CUBE_COLUMNS if name not in cams.MODEL_LEVEL_FIELDS]
        spark = FakeSpark(old_columns)
        cams.ensure_cube_schema(spark)
        cams.ensure_cube_schema(spark)
        self.assertEqual(len(spark.statements), 1)
        self.assertEqual(set(spark.frame.columns), set(cams.CUBE_COLUMNS))
        self.assertTrue(spark.frame.columns.index("co") > spark.frame.columns.index("loaded_at"))

    def test_migrated_column_order_preserves_each_variable_and_lineage(self):
        old_columns = [name for name in cams.CUBE_COLUMNS if name not in cams.MODEL_LEVEL_FIELDS]
        spark = FakeSpark(old_columns)
        cams.ensure_cube_schema(spark)
        row = ("dataset", datetime.now(timezone.utc), "grid",
               *([float(index)] for index in range(20)), "batch", "run", datetime.now(timezone.utc))
        with patch.object(cams, "merge_dataframe") as merge:
            self.assertEqual(cams.merge_cube_chunk(spark, [row]), 1)
        output = merge.call_args.args[1][0]
        for index, column in enumerate(cams.FIELD_SPECS):
            self.assertEqual(output[column], [float(index)])
        self.assertEqual(output["bronze_batch_id"], "batch")
        self.assertEqual(output["ingestion_run_id"], "run")

    def test_schema_sql_and_driver_use_same_twenty_arrays(self):
        schema_path = next(
            parent / "lakehouse/silver/silver.sql" for parent in Path(__file__).resolve().parents
            if (parent / "lakehouse/silver/silver.sql").is_file()
        )
        sql = schema_path.read_text(encoding="utf-8")
        body = sql.split("CREATE TABLE IF NOT EXISTS nessie.silver.cams_cube_standard (", 1)[1].split(")", 1)[0]
        self.assertEqual(re.findall(r"^\s+(\w+)\s+ARRAY<FLOAT>", body, re.M), list(cams.FIELD_SPECS))
        self.assertEqual(len(cams.FIELD_SPECS), 20)

    def run_transform(self, source, steps=3, file_limit=None, metadata_override=None):
        streams = {name: 0 for name in source}
        bronze_path = "s3a://test/bronze/cams/eac4/batch"
        metadata = [types.SimpleNamespace(source_file=name, bronze_object=f"{bronze_path}/files/{name}",
                    file_size=0, file_sha256=hashlib.sha256(b"").hexdigest()) for name in source]
        if metadata_override:
            for key, value in metadata_override.items():
                setattr(metadata[0], key, value)
        if file_limit is not None:
            metadata = metadata[:file_limit]

        def read(eccodes, handle, seen, name):
            index = streams[name]
            streams[name] += 1
            if index == steps:
                return None
            value = copy.deepcopy(source[name])
            return (value[0], value[1] + timedelta(hours=index * 3), value[2], value[3],
                    None if value[2] in seen else value[4])

        chunks = []
        with ExitStack() as stack:
            for context in (
                patch.dict(sys.modules, {"eccodes": types.ModuleType("eccodes")}),
                patch.object(cams, "metadata_rows", return_value=metadata),
                patch.object(cams, "copy_bronze_file_to_local", side_effect=lambda spark, src, dest: Path(dest).touch()),
                patch.object(cams, "read_message", side_effect=read),
                patch.object(cams, "register_sources"),
                patch.object(cams, "utc_now", return_value=datetime.now(timezone.utc)),
                patch.object(cams, "CAMS_CHUNK_TIMESTEPS", 2),
                patch.object(cams, "merge_cube_chunk", side_effect=lambda spark, rows: chunks.extend(rows) or len(rows)),
            ):
                stack.enter_context(context)
            register_grid = stack.enter_context(patch.object(cams, "register_grid"))
            result = cams.transform(None, types.SimpleNamespace(batch_id="batch", bronze_path=bronze_path),
                                    types.SimpleNamespace(dataset_id="dataset", run_id="run"))
        return result, chunks, register_grid

    def test_twenty_streams_write_aligned_chunks_with_all_arrays(self):
        result, chunks, register_grid = self.run_transform(messages())
        self.assertEqual(result, (120, 3, 0))
        self.assertEqual(len(chunks), 3)
        register_grid.assert_called_once()
        for row in chunks:
            self.assertEqual(len(row), len(cams.CUBE_COLUMNS))
            for index, column in enumerate(cams.FIELD_SPECS):
                self.assertEqual(row[index + 3], normalize_fields(messages())[column])

    def test_conversion_preserves_source_arrays_and_repeats_identically(self):
        source = messages()
        before = copy.deepcopy(source)
        first, rows, _ = self.run_transform(source)
        second, rerun, _ = self.run_transform(source)
        self.assertEqual(first, second)
        self.assertEqual([r[:23] for r in rows], [r[:23] for r in rerun])
        self.assertEqual(source, before)
        self.assertEqual(len({r[:3] for r in rows}), len(rows))

    def test_bad_unit_never_reaches_standard_cube(self):
        source = messages()
        source["co"][0]["units"] = "ug/m3"
        with self.assertRaisesRegex(cams.DataQualityError, "unexpected source unit"):
            self.run_transform(source)

    def test_invalid_density_input_never_writes_concentration(self):
        source = messages()
        source["q_model"][3][0] = float("nan")
        with self.assertRaisesRegex(cams.DataQualityError, "normalization failed"):
            self.run_transform(source)

    def test_rejects_file_checksum_size_and_bronze_path_mismatch(self):
        for override, error in (
            ({"file_sha256": "0" * 64}, "SHA-256/size mismatch"),
            ({"file_size": 1}, "SHA-256/size mismatch"),
            ({"bronze_object": "s3a://other/files/aod550"}, "outside its declared Bronze batch"),
        ):
            with self.subTest(override=override), self.assertRaisesRegex(cams.DataQualityError, error):
                self.run_transform(messages(), metadata_override=override)

    def test_valid_time_preserves_utc_instant_and_checks_reference_and_step(self):
        source = messages()["co"][0]
        self.assertEqual(cams.valid_time(source).isoformat(), "2003-01-01T07:00:00+07:00")
        for key, value in (("step", 3), ("dataType", "fc"), ("dataTime", 300),
                           ("validityTime", 100)):
            with self.subTest(key=key), self.assertRaises(cams.DataQualityError):
                cams.valid_time(dict(source, **{key: value}))

    def test_rejects_old_fourteen_file_batch(self):
        with self.assertRaisesRegex(cams.DataQualityError, "requires 20 GRIB files, got 14"):
            self.run_transform(messages(), file_limit=14)

    def test_rejects_model_field_at_wrong_level(self):
        source = messages()
        source["co"][0]["level"] = 59
        with self.assertRaisesRegex(cams.DataQualityError, "requires hybrid model level 60"):
            self.run_transform(source)

    def test_rejects_unexpected_parameter(self):
        source = messages()
        source["co"][0]["shortName"] = "tcco"
        with self.assertRaisesRegex(cams.DataQualityError, "unexpected GRIB paramId/shortName"):
            self.run_transform(source)


if __name__ == "__main__":
    unittest.main()
