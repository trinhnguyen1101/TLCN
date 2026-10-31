"""Unit tests for Airflow configuration without requiring Airflow itself."""

from datetime import date, datetime, timezone
import ast
from pathlib import Path
import unittest

from lakehouse_config import (
    daily_window,
    validate_landing_all_conf,
    validate_landing_conf,
    validate_missing_hour_limit,
    resolve_landing_full_conf,
)


class DailyWindowTests(unittest.TestCase):
    def test_airflow_interval_is_normalized_to_vietnam_day(self):
        result = daily_window(datetime(2026, 10, 28, 17, 30, tzinfo=timezone.utc))
        self.assertEqual(result["business_date"], "2026-10-28")
        self.assertEqual(result["window_start_utc"], "2026-10-27T17:00:00Z")
        self.assertEqual(result["window_end_utc"], "2026-10-28T17:00:00Z")
        self.assertEqual(result["ingestion_date"], "2026-10-29")
        self.assertIn("20261027T170000Z", result["waqi_batch_id"])
        prefixes = result["rclone_hour_prefixes"].split(",")
        self.assertEqual(len(prefixes), 24)
        self.assertEqual(prefixes[0], "2026/10/27/17")
        self.assertEqual(prefixes[-1], "2026/10/28/16")


class LandingConfigTests(unittest.TestCase):
    def test_full_landing_run_builds_five_isolated_batches(self):
        result = validate_landing_all_conf({
            "batch_id": "landing-full-20261029",
            "ingestion_date": "2026-10-29",
            "publish_gold": False,
        })
        self.assertEqual(len(result["datasets"]), 5)
        self.assertEqual(
            result["datasets"]["cams"]["batch_id"],
            "landing-full-20261029-cams",
        )
        self.assertEqual(
            result["datasets"]["reference_admin"]["dataset"],
            "reference/vietnam_administrative_divisions",
        )
        self.assertEqual(len({
            item["bronze_path"] for item in result["datasets"].values()
        }), 5)

    def test_full_landing_gold_requires_cams_scope(self):
        with self.assertRaisesRegex(ValueError, "requires a gold object"):
            validate_landing_all_conf({
                "batch_id": "landing-full-20261029",
                "ingestion_date": "2026-10-29",
                "publish_gold": True,
            })

    def test_full_landing_gold_splits_the_entire_scope_for_airflow_mapping(self):
        result = validate_landing_all_conf({
            "batch_id": "landing-full-20261029",
            "ingestion_date": "2026-10-29",
            "publish_gold": True,
            "gold": {
                "dataset_id": "abc123",
                "start_date": "2003-01-01",
                "end_date": "2026-01-01",
                "chunk_days": 14,
                "allow_validation": False,
            },
        })
        chunks = result["gold_chunks"]
        self.assertEqual(chunks[0], {
            "start_date": "2003-01-01", "end_date": "2003-01-15"
        })
        self.assertEqual(chunks[-1]["end_date"], "2026-01-01")
        self.assertLessEqual(len(chunks), 1024)
        for chunk in chunks:
            start = date.fromisoformat(chunk["start_date"])
            end = date.fromisoformat(chunk["end_date"])
            self.assertLessEqual((end - start).days, 14)

    def test_full_landing_gold_rejects_too_many_mapped_tasks(self):
        with self.assertRaisesRegex(ValueError, "increase gold.chunk_days"):
            validate_landing_all_conf({
                "batch_id": "landing-full-20261029",
                "ingestion_date": "2026-10-29",
                "publish_gold": True,
                "gold": {
                    "dataset_id": "abc123",
                    "start_date": "2003-01-01",
                    "end_date": "2026-01-01",
                    "chunk_days": 1,
                    "allow_validation": False,
                },
            })

    def test_full_landing_gold_rejects_invalid_chunk_days(self):
        with self.assertRaisesRegex(ValueError, "between 1 and 31"):
            validate_landing_all_conf({
                "batch_id": "landing-full-20261029",
                "ingestion_date": "2026-10-29",
                "publish_gold": True,
                "gold": {
                    "dataset_id": "abc123",
                    "start_date": "2026-01-01",
                    "end_date": "2026-01-02",
                    "chunk_days": 32,
                    "allow_validation": False,
                },
            })

    def test_historical_waqi_defaults_to_silver_only(self):
        result = validate_landing_conf(
            {
                "dataset": "waqi/historical",
                "batch_id": "waqi-history-1",
                "ingestion_date": "2026-10-28",
            }
        )
        self.assertEqual(result["gold_kind"], "none")
        self.assertEqual(
            result["bronze_path"],
            "s3a://lakehouse/bronze/waqi/historical/ingestion_date=2026-10-28/batch_id=waqi-history-1",
        )

    def test_admin_cannot_be_forced_into_gold(self):
        with self.assertRaisesRegex(ValueError, "no Gold adapter"):
            validate_landing_conf(
                {
                    "dataset": "reference/vietnam_administrative_divisions",
                    "batch_id": "admin-1",
                    "ingestion_date": "2026-10-28",
                    "publish_gold": True,
                }
            )

    def test_cams_gold_requires_scope(self):
        result = validate_landing_conf(
            {
                "dataset": "CAMS/EAC4",
                "batch_id": "cams-1",
                "ingestion_date": "2026-10-28",
                "publish_gold": True,
                "gold": {
                    "dataset_id": "abc123",
                    "start_date": "2026-01-01",
                    "end_date": "2026-01-03",
                    "allow_validation": False,
                },
            }
        )
        self.assertEqual(result["gold_kind"], "cams")


class SupabaseCoverageConfigTests(unittest.TestCase):
    def test_one_missing_hour_is_allowed_by_default_policy(self):
        self.assertEqual(validate_missing_hour_limit("1"), 1)

    def test_invalid_missing_hour_limit_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "between 0 and 23"):
            validate_missing_hour_limit("24")


class FullLandingTriggerTests(unittest.TestCase):
    def setUp(self):
        # Read the actual DAG defaults without importing Airflow or executing a DAG.
        path = Path(__file__).resolve().parents[1] / "dags/landing_batch_to_gold.py"
        module = ast.parse(path.read_text())
        self.defaults = next(
            ast.literal_eval(node.value) for node in module.body
            if isinstance(node, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "DEFAULT_FULL_RUN_CONF" for t in node.targets)
        )
        self.clock = datetime(2026, 10, 31, 0, 15, tzinfo=timezone.utc)

    def resolve(self, conf=None, run_id="manual__2026-10-31T00:15:00+00:00"):
        return resolve_landing_full_conf(
            conf, defaults=self.defaults, run_id=run_id, logical_date=self.clock
        )

    def test_empty_ui_trigger_runs_all_sources_through_hourly_gold(self):
        for conf in (None, {}):
            result = self.resolve(conf)
            self.assertTrue(result["publish_gold"])
            self.assertEqual(len(result["datasets"]), 5)
            self.assertEqual(result["gold_kind"], "cams")
            self.assertEqual(result["gold_dataset_id"], "5ca22d69be491cfe59e338e641c6b2238fbfb9555358ae440e0ce1e05c4c5f5f")
            self.assertEqual(result["gold_chunks"][0]["start_date"], "2003-01-01")
            self.assertEqual(result["gold_chunks"][-1]["end_date"], "2026-01-02")
            self.assertLessEqual(len(result["gold_chunks"]), 1024)
            self.assertEqual(result["gold_chunk_days"], 14)

    def test_retry_reuses_identity_but_new_run_gets_new_batches(self):
        first = self.resolve()
        self.assertEqual(first, self.resolve())
        self.assertNotEqual(first["batch_id"], self.resolve(run_id="another-run")["batch_id"])
        self.assertEqual(first["ingestion_date"], "2026-10-31")

    def test_overrides_keep_defaults_and_can_disable_gold(self):
        scoped = self.resolve({"gold": {"end_date": "2003-01-02"}})
        self.assertEqual(len(scoped["gold_chunks"]), 1)
        self.assertEqual(self.defaults["gold"]["end_date"], "2026-01-02")
        disabled = self.resolve({"publish_gold": False, "batch_id": "resume-existing", "ingestion_date": "2026-10-30"})
        self.assertFalse(disabled["publish_gold"])
        self.assertEqual(disabled["batch_id"], "resume-existing")
        self.assertEqual(disabled["ingestion_date"], "2026-10-30")


if __name__ == "__main__":
    unittest.main()
