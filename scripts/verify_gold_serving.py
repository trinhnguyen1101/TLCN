"""Real-stack FastAPI -> Trino -> pinned Iceberg integration checks."""
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


def main():
    outputs={}
    for schema in ['gold_pilot','gold_test_hourly']:
        app=create_app(Settings(dashboard_data_source='gold',gold_schema=schema))
        with TestClient(app) as client:
            results={}
            for path in ['/api/gold/map','/api/gold/air-quality?resolution=hourly',
                         '/api/gold/air-quality?resolution=daily','/api/gold/air-quality?resolution=monthly',
                         '/api/gold/source-quality','/api/gold/admin/summary',
                         '/api/dashboard?resolution=hourly','/api/admin/dashboard?resolution=hourly']:
                t=time.monotonic()
                response=client.get(path)
                assert response.status_code==200,(schema,path,response.text[:1000])
                data=response.json()
                results[path]=dict(seconds=round(time.monotonic()-t,3),rows=len(data.get('rows',data.get('provinceSnapshots',[]))))
                if path=='/api/dashboard?resolution=hourly':
                    Path('reports/gold/'+schema+'-dashboard.json').write_text(json.dumps(data,ensure_ascii=False,indent=2))
                if path=='/api/admin/dashboard?resolution=hourly':
                    Path('reports/gold/'+schema+'-admin-dashboard.json').write_text(json.dumps(data,ensure_ascii=False,indent=2))
                if path=='/api/gold/map':
                    assert len(data['rows'])==34
                    assert len({r['admin_code'] for r in data['rows']})==34
                    assert all(r['aqi'] is None for r in data['rows']) if schema=='gold_pilot' else any(r['aqi']==50 for r in data['rows'])
                    Path('reports/gold/'+schema+'-map.json').write_text(json.dumps(data,ensure_ascii=False,indent=2))
                if schema=='gold_test_hourly' and path.endswith('resolution=hourly') and path.startswith('/api/gold/air-quality'):
                    assert len(data['rows'])==48
                    assert all(r['aqi']==50 for r in data['rows'])
                if schema=='gold_test_hourly' and path.endswith('resolution=daily'):
                    assert len(data['rows'])==2
                    assert all(r['aqi']==50 and r['valid_hours']==24 for r in data['rows'])
            outputs[schema]=results
    native=GoldServingRepository(TrinoClient('http://127.0.0.1:8083'),'gold','native_sources')
    emissions=native.native_emissions()
    assert emissions['rows'] and all(r['unit'] is None and r['unit_status']=='unverified' and r['aggregation_level']=='totals' for r in emissions['rows'])
    outputs['native_emissions_rows']=len(emissions['rows'])
    Path('reports/gold/serving-checks.json').write_text(json.dumps(outputs,indent=2))
    print(json.dumps(outputs,indent=2))

if __name__=='__main__':
    main()
    if '--performance' in sys.argv:
        from gold_performance_checks import run
        run()
