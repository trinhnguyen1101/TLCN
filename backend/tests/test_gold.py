import json
from datetime import datetime,timezone
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from app.core.config import Settings
from app.main import create_app
from app.repositories.gold.serving import GoldServingRepository,literal,ident,instant
from app.repositories.base import DataSourceUnavailable


class EmptyDashboard:
    def get_dashboard(self,query=None):
        raise DataSourceUnavailable('configured source down')


class GoldTests(unittest.TestCase):
    def test_literals_and_identifiers(self):
        self.assertEqual(literal("a'b"),"'a''b'")
        with self.assertRaises(ValueError):
            ident('gold;drop')
        with self.assertRaises(ValueError):
            instant('2026-01-01T00:00:00')

    def test_manifest_resolved_once_and_snapshot_pinned(self):
        class Client:
            def __init__(self):self.sql=[]
            def query(self,sql):
                self.sql.append(sql)
                if 'gold_current_release' in sql:
                    return [dict(release_id='r1',scope_start_utc='2026-01-01T17:00:00Z',scope_end_utc='2026-01-02T17:00:00Z',
                                 output_snapshots_json=json.dumps({'mart_air_quality_hourly':123}))]
                return []
        client=Client()
        result=GoldServingRepository(client).air_quality()
        self.assertEqual(result['published_release_id'],'r1')
        self.assertEqual(sum('gold_current_release' in s for s in client.sql),1)
        self.assertIn('FOR VERSION AS OF 123',client.sql[1])
        self.assertIn("release_id='r1'",client.sql[1])

    def test_no_sample_fallback_and_api_parameter_validation(self):
        app=create_app(Settings(),EmptyDashboard())
        with TestClient(app) as client:
            with patch.object(app.state.gold_repository,'province_map',side_effect=DataSourceUnavailable('down')):
                self.assertEqual(client.get('/api/gold/map').status_code,503)
            self.assertEqual(client.get('/api/gold/map?pollutant=pm1').status_code,422)
            self.assertEqual(client.get('/api/gold/air-quality?limit=999999').status_code,422)

    def test_hourly_never_silently_uses_legacy_parquet(self):
        from pathlib import Path
        from app.repositories.parquet.dashboard import ParquetDashboardRepository
        from app.services.temporal import DashboardQuery, InvalidDashboardQuery
        with self.assertRaises(InvalidDashboardQuery):
            ParquetDashboardRepository(Path('/tmp/no-gold-fallback')).get_dashboard(DashboardQuery('hourly'))

    def test_compatibility_dashboard_rejects_mixed_time_semantics(self):
        from types import SimpleNamespace
        from app.repositories.gold.dashboard import GoldDashboardRepository
        release=dict(release_id='r',scope_start_utc='2026-01-01T17:00:00Z',scope_end_utc='2026-01-02T17:00:00Z')
        rows=[dict(source='cams',source_resolution_minutes=60,temporal_support='hourly_mean',
                   spatial_representation='area_estimate',applicability_profile='area_estimate',
                   aqi_method_version='v1',series_id='s1',location_id='l1'),
              dict(source='cams',source_resolution_minutes=180,temporal_support='instantaneous',
                   spatial_representation='area_estimate',applicability_profile='area_estimate',
                   aqi_method_version='v1',series_id='s2',location_id='l2')]
        serving=SimpleNamespace(resolve=lambda:release,air_quality=lambda *args,**kwargs:dict(rows=rows))
        from unittest.mock import MagicMock
        history=MagicMock()
        history.resolve.return_value={}
        history.select.return_value=([dict(release_id='r',compatibility_id='v1',start=release['scope_start_utc'],end=release['scope_end_utc'])],instant(release['scope_start_utc']),instant(release['scope_end_utc']),[])
        history.air_quality.return_value=dict(rows=rows,next_cursor=None)
        with patch('app.repositories.gold.dashboard.GoldHistoryRepository',return_value=history):
            with self.assertRaises(DataSourceUnavailable):
                GoldDashboardRepository(serving).get_dashboard()

    def test_out_of_scope_rejected(self):
        repo=GoldServingRepository(None)
        with patch.object(repo,'resolve',return_value=dict(release_id='r1',scope_start_utc='2026-01-01T17:00:00Z',scope_end_utc='2026-01-02T17:00:00Z')):
            with self.assertRaises(ValueError):
                repo.air_quality(start=datetime(2020,1,1,tzinfo=timezone.utc))

if __name__=='__main__':unittest.main()
