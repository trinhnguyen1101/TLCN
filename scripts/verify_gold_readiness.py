"""Read-only final real-stack acceptance: multi-year bounds, source filters and provenance."""
import json
from pathlib import Path
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from fastapi.testclient import TestClient
from app.main import create_app
from app.core.config import Settings
from app.repositories.gold.client import TrinoClient
from app.repositories.gold.serving import GoldServingRepository
from app.repositories.gold.history import GoldHistoryRepository
from unittest.mock import patch

settings=Settings(dashboard_data_source='gold',gold_schema='gold_test_history_v2')
app=create_app(settings)
results={}
with TestClient(app) as client:
    for resolution,count in [('hourly',72),('daily',3),('monthly',2)]:
        start=time.monotonic()
        response=client.get('/api/gold/history',params=dict(resolution=resolution,start='2018-12-31T17:00:00Z',end='2030-12-31T17:00:00Z'))
        assert response.status_code==200,response.text
        data=response.json();assert len(data['rows'])==count and len(data['missing_scopes'])==2,data
        if resolution=='monthly':
            assert data['rows'][0]['valid_days']==1 and data['rows'][0]['observed_days']==2
        results[resolution]=dict(rows=count,missing_scopes=data['missing_scopes'],seconds=round(time.monotonic()-start,3))
    for path in ['/api/dashboard?resolution=monthly&source=hourly_fixture',
                 '/api/admin/dashboard?resolution=daily&source=hourly_fixture',
                 '/api/dashboard/analytics?metric=pm25',
                 '/api/gold/history/quality','/api/gold/history/aqi-distribution',
                 '/api/gold/map?at=2025-12-29T17:00:00Z']:
        response=client.get(path);assert response.status_code==200,(path,response.text)
        results[path]=response.json()
    assert results['/api/gold/history/aqi-distribution']['series_days']==3
    quality=next(r for r in results['/api/gold/history/quality']['rows'] if r['pollutant']=='pm25')
    assert quality['valid_measurements']==71 and quality['expected_hours']==72
    assert client.get('/api/gold/history/quality?start=2025-12-30T00:00:00Z').status_code==422
    assert client.get('/api/dashboard?resolution=daily&source=hourly_fixture&start=2024-01-01&end=2024-01-03').status_code==200
trino=TrinoClient('http://127.0.0.1:8083')
results['production_air_quality_releases']=trino.query("SELECT count(*) n FROM iceberg.gold.gold_release WHERE channel='air_quality'")[0]['n']
assert results['production_air_quality_releases']==0
results['production_fixture_rows']=trino.query("SELECT count(*) n FROM iceberg.gold.fact_air_quality_hourly WHERE source_dataset LIKE '%fixture%' OR source_dataset LIKE '%validation%'")[0]['n']
assert results['production_fixture_rows']==0
results['production_concentration_rows']=trino.query('SELECT count(*) n FROM iceberg.gold.fact_air_quality_hourly')[0]['n']
assert results['production_concentration_rows']==0
published=GoldServingRepository(trino,'gold_test_performance').resolve()
results['provenance_rows']=trino.query('SELECT count(*) n FROM iceberg.gold_test_performance.fact_measurement_provenance FOR VERSION AS OF '+str(published['snapshots']['fact_measurement_provenance'])+" WHERE release_id='"+published['release_id']+"'")[0]['n']
assert results['provenance_rows']==1074
# Resolve an actual immutable mixed spatial-policy view from the registry.
views=trino.query('SELECT timeline_id,manifest_json FROM iceberg.gold_test_history_v2.gold_timeline ORDER BY published_at DESC')
mixed=next(row for row in views if len({s['compatibility_id'] for s in json.loads(row['manifest_json'])['segments']})>1)
history=GoldHistoryRepository(GoldServingRepository(trino,'gold_test_history_v2'))
context=history.resolve(mixed['timeline_id'])
with patch.object(GoldHistoryRepository,'resolve',return_value=context):
    with TestClient(create_app(settings)) as client:
        response=client.get('/api/dashboard',params=dict(resolution='hourly',start='2025-12-30T17:00:00Z',end='2025-12-31T16:59:59Z'))
        assert response.status_code==200,response.text
        assert len(response.json()['dashboardTrendRecords'])==24
        assert client.get('/api/dashboard?resolution=hourly').status_code==422
        results['mixed_policy_narrow_dashboard_rows']=24
with TestClient(create_app(Settings(dashboard_data_source='gold',gold_schema='gold_test_deletion'))) as client:
    response=client.get('/api/dashboard?resolution=hourly')
    assert response.status_code==200,response.text
    province=next(row for row in response.json()['provinceSnapshots'] if row['provinceCode']=='01')
    assert province['qualityStatus']=='partial'
    assert province['so2'] is None and province['metricQuality']['so2']['qualityStatus']=='missing'
    assert province['metricQuality']['so2']['observationTime'] is None
    assert province['metricQuality']['o3']['qualityStatus']=='ok' and province['metricQuality']['o3']['observationTime']
    results['per_pollutant_snapshot_qc']=province['metricQuality']
host=GoldHistoryRepository(GoldServingRepository(trino,'gold_test_hostrunner'))
host_hourly=host.air_quality();host_daily=host.air_quality('daily');host_monthly=host.air_quality('monthly')
assert len(host_hourly['rows'])==168 and all(row['aqi']==50 for row in host_hourly['rows'])
assert len(host_daily['rows'])==7 and all(row['aqi']==50 for row in host_daily['rows'])
assert len(host_monthly['rows'])==1 and host_monthly['rows'][0]['valid_days']==7
host_registry=trino.query('SELECT count(*) n FROM iceberg.gold_test_hostrunner.gold_release')[0]['n']
host_versions=trino.query('SELECT count(*) n FROM iceberg.gold_test_hostrunner.gold_timeline')[0]['n']
assert host_registry==2 and host_versions==2
results['host_runner_counts']=dict(hourly=168,daily=7,monthly=1,releases=host_registry,timeline_versions=host_versions)
Path('reports/gold/readiness/final-serving.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))
print(json.dumps({k:v for k,v in results.items() if not k.startswith('/api/')},indent=2))
