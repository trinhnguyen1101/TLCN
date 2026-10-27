"""Pure transform tests; Spark MERGE is covered by the existing Silver framework."""

import importlib.util
import sys
import types
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

MODULE = Path(__file__).resolve().parents[1] / "supabase_bronze_to_silver.py"
if "common" not in sys.modules:
    fake = types.ModuleType("common")
    fake.TABLE_PREFIX = "nessie.silver"
    fake.DataQualityError = type("DataQualityError", (RuntimeError,), {})
    for name in ("bootstrap_schema", "create_spark", "finish_run", "load_bronze_batch",
                 "merge_dataframe", "metadata_rows", "register_dataset", "sha256_json",
                 "start_run", "utc_now", "write_quality_issues"):
        setattr(fake, name, lambda *args, **kwargs: None)
    sys.modules["common"] = fake
spec = importlib.util.spec_from_file_location("supabase_transform_under_test", MODULE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class SupabaseTransformTest(unittest.TestCase):
    def test_manifest_links_raw_and_skips_non_json_failed_response(self):
        run_id = "00000000-0000-4000-8000-000000000001"
        parent = "2026/10/26/04/" + run_id
        manifest_path = parent + "/manifest.json"
        raw_path = parent + "/ha-noi.raw.json"
        manifest = {"schema_version": 1, "source": "api_ninjas", "collection_run_id": run_id,
                    "scheduled_hour_utc": "2026-10-26T04:00:00Z", "status": "partial",
                    "expected_records": 1, "records": [{"outcome": "failed",
                    "raw_object_path": "api_ninjas/" + raw_path, "payload_sha256": "a" * 64}]}
        files = [types.SimpleNamespace(source_file=manifest_path, file_sha256="b" * 64,
                                       file_size=100, bronze_object="s3a://test/" + manifest_path),
                 types.SimpleNamespace(source_file=raw_path, file_sha256="a" * 64,
                                       file_size=10, bronze_object="s3a://test/" + raw_path)]
        batch = types.SimpleNamespace(source="api_ninjas")
        with patch.object(module, "metadata_rows", return_value=files), \
             patch.object(module, "read_file", side_effect=[manifest, b"HTTP 500"] ) as read:
            records, issues, input_targets = module.source_records(None, batch)
        self.assertEqual(records, [])
        self.assertEqual(len(issues), 1)
        self.assertEqual(input_targets, 1)
        self.assertFalse(read.call_args.kwargs["parse_json"])

    def test_aqi_rejects_fraction_negative_nan_and_overflow(self):
        self.assertEqual(module.number(0, integer=True), 0)
        for value in (-1, 1.5, float("nan"), float("inf"), 2147483648):
            with self.subTest(value=value), self.assertRaises(module.DataQualityError):
                module.number(value, integer=True)

    def test_conflicting_retry_is_rejected(self):
        rows = [{"station": "s", "time": "t", "aqi": 10},
                {"station": "s", "time": "t", "aqi": 10}]
        self.assertEqual(module.distinct(rows, ["station", "time"], ["aqi"], "waqi")[1], 1)
        rows[1]["aqi"] = 11
        with self.assertRaises(module.DataQualityError):
            module.distinct(rows, ["station", "time"], ["aqi"], "waqi")

    def test_ninjas_keeps_aqi_separate_and_unconfirmed_unit_null(self):
        run = types.SimpleNamespace(dataset_id="dataset", run_id="attempt")
        meta = types.SimpleNamespace(source_file="2026/10/26/04/r/ha-noi.raw.json", file_sha256="0" * 64)
        entry = {"location_id": "loc", "location_key": "ha-noi", "province_name": "Hà Nội",
                 "query_city": "Hanoi", "latitude": 21.0, "longitude": 105.0,
                 "collected_at_utc": "2026-10-26T04:01:00Z", "validation_status": "valid",
                 "_manifest_source_file": "2026/10/26/04/r/manifest.json", "_manifest_sha256": "1" * 64}
        raw = {"overall_aqi": 20, "PM2.5": {"aqi": 30, "concentration": 6.5}}
        hour = datetime(2026, 10, 26, 4, tzinfo=timezone.utc)
        with patch.object(module, "province_lookup", return_value={"loc": ("admin", "01", "province_name_and_boundary", 1.0, 0.0)}), \
             patch.object(module, "sha256_json", side_effect=lambda *args: ":".join(map(str, args))):
            specs, output = module.ninjas(None, [(hour, "run", entry, raw, meta)], run)
        measurement = next(rows for table, rows, *_ in specs if table.endswith("measurement"))
        self.assertEqual(output, 1)
        self.assertEqual(len(measurement), 12)
        aqi = next(r for r in measurement if r["value_native"] == 30)
        concentration = next(r for r in measurement if r["value_native"] == 6.5)
        self.assertNotEqual(aqi["variable_id"], concentration["variable_id"])
        self.assertIsNone(concentration["value_standard"])
        self.assertEqual(aqi["value_standard"], 30)
        self.assertIsInstance(aqi["value_native"], float)
        self.assertIsInstance(aqi["value_standard"], float)

    def test_waqi_uses_observation_time_and_keeps_missing_optional_value(self):
        run = types.SimpleNamespace(dataset_id="dataset", run_id="attempt")
        meta = types.SimpleNamespace(source_file="2026/10/26/04/r/123.raw.json", file_sha256="0" * 64)
        entry = {"requested_source_uid": "123", "collected_at_utc": "2026-10-26T04:20:00Z",
                 "validation_status": "partial", "validation_errors": {"pm25": "out_of_range"}}
        raw = {"status": "ok", "data": {"idx": 123, "aqi": 42,
               "time": {"iso": "2026-10-26T10:00:00+07:00", "tz": "+07:00"},
               "city": {"name": "Station", "geo": [21.0, 105.0]},
               "iaqi": {"pm25": {"v": -100}, "pm10": {"v": 0}}}}
        with patch.object(module, "sha256_json", side_effect=lambda *args: ":".join(map(str, args))):
            specs, output = module.waqi(None, [(datetime(2026, 10, 26, 4, tzinfo=timezone.utc),
                                               "collection", entry, raw, meta)], run)
        observation = next(rows[0] for table, rows, *_ in specs if table == "waqi_hourly_observation")
        measurements = next(rows for table, rows, *_ in specs if table == "waqi_hourly_measurement")
        self.assertEqual(output, 1)
        self.assertEqual(observation["observation_time_utc"].hour, 3)
        self.assertEqual(observation["collected_at_utc"].hour, 4)
        self.assertTrue(any(r["value_native"] is None and r["missing_reason"] == "provider_invalid"
                            for r in measurements))
        self.assertTrue(any(r["value_native"] == 0 for r in measurements))


if __name__ == "__main__":
    unittest.main()
