from datetime import datetime,timezone,timedelta
import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from incremental import invalidation_scope


class ScopeTest(unittest.TestCase):
    def test_late_hour_invalidates_next_local_day_and_month(self):
        h=datetime(2026,1,31,16,tzinfo=timezone.utc)  # Jan31 23:00 VN
        result=invalidation_scope([h])
        self.assertEqual(result['start_date'],'2026-01-31')
        self.assertEqual(result['end_date'],'2026-02-02')
        self.assertEqual(result['pm_end_exclusive'],h+timedelta(hours=12))
        self.assertEqual(result['o3_end_exclusive'],h+timedelta(hours=8))
        self.assertEqual(result['required_input_start_utc'],datetime(2026,1,30,6,tzinfo=timezone.utc))

    def test_24_hour_spine_including_leap_day(self):
        from aqi.engine import local_day_bounds,HOUR
        from datetime import date
        start,end=local_day_bounds(date(2024,2,29))
        self.assertEqual(int((end-start)/HOUR),24)
        self.assertEqual(end.date().isoformat(),'2024-02-29')


class SpatialTest(unittest.TestCase):
    def test_intersection_denominator_and_partial_domain(self):
        from shapely.geometry import box
        from spatial import weights,area
        geometry=box(0,0,2,1)
        points=[(0,0.5,0.5),(1,0.5,1.5)]
        w=weights(geometry,points,1,1)
        self.assertAlmostEqual(sum(r[3] for r in w),1,places=8)
        self.assertAlmostEqual(w[0][3],.5,places=8)
        partial=weights(geometry,points[:1],1,1)
        self.assertAlmostEqual(sum(r[3] for r in partial),.5,places=8)
        # Parent union already containing child keeps the same area.
        child=box(0,0,1,1)
        self.assertAlmostEqual(area(geometry.union(child)),area(geometry),places=3)

if __name__=='__main__':unittest.main()
