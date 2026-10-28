"""Real Spark/Iceberg/Trino replay, corrections, deletion, failed publish and rollback.

Only gold_test* is mutated. Existing real Silver is read-only.
"""
import json
from pathlib import Path
import subprocess
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from app.repositories.gold.client import TrinoClient
from app.repositories.gold.serving import GoldServingRepository

BASE=['docker','compose','exec','-T','spark-master','/opt/spark/bin/spark-submit','--master','local[1]','--driver-memory','2g']
ROOT='/opt/spark/work-dir/jobs/gold/'
ARGS=['--schema','gold_test_hourly','--silver-schema','gold_test_silver','--adapter','normalized_hourly',
      '--contract','/opt/spark/work-dir/lakehouse/gold/contracts/normalized-hourly-v1.json',
      '--dataset-id','hourly_fixture_only','--fixture','--start-date','2026-01-02','--end-date','2026-01-04']
REPORT=Path('reports/gold/pipeline-checks.json')


def run(name,job,args=(),expect=0):
    start=time.monotonic()
    log=Path('reports/gold')/(name+'.log')
    with log.open('w') as output:
        result=subprocess.run(BASE+[ROOT+job]+list(args),stdout=output,stderr=subprocess.STDOUT)
    if expect==0 and result.returncode!=0 or expect!=0 and result.returncode==0:
        raise AssertionError((name,result.returncode,log.read_text()[-2500:]))
    markers=[line for line in log.read_text().splitlines() if line.startswith('GOLD_')]
    return dict(seconds=round(time.monotonic()-start,3),exit_code=result.returncode,markers=markers)


def main():
    client=TrinoClient('http://127.0.0.1:8083')
    repo=GoldServingRepository(client,'gold_test_hourly')
    checks={}
    checks['restore_input']=run('test-restore','tests/mutate_hourly_fixture.py',['restore'])
    checks['baseline']=run('test-baseline','run.py',ARGS)
    first=repo.resolve()
    baseline=repo.air_quality(release_id=first['release_id'])
    assert len(baseline['rows'])==48 and all(r['aqi']==50 for r in baseline['rows'])
    checks['replay']=run('test-replay','run.py',ARGS)
    assert any(line.startswith('GOLD_REPLAY') for line in checks['replay']['markers'])
    assert repo.resolve()==first
    checks['correct_delete']=run('test-correct-delete','tests/mutate_hourly_fixture.py',['change'])
    checks['failed_stage']=run('test-failed-stage','run.py',ARGS+['--fail-before-pointer'],expect=1)
    assert repo.resolve()==first
    assert repo.air_quality(release_id=first['release_id'])['rows']==baseline['rows']
    checks['failed_after_registry']=run('test-failed-registry','run.py',ARGS+['--fail-after-registry'],expect=1)
    assert repo.resolve()==first
    checks['recovery']=run('test-recovery','run.py',ARGS)
    assert any(line.startswith('GOLD_RECOVERED_POINTER') for line in checks['recovery']['markers'])
    second=repo.resolve()
    assert second['release_id']!=first['release_id']
    daily=repo.air_quality('daily')['rows']
    assert [r['aqi'] for r in daily]==[56,10],daily
    assert [r['valid_hours'] for r in daily]==[24,23]
    rejected=repo.air_quality('daily',pollutant='so2')['rows']
    assert rejected[0]['valid_hours']==23 and rejected[1]['valid_hours']==24
    # Fixed scopes recompute all dependencies, and removed input is absent from facts.
    fact=repo.table('fact_air_quality_hourly',second)
    removed=client.query('SELECT count(*) n FROM '+fact+' WHERE '+repo.release_filter(second)+
        " AND pollutant='pm25' AND hour_start_utc=TIMESTAMP '2026-01-03 05:00:00 UTC'")
    assert removed[0]['n']==0
    assert repo.air_quality(release_id=first['release_id'])['rows']==baseline['rows']
    checks['rollback']=run('test-rollback','activate_release.py',['--schema','gold_test_hourly','--release-id',first['release_id']])
    assert repo.resolve()['release_id']==first['release_id']
    assert repo.air_quality()['rows']==baseline['rows']
    checks['restore_again']=run('test-restore-again','tests/mutate_hourly_fixture.py',['restore'])
    checks['final_baseline']=run('test-final-baseline','run.py',ARGS)
    assert all(r['aqi']==50 for r in repo.air_quality()['rows'])
    checks['partition_fixture']=run('test-partition-fixture','tests/prepare_hourly_fixture.py',['--start-date','2026-01-31'])
    partition_args=[v for v in ARGS]
    partition_args[partition_args.index('gold_test_hourly')]='gold_test_partition'
    partition_args[partition_args.index('2026-01-02')]='2026-01-31'
    partition_args[partition_args.index('2026-01-04')]='2026-02-02'
    checks['partition_build']=run('test-partition-build','run.py',partition_args)
    partition_repo=GoldServingRepository(client,'gold_test_partition')
    assert len(partition_repo.air_quality()['rows'])==48
    months=partition_repo.air_quality('monthly')['rows']
    assert len(months)==2 and [r['valid_hours'] for r in months]==[24,24]
    assert all(r['aqi']==50 for r in partition_repo.air_quality('daily')['rows'])
    checks['releases']=dict(original=first['release_id'],corrected=second['release_id'],final=repo.resolve()['release_id'])
    REPORT.write_text(json.dumps(checks,indent=2))
    print(json.dumps(checks,indent=2))

if __name__=='__main__':main()
