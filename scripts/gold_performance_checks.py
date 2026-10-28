"""Real API/Trino acceptance for the isolated 34-province monthly benchmark."""
from datetime import datetime,timedelta
import json
from pathlib import Path
import time
from urllib.request import Request,urlopen
from fastapi.testclient import TestClient
from app.main import create_app
from app.core.config import Settings
from app.repositories.gold.client import TrinoClient
from app.repositories.gold.serving import GoldServingRepository
from app.repositories.gold.dashboard import GoldDashboardRepository


class MeasuredClient(TrinoClient):
    def __init__(self):super().__init__('http://127.0.0.1:8083');self.calls=[]
    def query(self,sql):
        start=time.monotonic();rows=super().query(sql)
        call=dict(seconds=time.monotonic()-start,rows=len(rows),snapshot_scans=sql.count('FOR VERSION AS OF'),sql_bytes=len(sql.encode()),stats=self.last_stats)
        if self.last_query_id:
            try:
                with urlopen(Request(self.uri+'/v1/query/'+self.last_query_id,headers={'X-Trino-User':self.user}),timeout=3) as response:info=json.load(response)
                call['query_stats']={k:info.get('queryStats',{}).get(k) for k in ['planningTime','analysisTime','executionTime','elapsedTime','physicalInputDataSize','physicalInputPositions']}
            except OSError:call['query_stats']=None
        self.calls.append(call);return rows


def run():
    client=MeasuredClient();schema='gold_test_perf_month34'
    serving=GoldServingRepository(client,schema);settings=Settings(dashboard_data_source='gold',gold_schema=schema)
    app=create_app(settings,GoldDashboardRepository(serving));app.state.gold_repository=serving
    checks=dict(kind='real_spark_iceberg_trino_fastapi_fixture_acceptance',schema=schema)
    start='2026-04-30T17:00:00Z';end='2026-05-31T17:00:00Z'
    with TestClient(app) as api:
        cursor=None;keys=set();pages=[];aqi_valid=0;missing_values=0;timeline=None
        while True:
            params=dict(start=start,end=end,pollutant='pm25',limit=10000)
            if cursor:params['cursor']=cursor
            begin=time.monotonic();response=api.get('/api/gold/history',params=params)
            assert response.status_code==200,response.text
            data=response.json();rows=data['rows']
            if timeline is None:timeline=data['published_timeline_id']
            assert data['published_timeline_id']==timeline and len(rows)<=10000
            for row in rows:
                key=(row['series_id'],row['hour_start_utc'],row['pollutant']);assert key not in keys;keys.add(key)
                aqi_valid+=row['aqi'] is not None;missing_values+=row['value'] is None
                if row['observation_time']:
                    assert datetime.fromisoformat(row['observation_time'].replace('Z','+00:00'))-datetime.fromisoformat(row['hour_start_utc'].replace('Z','+00:00'))==timedelta(hours=1)
            pages.append(dict(rows=len(rows),seconds=time.monotonic()-begin));cursor=data['next_cursor']
            if not cursor:break
        assert len(keys)==34*31*24 and aqi_valid==len(keys) and missing_values==1
        checks['hourly']=dict(rows=len(keys),pages=pages,valid_aqi=aqi_valid,missing_pm25=missing_values)
        for resolution,count in [('daily',34*31),('monthly',34)]:
            response=api.get('/api/gold/history',params=dict(resolution=resolution,start='2018-12-31T17:00:00Z',end='2030-12-31T17:00:00Z'))
            assert response.status_code==200,response.text
            rows=response.json()['rows'];assert len(rows)==count
            if resolution=='monthly':
                assert all(r['aqi'] is None and r['expected_hours']==744 for r in rows)
                assert next(r for r in rows if r['admin_code']=='01')['valid_hours']==743
            checks[resolution]=dict(rows=count,missing_scopes=response.json()['missing_scopes'])
        response=api.get('/api/gold/history',params=dict(start=start,end=end,admin_code='01'))
        assert response.status_code==200 and len(response.json()['rows'])==744
        response=api.get('/api/gold/history/aqi-distribution');assert response.status_code==200,response.text
        assert response.json()['series_days']==34*31;checks['aqi_distribution']=response.json()
        response=api.get('/api/gold/history/quality');assert response.status_code==200,response.text
        rows={r['pollutant']:r for r in response.json()['rows']}
        assert rows['pm25']['absent_slots']==1 and rows['pm25']['invalid_measurements']==0
        assert rows['no2']['missing_value_slots']==1 and rows['no2']['absent_slots']==0
        assert rows['so2']['invalid_measurements']==1 and rows['so2']['absent_slots']==0
        assert all(r['failed_ingestions'] is None and r['collection_attempts'] is None for r in rows.values())
        checks['quality']=rows
        response=api.get('/api/dashboard?resolution=monthly');assert response.status_code==200,response.text
        data=response.json();assert len(data['provinceSnapshots'])==34 and len(data['dashboardTrendRecords'])==34
        checks['dashboard_monthly']=dict(provinces=34,points=34,generation=data['metadata']['generation'])
    assert max(c['snapshot_scans'] for c in client.calls)<=32
    checks['queries']=client.calls
    release=serving.resolve();outputs=json.loads(release['output_snapshots_json']);checks['storage']={}
    for table in ['fact_air_quality_hourly','fact_aqi_hourly','mart_air_quality_hourly','mart_air_quality_daily','mart_air_quality_monthly']:
        checks['storage'][table]=client.query('SELECT count(*) files,sum(file_size_in_bytes) bytes,sum(record_count) records FROM iceberg.'+schema+'."'+table+'$files"')[0]
    Path('reports/gold/performance/api-month34.json').write_text(json.dumps(checks,indent=2))
    print('PERFORMANCE_API_VERIFIED '+json.dumps(dict(hourly=34*31*24,daily=34*31,monthly=34,pages=len(pages),series_days=34*31)),flush=True)
