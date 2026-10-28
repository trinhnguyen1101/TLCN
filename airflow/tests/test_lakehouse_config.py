"""Unit tests for Airflow configuration without requiring Airflow itself."""

from datetime import datetime, timezone
import unittest

from lakehouse_config import (
    daily_window,
    validate_landing_conf,
    validate_missing_hour_limit,
)


class DailyWindowTests(unittest.TestCase):
    def test_airflow_interval_is_normalized_to_vietnam_day(self):
        result = daily_window(datetime(2026, 10, 28, 17, 30, tzinfo=timezone.utc))
        self.assertEqual(result["business_date"], "2026-10-28")
        self.assertEqual(result["window_start_utc"], "2026-10-27T17:00:00Z")
        self.assertEqual(result["window_end_utc"], "2026-10-28T17:00:00Z")
        self.assertEqual(result["ingestion_date"], "2026-10-29")
        self.assertIn("20261027T170000Z", result["waqi_batch_id"])


class LandingConfigTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
