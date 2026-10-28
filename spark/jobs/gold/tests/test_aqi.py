import hashlib
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import unittest
from spark.jobs.gold.aqi.engine import *
from spark.jobs.gold.aqi.reference import BREAKPOINTS, INDICES, REFERENCE_SHA256


def reading(value, **changes):
    row = dict(value=value, unit="ug/m3", temporal_support="hourly_mean",
               source_resolution_minutes=60, quality_status="ok", vertical_support="surface",
               spatial_representation="station", reference_eligible=True)
    row.update(changes)
    return row


class AQITest(unittest.TestCase):
    def test_reference_checksum(self):
        content = Path("lakehouse/gold/references/1459-2019.pdf").read_bytes()
        self.assertEqual(hashlib.sha256(content).hexdigest(), REFERENCE_SHA256)

    def test_all_breakpoints_and_terminal_cutoff(self):
        for p, points in BREAKPOINTS.items():
            pollutant, basis = ("o3", "max8h") if p == "o3_8h" else (p, "mean1h")
            for c, expected in zip(points, INDICES):
                with self.subTest(p=p, c=c):
                    self.assertEqual(subindex(pollutant, c, basis)["sub_index"], expected)
            expected = None if p == "o3_8h" else 500
            self.assertEqual(subindex(pollutant, points[-1] + 100, basis)["sub_index"], expected)

    def test_half_up_and_invalid(self):
        self.assertEqual(round_aqi(42.5), 43)
        for v in [None, -1, float("nan"), float("inf"), True]:
            self.assertIsNone(subindex("pm25", v)["sub_index"])
        self.assertEqual(subindex("pm25", 0)["sub_index"], 0)
        with self.assertRaises(ValueError):
            subindex("pm1", 10)

    def test_pdf_nowcast_example_page8(self):
        values = [26.9,24.7,20.5,23.5,19.5,16.5,19,16.5,20.3,22.4,19.6,20.6]
        value, n, weight, reason = nowcast(values[::-1])
        self.assertAlmostEqual(value, 20.3, delta=0.05)
        self.assertAlmostEqual(weight, 16.5/26.9)
        self.assertEqual(n, 12)
        self.assertIsNone(reason)

    def test_pdf_hourly_example_page8(self):
        cs = [subindex("o3", 136.1), subindex("no2", 118.7), subindex("pm25", 20.3)]
        self.assertEqual([c["sub_index"] for c in cs], [43,59,41])
        # PDF prints 60 for NO2=118.7 (formula gives 59.35). Preserve
        # half-up implementation; document original worked-example discrepancy.
        self.assertEqual(aggregate_indices(cs)["aqi"], 59)

    def test_pdf_daily_example_page9(self):
        cs = [subindex("o3",89.3,"max8h"), subindex("o3",114.6,"max1h"),
              subindex("no2",130.8,"max1h"), subindex("pm25",55.7,"mean24h")]
        self.assertEqual([c["sub_index"] for c in cs], [45,36,65,110])
        self.assertEqual(aggregate_indices(cs)["aqi"],110)

    def test_nowcast_half_branch_missing_ages(self):
        value, _, w, _ = nowcast([100,50]+[None]*10)
        self.assertEqual(w,0.5)
        self.assertEqual(value,62.5)  # exact PDF unnormalized branch
        a = nowcast([100,None,50]+[None]*9)[0]
        self.assertEqual(a,56.25)
        self.assertIsNone(nowcast([100,None,None]+[50]*9)[0])
        self.assertEqual(nowcast([0]*12)[0],0)
        self.assertEqual(nowcast([10]*12)[0],10)
        with self.assertRaises(ValueError):
            nowcast([10]*11)

    def test_gaps_are_time_windows(self):
        h = datetime(2026,1,1,tzinfo=UTC)
        rows = {(h-timedelta(hours=i*3),"pm25"):reading(10) for i in range(12)}
        components, overall = hourly(h, rows, "station_reference")
        self.assertIsNone(overall["aqi"])
        self.assertEqual(components[0]["input_count"],4)

    def test_3h_and_snapshots_never_reference(self):
        h = datetime(2026,1,1,tzinfo=UTC)
        for changes in [dict(temporal_support="instantaneous",source_resolution_minutes=180),
                        dict(temporal_support="instantaneous",source_resolution_minutes=60),
                        dict(temporal_support="provider_snapshot"), dict(unit="mg/m3"),
                        dict(quality_status="invalid"),dict(reference_eligible=False)]:
            rows = {(h-HOUR*i,"pm25"):reading(30,**changes) for i in range(12)}
            self.assertIsNone(hourly(h,rows,"station_reference")[1]["aqi"])
            if changes.get("reference_eligible") is False:
                self.assertIsNotNone(hourly(h,rows,"area_estimate")[1]["aqi"])

    def test_pm_required_ties_and_colors(self):
        self.assertIsNone(aggregate_indices([subindex("co",10000)])["aqi"])
        result=aggregate_indices([subindex("co",10000),subindex("pm25",25)])
        self.assertEqual(result["dominant_pollutants"],["co","pm25"])
        self.assertEqual(result["color"],"#00E400")
        self.assertEqual(category(500)[2],"#7E0023")

    def test_daily_complete_local_boundary_and_ozone_midnight(self):
        day=date(2026,1,2)
        start,end=local_day_bounds(day)
        self.assertEqual(start,datetime(2026,1,1,17,tzinfo=UTC))
        rows={(start+HOUR*i,p):reading(25 if p=="pm25" else 10)
              for i in range(-11,24) for p in POLLUTANTS}
        cs, overall=daily(day,rows,"station_reference")
        self.assertEqual(overall["aqi"],50)
        self.assertEqual([c["input_count"] for c in cs],[24]*7)
        rows[(start-HOUR,"o3")]=reading(90)
        self.assertEqual(rolling8(start,rows,"station_reference"),(20,8))
        del rows[(start,"pm25")]
        self.assertIsNone(daily(day,rows,"station_reference")[0][0]["sub_index"])
        # Other eligible PM still permits overall.
        self.assertIsNotNone(daily(day,rows,"station_reference")[1]["aqi"])
        rows={k:v for k,v in rows.items() if k[1]!="pm10"}
        self.assertIsNone(daily(day,rows,"station_reference")[1]["aqi"])

    def test_pdf_o3_8h_max_page7(self):
        # End labels previous 18..23 then target 00..24. Convert end to start.
        values=[15.7,14.2,17.7,18.9,19.3,15.7,19.7,22.6,27.1,29.0,31.9,
                25.3,34.7,35.2,41.6,45.7,49.2,55.8,69.6,78.3,91.5,97.7,
                81.2,71.8,43.5,34.3,21.5,20.5,19.4,20.4,21.3]
        start,_=local_day_bounds(date(2026,1,2))
        rows={(start+HOUR*(i-7),"o3"):reading(v) for i,v in enumerate(values)}
        windows=[rolling8(start+HOUR*i,rows,"station_reference")[0] for i in range(24)]
        self.assertAlmostEqual(max(windows),74.4,delta=0.05)

    def test_version_and_invalidation(self):
        self.assertEqual(METHOD_VERSION,"vn-aqi-1459-2019-project-v1")
        h=datetime(2026,1,1,tzinfo=UTC)
        self.assertEqual(affected_hours(h)["pm_nowcast_end_exclusive"],h+12*HOUR)
        with self.assertRaises(ValueError):
            hourly(h.replace(tzinfo=None),{})


if __name__ == "__main__":
    unittest.main()
