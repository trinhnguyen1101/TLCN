"""Read-only real-stack evidence; no credentials or Landing reads."""
from datetime import datetime,timezone
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from app.repositories.gold.client import TrinoClient
from app.repositories.gold.serving import GoldServingRepository,literal


def main():
    client=TrinoClient('http://127.0.0.1:8083')
    result={'checked_at_utc':datetime.now(timezone.utc).isoformat()}
    result['silver_runs']=client.query("SELECT d.source_system,d.source_version,r.status,r.pipeline_version,count(*) runs,sum(r.output_rows) output_rows FROM iceberg.silver.ingestion_run r JOIN iceberg.silver.dataset d ON d.dataset_id=r.dataset_id GROUP BY 1,2,3,4")
    result['live_silver_counts']={name:client.query('SELECT count(*) rows FROM iceberg.silver.'+name)[0]['rows'] for name in ['waqi_hourly_observation','waqi_hourly_measurement','api_ninjas_province_air_quality_hourly']}
    result['cams_actual']=client.query('SELECT count(*) rows,min(valid_time) first_time,max(valid_time) last_time FROM iceberg.silver.cams_cube_standard')
    result['admin_hierarchy']=client.query("SELECT admin_code,name_vi,parent_code FROM iceberg.silver.admin_unit WHERE is_current AND (parent_code IS NULL OR admin_code IN ('20333','22736')) ORDER BY admin_code")
    for schema,channel in [('gold_pilot','air_quality'),('gold_test_hourly','air_quality'),('gold_test_partition','air_quality'),('gold','native_sources')]:
        repo=GoldServingRepository(client,schema,channel)
        release=repo.resolve()
        registry=client.query('SELECT * FROM iceberg.'+schema+'.gold_release WHERE release_id='+literal(release['release_id']))[0]
        entry={'release':registry,'row_counts':{}}
        for name,snapshot_id in release['snapshots'].items():
            if name=='bridge_cams_region_weight':continue
            count=client.query('SELECT count(*) n FROM iceberg.'+schema+'.'+name+' FOR VERSION AS OF '+str(snapshot_id)+' WHERE release_id='+literal(release['release_id']))
            entry['row_counts'][name]=count[0]['n']
        if schema=='gold_pilot':
            entry['storage']={}
            for name in ['fact_air_quality_hourly','mart_air_quality_hourly']:
                entry['storage'][name]=client.query('SELECT count(*) files,sum(file_size_in_bytes) bytes,sum(record_count) records FROM iceberg.'+schema+'."'+name+'$files" WHERE partition.release_id='+literal(release['release_id']))[0]
            entry['aqi_status']=client.query('SELECT status,missing_reason,count(*) rows FROM iceberg.gold_pilot.fact_aqi_hourly WHERE release_id='+literal(release['release_id'])+' GROUP BY 1,2')
        result[schema]=entry
    Path('reports/gold/runtime-audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps({k:v['row_counts'] for k,v in result.items() if isinstance(v,dict) and 'row_counts' in v},indent=2))

if __name__=='__main__':main()
