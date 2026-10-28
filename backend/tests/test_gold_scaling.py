from datetime import datetime,timedelta,timezone
import json
import unittest
from app.repositories.gold.history import GoldHistoryRepository
from app.repositories.gold.serving import GoldServingRepository,instant
from app.repositories.gold.history_pages import window


def entries(n,days=1):
    start=datetime(2025,1,1,17,tzinfo=timezone.utc)
    return [dict(start=(start+timedelta(days=i*days)).isoformat(),end=(start+timedelta(days=(i+1)*days)).isoformat(),
        release_id='r'+str(i),compatibility_id='v1',method_version='vn1',snapshots={'mart_air_quality_hourly':100+i,'mart_air_quality_daily':200+i,'mart_source_quality_daily':300+i},
        series=[dict(series_id='s',source_system='test',applicability_profile='area_estimate')]) for i in range(n)]


class Client:
    def __init__(self,segments):self.segments=segments;self.sql=[]
    def query(self,sql):
        self.sql.append(sql)
        if 'gold_timeline' in sql:return [dict(timeline_id='fixed-view',manifest_json=json.dumps(dict(version=1,segments=self.segments)))]
        return []


class ScalingTests(unittest.TestCase):
    def test_hourly_1200_segments_are_bounded_and_pagination_pins_timeline(self):
        client=Client(entries(1200,7));repo=GoldHistoryRepository(GoldServingRepository(client))
        cursor=None;pages=0
        while True:
            result=repo.air_quality(cursor=cursor);cursor=result['next_cursor'];pages+=1
            if not cursor:break
            self.assertLess(pages,100)
        sql=[s for s in client.sql if 'FOR VERSION AS OF' in s]
        self.assertEqual(sum(s.count('FOR VERSION AS OF') for s in sql),1200)
        self.assertLessEqual(max(s.count('FOR VERSION AS OF') for s in sql),16)
        self.assertEqual(sum('gold_timeline_current' in s for s in client.sql),1)
        self.assertEqual(pages,75)
    def test_monthly_batches_do_not_split_months(self):
        segments=entries(90);lower=instant(segments[0]['start']);upper=instant(segments[-1]['end'])
        page=0;seen=[]
        while True:
            selected,lo,hi,next_page=window(segments,'monthly',lower,upper,page)
            self.assertLessEqual(len(selected),32)
            seen.append((lo,hi))
            if next_page is None:break
            page=next_page
        self.assertEqual(seen[0][0],lower);self.assertEqual(seen[-1][1],upper)
        for a,b in zip(seen,seen[1:]):self.assertEqual(a[1],b[0])
    def test_small_legacy_cursor_remains_readable(self):
        import base64,hashlib
        client=Client(entries(3));repo=GoldHistoryRepository(GoldServingRepository(client))
        signature=hashlib.sha256(json.dumps(['hourly','None','None','pm25',None,None,None,None,None,None],sort_keys=True).encode()).hexdigest()
        cursor=base64.urlsafe_b64encode(json.dumps(dict(timeline_id='fixed-view',signature=signature,offset=2)).encode()).decode()
        repo.air_quality(cursor=cursor)
        self.assertIn('OFFSET 2',client.sql[-1])
    def test_v2_reader_rejects_missing_reference(self):
        from app.repositories.gold.manifest import decode
        with self.assertRaises(KeyError):decode(dict(version=2,series_catalog={},segments=[dict(series_ref='missing')]))
    def test_aggregate_scans_bounded_and_no_daily_rows_downloaded(self):
        client=Client(entries(100,7));repo=GoldHistoryRepository(GoldServingRepository(client))
        repo.aqi_distribution();repo.quality()
        for sql in client.sql:
            if 'FOR VERSION AS OF' in sql:self.assertLessEqual(sql.count('FOR VERSION AS OF'),32)
        self.assertTrue(any('count(*) n' in sql for sql in client.sql))

    def test_quality_batches_preserve_unknown_collection_and_missing_types(self):
        class QualityClient(Client):
            def query(self,sql):
                if 'gold_timeline' in sql:return super().query(sql)
                self.sql.append(sql)
                return [dict(source='test',pollutant='so2',valid_measurements=20,
                    expected_hours=24,observed_slots=23,missing_hours=4,invalid_measurements=2,
                    collection_attempts=None,failed_ingestions=None,latest_observation_time=None)]
        client=QualityClient(entries(33));repo=GoldHistoryRepository(GoldServingRepository(client))
        result=repo.quality()['rows'][0]
        self.assertEqual(result['expected_hours'],48)
        self.assertEqual(result['absent_slots'],2)
        self.assertEqual(result['missing_value_slots'],2)
        self.assertEqual(result['invalid_measurements'],4)
        self.assertIsNone(result['collection_attempts']);self.assertIsNone(result['failed_ingestions'])
