"""Real incompatible policy rejection, rollback, bounded 7-day telemetry and storage evidence."""
import json
from pathlib import Path
import subprocess
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from app.repositories.gold.client import TrinoClient
from app.repositories.gold.serving import GoldServingRepository
from app.repositories.gold.history import GoldHistoryRepository
from test_gold_pipeline import run,BASE,ROOT

client=TrinoClient('http://127.0.0.1:8083')
repo=GoldHistoryRepository(GoldServingRepository(client,'gold_test_history_v2'))
saved=repo.resolve()
args=['--schema','gold_test_history_v2','--silver-schema','gold_test_history_v2_silver','--adapter','normalized_hourly',
 '--contract','/opt/spark/work-dir/lakehouse/gold/contracts/normalized-hourly-incompatible-fixture.json','--dataset-id','hourly_fixture_only',
 '--fixture','--start-date','2025-12-30','--end-date','2025-12-31']
result={}
result['incompatible_build']=run('operations-incompatible','run.py',args)
try:
    repo.air_quality()
except ValueError:
    pass
else:
    # Replaying a previously rolled-back release must not re-publish it. To
    # repeat this isolated test, explicitly restore its immutable mixed view.
    candidates=client.query('SELECT timeline_id,manifest_json FROM iceberg.gold_test_history_v2.gold_timeline ORDER BY published_at DESC')
    mixed=next(row for row in candidates if len({s['compatibility_id'] for s in json.loads(row['manifest_json'])['segments']})>1)
    result['repeat_explicit_activation']=run('operations-repeat','activate_release.py',['--schema','gold_test_history_v2','--timeline-id',mixed['timeline_id']])
    try:repo.air_quality();raise AssertionError('Mixed policies must be rejected')
    except ValueError:pass
lane=saved['segments'][0]['compatibility_id']
assert len(repo.air_quality(compatibility_id=lane)['rows'])==72
result['incompatibility_rejected']=True
result['rollback']=run('operations-restore','activate_release.py',['--schema','gold_test_history_v2','--timeline-id',saved['timeline_id']])
result['prepare_7day']=run('operations-prepare','tests/prepare_hourly_fixture.py',['--namespace','gold_test_performance_silver','--start-date','2026-03-01','--days','7'])
performance=['--schema','gold_test_performance','--silver-schema','gold_test_performance_silver','--adapter','normalized_hourly',
 '--contract','/opt/spark/work-dir/lakehouse/gold/contracts/normalized-hourly-v2.json','--dataset-id','hourly_fixture_only',
 '--fixture','--start-date','2026-03-01','--end-date','2026-03-08']
log=Path('reports/gold/readiness/performance.log')
with log.open('w') as output:
    process=subprocess.run(['docker','compose','exec','-T','spark-master','python3',ROOT+'tests/measure_process.py']+performance,stdout=output,stderr=subprocess.STDOUT)
assert process.returncode==0,log.read_text()[-3000:]
result['performance']=json.loads(next(l.split(' ',1)[1] for l in log.read_text().splitlines() if l.startswith('GOLD_PROCESS_METRICS ')))
serving=GoldServingRepository(client,'gold_test_performance');release=serving.resolve()
result['storage']={}
for table in ['fact_air_quality_hourly','fact_measurement_provenance','mart_air_quality_hourly','mart_air_quality_daily','mart_air_quality_monthly']:
    result['storage'][table]=client.query('SELECT count(*) files,sum(file_size_in_bytes) bytes,sum(record_count) records FROM iceberg.gold_test_performance."'+table+'$files" WHERE partition.release_id=\''+release['release_id']+"'")[0]
start=time.monotonic();rows=GoldHistoryRepository(serving).air_quality()['rows'];result['trino_history_seconds']=round(time.monotonic()-start,3)
assert len(rows)==168
result['timeline_growth']=client.query('SELECT count(*) versions,sum(length(manifest_json)) bytes,max(length(manifest_json)) max_manifest_bytes FROM iceberg.gold_test_history_v2.gold_timeline')[0]
result['limits']='Synthetic one-location 7-day scope, local[1]/2GiB; child RSS is not aggregate Docker memory. No full archive or production throughput claim.'
Path('reports/gold/readiness/operations-checks.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result,indent=2))
