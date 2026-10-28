"""Bounded Gold build; explicit local-date scope; single writer required.

Production rejects validation/fixture datasets. No input interpolation/fallback.
All staging outputs are immutable once registered and exposed via one pointer.
"""
import argparse
import fcntl
from datetime import date,timezone
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import time
import zipfile

sys.path.insert(0,str(Path(__file__).resolve().parent))
from runtime import Build,bootstrap,spark_session,stable_id,identifier
from aqi.engine import local_day_bounds
from dimensions import build_geography,build_time_method,build_spatial
from adapters import cams,normalized_hourly
from calculate_aqi import calculate
from marts import materialize
from validation import validate
from pyspark.sql import functions as F


def code_digest(schema_sql=None):
    digest=hashlib.sha256()
    for path in sorted(Path(__file__).resolve().parent.rglob('*.py')):
        if 'tests' not in path.parts:
            digest.update(path.name.encode())
            digest.update(path.read_bytes())
    if schema_sql:digest.update(Path(schema_sql).read_bytes())
    return digest.hexdigest()


def distribute(spark):
    path=Path(__file__).resolve().parent
    target=Path(tempfile.gettempdir())/'gold_runtime.zip'
    with zipfile.ZipFile(str(target),'w') as archive:
        for source in path.rglob('*.py'):
            if 'tests' not in source.parts:
                archive.write(str(source),str(source.relative_to(path)))
    spark.sparkContext.addPyFile(str(target))


def execute(args):
    begin=time.monotonic()
    writer_lock=open('/tmp/tlcn-gold-writer.lock','w')
    fcntl.flock(writer_lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    spark=spark_session()
    try:
        distribute(spark)
        schema=identifier(args.schema)
        contract_path=Path(args.contract)
        contract=json.loads(contract_path.read_text())
        contract['geography']=json.loads((contract_path.parent/'reporting-geography-v1.json').read_text())
        start=local_day_bounds(date.fromisoformat(args.start_date))[0]
        end=local_day_bounds(date.fromisoformat(args.end_date))[0]
        if not 0<(end-start).days<=31:
            raise ValueError('Use bounded scopes of 1..31 local days; backfill by chunks')
        if args.allow_validation and schema=='gold':
            raise ValueError('Validation input must use isolated namespace, never gold')
        if args.fixture and (not schema.startswith('gold_test') or not args.silver_schema.startswith('gold_test')):
            raise ValueError('Fixtures require isolated gold_test* input/output namespaces')
        if args.adapter=='normalized_hourly' and not args.fixture and 'minimum_spatial_coverage' not in contract:
            raise ValueError('Production province adapters require a declared spatial coverage gate')
        if args.adapter=='normalized_hourly' and not args.fixture and not contract.get('metric_policies'):
            raise ValueError('Production normalized adapters require complete declared metric policies')
        if args.adapter=='normalized_hourly' and not args.fixture and not contract.get('require_measurement_intervals',False):
            raise ValueError('Production normalized adapters require the explicit interval/provenance contract')
        if args.adapter=='normalized_hourly' and not args.fixture and not contract.get('reviewed_for_production',False):
            raise ValueError('Normalized production contract requires explicit source/temporal review')
        bootstrap(spark,schema,args.schema_sql)
        from aqi.reference import REFERENCE_SHA256
        reference=Path(args.schema_sql).parent/'references'/'1459-2019.pdf'
        if hashlib.sha256(reference.read_bytes()).hexdigest()!=REFERENCE_SHA256:
            raise ValueError('AQI reference checksum mismatch')
        build=Build(spark,schema,args.silver_schema,contract,start,end,args.channel,code_digest(args.schema_sql))
        # Resolve/pin every input BEFORE release identity and any Gold writes.
        inputs=['admin_unit','admin_boundary','ingestion_run']
        if args.adapter=='cams':
            inputs+=['dataset','cams_grid','cams_grid_point','cams_cube_standard_source','cams_cube_standard']
        else:
            inputs+=[contract['silver_table']]
            if not args.fixture:inputs+=['dataset']
        for name in inputs:
            build.read(name)
        # Test fixture namespace inherits real geography via copies with source snapshot metadata.
        if args.adapter=='cams':
            datasets=build.read('dataset').filter('dataset_id=\''+args.dataset_id+'\'').collect()
            if len(datasets)!=1 or datasets[0].source_system!='cams':
                raise ValueError('Unknown CAMS dataset')
            if datasets[0].source_version!='EAC4' and not args.allow_validation:
                raise ValueError('Production accepts only reviewed EAC4 dataset version')
            if contract.get('temporal_support')!='instantaneous' or contract.get('contract_version')!='cams-eac4-instant-v1':
                raise ValueError('This EAC4 adapter accepts only reviewed instantaneous contract')
        if args.adapter=='normalized_hourly' and not args.fixture:
            datasets=build.read('dataset').filter(F.col('dataset_id')==args.dataset_id).collect()
            if len(datasets)!=1 or datasets[0].source_system!=contract['source_system']:
                raise ValueError('Normalized source dataset registry mismatch')
        build.identify()
        print('GOLD_BEGIN '+json.dumps(dict(release_id=build.release_id,inputs=build.inputs)),flush=True)
        existing=spark.table(build.prefix+'gold_release').filter("release_id='"+build.release_id+"'").collect()
        if existing:
            registered=existing[0].asDict()
            pointer=spark.table(build.prefix+'gold_current_release').filter(F.col('channel')==args.channel).collect()
            if not pointer or pointer[0].published_at<registered['published_at']:
                build.activate(registered)
                print('GOLD_RECOVERED_POINTER '+build.release_id,flush=True)
            print('GOLD_REPLAY '+json.dumps(existing[0].asDict(),default=str),flush=True)
            return
        timings={}
        phase=time.monotonic()
        locations=build_geography(build)
        build_time_method(build)
        timings['foundation_seconds']=time.monotonic()-phase
        phase=time.monotonic()
        print('GOLD_PHASE foundation_dimensions_ok',flush=True)
        if args.adapter=='cams':
            build_spatial(build)
            timings['spatial_seconds']=time.monotonic()-phase
            facts,series=cams(build,args.dataset_id,locations)
        else:
            facts,series=normalized_hourly(build,args.dataset_id,locations)
        print('GOLD_PHASE concentration_materialized '+str(len(facts)),flush=True)
        timings['adapter_seconds']=time.monotonic()-phase
        phase=time.monotonic()
        calculate(build)
        timings['aqi_seconds']=time.monotonic()-phase
        print('GOLD_PHASE aqi_materialized',flush=True)
        phase=time.monotonic()
        materialize(build)
        timings['marts_seconds']=time.monotonic()-phase
        phase=time.monotonic()
        counts=validate(build)
        timings['validation_seconds']=time.monotonic()-phase
        phase=time.monotonic()
        release=build.publish(counts,args.fail_before_pointer,args.fail_after_registry)
        timings['publish_seconds']=time.monotonic()-phase
        print('GOLD_TIMINGS '+json.dumps(dict(phases=timings,metrics=build.metrics)),flush=True)
        print('GOLD_PUBLISHED '+json.dumps(dict(release_id=release['release_id'],counts=counts,
                    elapsed_seconds=round(time.monotonic()-begin,3),snapshots=json.loads(release['output_snapshots_json'])),sort_keys=True),flush=True)
    finally:
        spark.stop()
        writer_lock.close()


def parse_args():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--schema',default='gold')
    p.add_argument('--silver-schema',default='silver')
    p.add_argument('--schema-sql',default='/opt/spark/work-dir/lakehouse/gold/gold.sql')
    p.add_argument('--contract',default='/opt/spark/work-dir/lakehouse/gold/contracts/cams-eac4-v1.json')
    p.add_argument('--adapter',choices=['cams','normalized_hourly'],default='cams')
    p.add_argument('--dataset-id',required=True,type=identifier_hash)
    p.add_argument('--start-date',required=True)
    p.add_argument('--end-date',required=True,help='exclusive local VN date')
    p.add_argument('--channel',default='air_quality')
    p.add_argument('--allow-validation',action='store_true')
    p.add_argument('--fixture',action='store_true')
    p.add_argument('--fail-before-pointer',action='store_true')
    p.add_argument('--fail-after-registry',action='store_true')
    return p.parse_args()


def identifier_hash(value):
    import re
    if not re.fullmatch('[a-zA-Z0-9_-]{1,128}',value):
        raise ValueError('Invalid dataset identity')
    return value


if __name__=='__main__':
    execute(parse_args())
