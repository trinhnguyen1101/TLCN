"""Real Spark/Iceberg/Trino/FastAPI historical acceptance, isolated fixture namespaces."""
import json
import os
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
from app.repositories.gold.dashboard import GoldDashboardRepository
from app.services.temporal import DashboardQuery
from test_gold_pipeline import run

SCHEMA=os.environ.get('GOLD_HISTORY_TEST_SCHEMA',sys.argv[1] if len(sys.argv)>1 else 'gold_test_history')
if not SCHEMA.startswith('gold_test'):raise ValueError('Isolated test namespace required')
SILVER=SCHEMA+'_silver'
ARGS=['--schema',SCHEMA,'--silver-schema',SILVER,'--adapter','normalized_hourly',
 '--contract','/opt/spark/work-dir/lakehouse/gold/contracts/normalized-hourly-v2.json','--dataset-id','hourly_fixture_only','--fixture']
START='2025-12-29T17:00:00Z';END='2026-01-01T17:00:00Z'

def main():
    checks={}
    checks['prepare']=run('history-prepare','tests/prepare_hourly_fixture.py',['--namespace',SILVER,'--start-date','2025-12-30','--days','4'])
    client=TrinoClient('http://127.0.0.1:8083');serving=GoldServingRepository(client,SCHEMA);history=GoldHistoryRepository(serving)
    def build(name,lo,hi,extra=()):
        checks[name]=run('history-'+name,'run.py',ARGS+['--start-date',lo,'--end-date',hi]+list(extra))
    def read(resolution='hourly',**kwargs):return history.air_quality(resolution,start=START,end=END,**kwargs)
    build('chunk_a','2025-12-30','2025-12-31');build('chunk_c','2026-01-01','2026-01-02')
    missing=read();assert len(missing['rows'])==48 and len(missing['missing_scopes'])==1,missing
    checks['missing_chunk']=dict(rows=48,missing=missing['missing_scopes'])
    build('chunk_b','2025-12-31','2026-01-01')
    original=history.resolve();hourly=read();daily=read('daily');monthly=read('monthly')
    assert len(hourly['rows'])==72 and not hourly['missing_scopes']
    assert len(daily['rows'])==3 and len(monthly['rows'])==2
    assert [r['valid_hours'] for r in monthly['rows']]==[48,24],monthly
    assert all(r['value']==25 and r['aqi']==50 for r in hourly['rows'])
    assert history.aqi_distribution(start=START,end=END)['series_days']==3
    checks['initial_counts']=dict(hourly=72,daily=3,monthly=2,aqi_series_days=3)
    # Page pins its immutable timeline even if publication happens later.
    first=read(limit=25);assert first['next_cursor']
    checks['correct_input']=run('history-correct-input','tests/mutate_history_fixture.py',['correct',SILVER])
    build('overlap_correction','2025-12-30','2026-01-01')
    corrected=read();assert len(corrected['rows'])==72
    assert sum(r['value']==75 for r in corrected['rows'])==1
    assert len({(r['series_id'],r['hour_start_utc'],r['pollutant']) for r in corrected['rows']})==72
    second=read(limit=25,cursor=first['next_cursor'])
    assert second['published_timeline_id']==original['timeline_id'] and all(r['value']==25 for r in second['rows'])
    checks['delete_input']=run('history-delete-input','tests/mutate_history_fixture.py',['delete',SILVER])
    build('delete_rebuild','2025-12-31','2026-01-02')
    deleted=read();assert len(deleted['rows'])==72 and sum(r['value'] is None for r in deleted['rows'])==1
    assert [r['valid_hours'] for r in read('monthly')['rows']]==[47,24]
    saved=history.resolve()
    # A request resolves once, then a real publication occurs before its data read.
    class ConcurrentClient:
        def __init__(self):self.published=False
        def query(self,sql):
            result=client.query(sql)
            if 'gold_timeline_current' in sql and not self.published:
                self.published=True;build('concurrent_chunk_d','2026-01-02','2026-01-03')
            return result
    concurrent=GoldHistoryRepository(GoldServingRepository(ConcurrentClient(),SCHEMA))
    held=concurrent.air_quality(start=START,end='2026-01-02T17:00:00Z')
    assert len(held['rows'])==72 and held['published_timeline_id']==saved['timeline_id']
    fresh=history.air_quality(start=START,end='2026-01-02T17:00:00Z');assert len(fresh['rows'])==96
    checks['concurrent_publication']=dict(held_rows=72,new_request_rows=96)
    checks['rollback']=run('history-rollback','activate_release.py',['--schema',SCHEMA,'--timeline-id',saved['timeline_id']])
    rolled=history.air_quality(start=START,end='2026-01-02T17:00:00Z');assert len(rolled['rows'])==72 and rolled['missing_scopes']
    # Exercise HTTP contracts with real Trino, including dashboard projection.
    app=create_app(Settings(),GoldDashboardRepository(serving));app.state.gold_repository=serving
    with TestClient(app) as api:
        for resolution,count in [('hourly',72),('daily',3),('monthly',2)]:
            response=api.get('/api/gold/history',params=dict(start=START,end=END,resolution=resolution))
            assert response.status_code==200,response.text
            assert len(response.json()['rows'])==count
        response=api.get('/api/gold/history/aqi-distribution',params=dict(start=START,end=END))
        assert response.status_code==200 and response.json()['series_days']==3,response.text
        response=api.get('/api/dashboard',params=dict(resolution='hourly',start=START,end='2026-01-01T16:59:59Z'))
        assert response.status_code==200,response.text
        data=response.json();Path('reports/gold/readiness/history-dashboard.json').write_text(json.dumps(data,indent=2))
        checks['dashboard']=dict(provinces=len(data['provinceSnapshots']),points=len(data['dashboardTrendRecords']))
        assert checks['dashboard']==dict(provinces=34,points=72)
    # Explicit withdrawal is a tombstone, never fallback to an older chunk.
    lane=history.resolve()['segments'][0]['compatibility_id']
    checks['withdraw']=run('history-withdraw','manage_timeline.py',['--schema',SCHEMA,'--action','withdraw','--compatibility-id',lane,
        '--start','2025-12-30T17:00:00Z','--end','2025-12-31T17:00:00Z'])
    withdrawn=read();assert len(withdrawn['rows'])==48 and withdrawn['missing_scopes'][0]['reason']=='withdrawn_scope'
    checks['restore_timeline']=run('history-restore','activate_release.py',['--schema',SCHEMA,'--timeline-id',saved['timeline_id']])
    checks['retention']=run('history-retention','manage_timeline.py',['--schema',SCHEMA,'--action','retention'])
    checks['final_counts']=dict(hourly=len(read()['rows']),daily=len(read('daily')['rows']),monthly=len(read('monthly')['rows']))
    Path('reports/gold/readiness/history-checks.json').write_text(json.dumps(checks,indent=2))
    print(json.dumps(checks,indent=2))
if __name__=='__main__':main()
