"""Metadata-only archive simulation; never creates Iceberg data/snapshots."""
from copy import deepcopy
from datetime import datetime,timedelta,timezone
import hashlib
import json
from pathlib import Path
import resource
import sys
import time
import tracemalloc
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'spark/jobs/gold'))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from timeline import overlay,unpack_manifest
from app.repositories.gold.history import GoldHistoryRepository
from app.repositories.gold.serving import GoldServingRepository


def identity(value):return hashlib.sha256(str(value).encode()).hexdigest()


def manifest(n):
    series=[dict(series_id=identity('s'+str(i)),dataset_id='benchmark_hourly_only',source_system='hourly_benchmark',
        source_contract_version='benchmark-hourly-v1',source_resolution_minutes=60,temporal_support='hourly_mean',
        applicability_profile='area_estimate',spatial_policy_version='fixture_admin_v1') for i in range(34)]
    tables=['dim_location','dim_air_quality_series','mart_air_quality_hourly','mart_air_quality_daily','mart_air_quality_monthly','mart_source_quality_daily']
    start=datetime(2000,1,1,17,tzinfo=timezone.utc)
    segments=[]
    for i in range(n):
        segments.append(dict(start=(start+timedelta(days=7*i)).isoformat(),end=(start+timedelta(days=7*(i+1))).isoformat(),
            release_id=identity(i),compatibility_id=identity('policy'),method_version='vn-aqi-1459-2019-project-v1',
            contract_sha256=identity('contract'),series=deepcopy(series),withdrawn=False,
            snapshots={table:1000000000000000000+i*100+j for j,table in enumerate(tables)}))
    return dict(version=1,activated_releases=[s['release_id'] for s in segments],segments=segments)


class Client:
    def __init__(self,payload):self.payload=payload;self.statements=[]
    def query(self,sql):
        if 'gold_timeline' in sql:return [dict(timeline_id=identity('timeline'),manifest_json=self.payload)]
        self.statements.append(sql);return []


def measured(function):
    tracemalloc.start();begin=time.perf_counter();value=function();elapsed=time.perf_counter()-begin
    _,peak=tracemalloc.get_traced_memory();tracemalloc.stop()
    return value,dict(seconds=elapsed,python_allocation_peak_bytes=peak)


def main():
    label=sys.argv[1] if len(sys.argv)>1 else 'before'
    result=dict(kind='metadata_only_simulation_no_real_snapshots',label=label,cases=[])
    try:
        from timeline import pack_manifest
    except ImportError:pack_manifest=None
    for count in [100,500,1200]:
        original=manifest(count)
        wire=pack_manifest(original) if pack_manifest and label!='before' else original
        payload=json.dumps(wire,sort_keys=True)
        client=Client(payload);repo=GoldHistoryRepository(GoldServingRepository(client,'gold_test_metadata'))
        context,resolve=measured(repo.resolve)
        _,planning=measured(lambda:repo.air_quality(context=context))
        correction=deepcopy(original['segments'][count//2]);correction['release_id']=identity('corrected')
        changed,correction_time=measured(lambda:overlay(unpack_manifest(wire),correction))
        withdrawal=dict(correction,withdrawn=True);withdrawal.pop('snapshots');withdrawal.pop('release_id')
        _,withdrawal_time=measured(lambda:overlay(changed,withdrawal))
        # Exact v1 cumulative bytes for all prefix versions without retaining N
        # entire JSON strings. Each segment and activation ID is serialized once.
        segment_sizes=[len(json.dumps(s,sort_keys=True).encode()) for s in original['segments']]
        cumulative=sum((count-i)*size for i,size in enumerate(segment_sizes))
        activation_sizes=[len(json.dumps(s).encode()) for s in original['activated_releases']]
        cumulative+=sum((count-i)*size for i,size in enumerate(activation_sizes))
        cumulative+=sum(len(json.dumps(dict(version=1,segments=[],activated_releases=[]),sort_keys=True).encode())+4*max(0,i-1) for i in range(1,count+1))
        wire_segments=[len(json.dumps(s,sort_keys=True).encode()) for s in wire['segments']]
        base={**wire,'segments':[],'activated_releases':[]}
        # This simulation has one shared semantic catalog throughout its lane.
        # Count exact prefix encodings without allocating all N full manifests.
        assert wire.get('version')==1 or len(wire['series_catalog'])==1
        wire_cumulative=count*len(json.dumps(base,sort_keys=True).encode())
        wire_cumulative+=sum((count-i)*(size+activation_sizes[i]) for i,size in enumerate(wire_segments))
        wire_cumulative+=4*sum(max(0,i-1) for i in range(1,count+1))
        case=dict(chunks=count,manifest_bytes=len(payload.encode()),v1_cumulative_prefix_version_bytes=cumulative,
                  cumulative_prefix_version_bytes=wire_cumulative,
                  resolve=resolve,query_generation=planning,overlay=correction_time,withdrawal=withdrawal_time,
                  sql_bytes=sum(len(s.encode()) for s in client.statements),max_scans=max(s.count('FOR VERSION AS OF') for s in client.statements),
                  process_max_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        result['cases'].append(case);print(json.dumps(case),flush=True)
    Path('reports/gold/performance/timeline-'+label+'.json').write_text(json.dumps(result,indent=2))
if __name__=='__main__':main()
