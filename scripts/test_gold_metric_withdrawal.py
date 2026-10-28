"""Real complete-metric deletion must replace its scope without creating a new semantic lane."""
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from test_gold_pipeline import run
from app.repositories.gold.client import TrinoClient
from app.repositories.gold.serving import GoldServingRepository
from app.repositories.gold.history import GoldHistoryRepository

args=['--schema','gold_test_deletion','--silver-schema','gold_test_deletion_silver','--adapter','normalized_hourly',
 '--contract','/opt/spark/work-dir/lakehouse/gold/contracts/normalized-hourly-v3.json','--dataset-id','hourly_fixture_only',
 '--fixture','--start-date','2026-04-01','--end-date','2026-04-03']
checks={}
checks['prepare']=run('metric-prepare','tests/prepare_hourly_fixture.py',['--namespace','gold_test_deletion_silver','--start-date','2026-04-01','--days','2'])
checks['restore_input']=run('metric-restore','tests/mutate_full_pollutant.py',['restore'])
checks['baseline']=run('metric-baseline','run.py',args)
client=TrinoClient('http://127.0.0.1:8083');repo=GoldHistoryRepository(GoldServingRepository(client,'gold_test_deletion'))
first=repo.resolve();lane=first['segments'][0]['compatibility_id']
assert len(repo.air_quality(pollutant='so2')['rows'])==48
checks['withdraw']=run('metric-withdraw','tests/mutate_full_pollutant.py',['withdraw'])
checks['rebuild']=run('metric-rebuild','run.py',args)
second=repo.resolve()
assert {s['compatibility_id'] for s in second['segments']}=={lane}
rows=repo.air_quality(pollutant='so2')['rows']
assert len(rows)==48 and all(r['value'] is None for r in rows)
assert all(r['valid_hours']==0 for r in repo.air_quality('daily',pollutant='so2')['rows'])
monthly=repo.air_quality('monthly',pollutant='so2')['rows'][0]
assert monthly['value'] is None and monthly['valid_hours']==0
assert all(r['value']==10 for r in repo.air_quality(pollutant='so2',timeline_id=first['timeline_id'])['rows'])
checks['bad_metadata']=run('metric-bad-metadata','tests/mutate_full_pollutant.py',['incompatible'])
checks['reject_metadata']=run('metric-reject','run.py',args,expect=1)
assert repo.resolve()['timeline_id']==second['timeline_id']
checks['result']=dict(semantic_lanes=1,so2_null_hour_statuses=48,old_snapshot_values_retained=True,
                     unreviewed_vertical_change_published=False)
Path('reports/gold/readiness/metric-withdrawal.json').write_text(json.dumps(checks,indent=2))
print(json.dumps(checks,indent=2))
