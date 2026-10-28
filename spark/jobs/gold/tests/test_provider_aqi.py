from datetime import datetime, timezone
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from provider_aqi import overall_fact, pollutant_fact


class ProviderAqiFactsTest(unittest.TestCase):
    def test_waqi_keeps_actual_observation_clock_and_station_profile(self):
        observed = datetime(2026, 10, 28, 3, 17, tzinfo=timezone.utc)
        row = overall_fact(source="waqi", release_id="r", series_id="s",
            hour_start=observed, provider_aqi=71, observed_at=observed,
            scheduled_at=None, collected_at=datetime(2026, 10, 28, 4, tzinfo=timezone.utc),
            observation_time_kind="provider_observation", dominant_pollutants=["pm25"],
            input_run_id="run", input_snapshots={"silver": 1})
        self.assertEqual(row["hour_start_utc"].hour, 3)
        self.assertEqual(row["observed_at_utc"], observed)
        self.assertEqual(row["applicability_profile"], "station_reference")
        self.assertEqual(row["aqi_origin"], "provider")

    def test_ninjas_never_fabricates_actual_observation_clock(self):
        slot = datetime(2026, 10, 28, 4, tzinfo=timezone.utc)
        row = pollutant_fact(source="api_ninjas", release_id="r", series_id="s",
            pollutant="pm25", hour_start=slot, provider_sub_index=42,
            missing_reason=None, observed_at=None, scheduled_at=slot,
            collected_at=datetime(2026, 10, 28, 4, 2, tzinfo=timezone.utc),
            observation_time_kind="scheduled_provider_snapshot", input_run_id="run",
            input_snapshots={"silver": 1})
        self.assertIsNone(row["observed_at_utc"])
        self.assertEqual(row["scheduled_at_utc"], slot)
        self.assertEqual(row["provider_sub_index"], 42.0)
        self.assertEqual(row["basis"], "provider_snapshot_slot")

    def test_fractional_provider_subindex_is_preserved_without_rounding(self):
        slot = datetime(2026, 10, 28, 4, tzinfo=timezone.utc)
        row = pollutant_fact(source="waqi", release_id="r", series_id="s",
            pollutant="o3", hour_start=slot, provider_sub_index=12.5,
            missing_reason=None, observed_at=slot, scheduled_at=None, collected_at=slot,
            observation_time_kind="provider_observation", input_run_id="run",
            input_snapshots={})
        self.assertIsNone(row["sub_index"])
        self.assertEqual(row["provider_sub_index"], 12.5)


if __name__ == "__main__":
    unittest.main()
