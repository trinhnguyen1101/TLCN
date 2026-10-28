"""Real failure recovery for the new timeline's second publication boundary."""
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from test_gold_pipeline import run
from app.repositories.gold.client import TrinoClient
from app.repositories.gold.serving import GoldServingRepository
from app.repositories.gold.history import GoldHistoryRepository
from app.repositories.base import DataSourceUnavailable

schema='gold_test_timeline_fault'
args=['--schema',schema,'--silver-schema','gold_test_history_v2_silver','--adapter','normalized_hourly',
 '--contract','/opt/spark/work-dir/lakehouse/gold/contracts/normalized-hourly-v2.json','--dataset-id','hourly_fixture_only',
 '--fixture','--start-date','2025-12-30','--end-date','2025-12-31']
client=TrinoClient('http://127.0.0.1:8083');repo=GoldHistoryRepository(GoldServingRepository(client,schema))
checks={}
checks['failure']=run('timeline-fault','tests/fail_timeline_pointer.py',args,expect=1)
try:repo.resolve();raise AssertionError('Uncommitted view must be unavailable')
except DataSourceUnavailable:pass
registered=client.query('SELECT timeline_id FROM iceberg.'+schema+'.gold_timeline')
assert len(registered)==1
checks['recovery']=run('timeline-recovery','run.py',args)
assert repo.resolve()['timeline_id']==registered[0]['timeline_id']
assert len(repo.air_quality()['rows'])==24
checks['committed_timeline']=registered[0]['timeline_id']
Path('reports/gold/readiness/timeline-recovery.json').write_text(json.dumps(checks,indent=2))
print(json.dumps(checks,indent=2))
