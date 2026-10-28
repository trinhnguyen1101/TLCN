import json
import unittest
from app.repositories.gold.serving import GoldServingRepository
from app.repositories.gold.history import GoldHistoryRepository


def segment(start,end,release='r1',lane='v1'):
    return dict(start=start,end=end,release_id=release,compatibility_id=lane,method_version='vn1',
                snapshots={'mart_air_quality_hourly':123,'mart_air_quality_daily':456},
                series=[dict(series_id='s1',source_system='cams',applicability_profile='area_estimate')])

class Client:
    def __init__(self,segments):self.sql=[];self.segments=segments
    def query(self,sql):
        self.sql.append(sql)
        if 'gold_timeline' in sql:return [dict(timeline_id='t1',manifest_json=json.dumps(dict(version=1,segments=self.segments)))]
        return []

class HistoryTests(unittest.TestCase):
    def test_three_chunks_snapshot_pin_and_missing(self):
        segments=[segment('2025-12-29T17:00:00Z','2025-12-30T17:00:00Z'),
                  segment('2025-12-31T17:00:00Z','2026-01-01T17:00:00Z','r3')]
        client=Client(segments);repo=GoldHistoryRepository(GoldServingRepository(client))
        result=repo.air_quality(start='2025-12-29T17:00:00Z',end='2026-01-01T17:00:00Z')
        self.assertEqual(len(result['missing_scopes']),1)
        self.assertEqual(result['published_release_ids'],['r1','r3'])
        self.assertEqual(sum('gold_timeline_current' in sql for sql in client.sql),1)
        self.assertEqual(client.sql[-1].count('FOR VERSION AS OF 123'),2)
        self.assertNotIn('gold_current_release',client.sql[-1])
    def test_monthly_uses_daily_sufficient_statistics(self):
        client=Client([segment('2025-12-29T17:00:00Z','2026-01-01T17:00:00Z')])
        GoldHistoryRepository(GoldServingRepository(client)).air_quality('monthly')
        self.assertIn('sum(concentration_sum)/nullif(sum(valid_hours),0)',client.sql[-1])
        self.assertIn('mart_air_quality_daily FOR VERSION AS OF 456',client.sql[-1])
        self.assertNotIn('avg(aqi)',client.sql[-1].lower())
        self.assertIn('count_if(valid_hours=expected_hours) valid_days',client.sql[-1])
    def test_incompatible_method_geometry_rejected(self):
        client=Client([segment('2025-12-29T17:00:00Z','2026-01-01T17:00:00Z'),segment('2025-12-29T17:00:00Z','2026-01-01T17:00:00Z','r2','geometry2')])
        repo=GoldHistoryRepository(GoldServingRepository(client))
        with self.assertRaises(ValueError):repo.air_quality()
        result=repo.air_quality(compatibility_id='v1')
        self.assertEqual(result['published_release_ids'],['r1'])
    def test_overlapping_manifest_rejected_before_query(self):
        from app.repositories.base import DataSourceUnavailable
        client=Client([segment('2025-12-29T17:00:00Z','2026-01-01T17:00:00Z')]*2)
        with self.assertRaises(DataSourceUnavailable):GoldHistoryRepository(GoldServingRepository(client)).resolve()

    def test_source_selection_default_bounds_exclude_other_sources(self):
        old=segment('2020-01-01T17:00:00Z','2020-01-02T17:00:00Z')
        newer=segment('2026-01-01T17:00:00Z','2026-01-02T17:00:00Z','r2','other')
        newer['series'][0]['source_system']='another_source'
        client=Client([old,newer])
        result=GoldHistoryRepository(GoldServingRepository(client)).air_quality(source='cams')
        self.assertEqual(result['scope_end_utc'],'2020-01-02T17:00:00+00:00')
        self.assertEqual(result['missing_scopes'],[])

    def test_invalid_daily_bounds_rejected_even_outside_published_scope(self):
        client=Client([segment('2025-12-29T17:00:00Z','2026-01-01T17:00:00Z')])
        repo=GoldHistoryRepository(GoldServingRepository(client))
        for method in [lambda:repo.air_quality('daily',start='2020-01-01T00:00:00Z',end='2020-01-02T00:00:00Z'),
                       lambda:repo.aqi_distribution(start='2020-01-01T00:00:00Z',end='2020-01-02T00:00:00Z'),
                       lambda:repo.quality(start='2020-01-01T00:00:00Z',end='2020-01-02T00:00:00Z')]:
            with self.assertRaises(ValueError):method()

    def test_method_selection_is_explicit_and_withdrawal_keeps_source_identity(self):
        old=segment('2025-12-29T17:00:00Z','2026-01-01T17:00:00Z')
        changed=segment('2025-12-29T17:00:00Z','2026-01-01T17:00:00Z','r2','method2')
        changed['method_version']='vn2'
        client=Client([old,changed]);repo=GoldHistoryRepository(GoldServingRepository(client))
        result=repo.air_quality(method_version='vn1')
        self.assertEqual(result['published_release_ids'],['r1'])
        old['withdrawn']=True
        old.pop('release_id');old.pop('snapshots')
        result=repo.air_quality(source='cams',method_version='vn1')
        self.assertEqual(result['rows'],[])
        self.assertEqual(result['missing_scopes'][0]['reason'],'withdrawn_scope')
