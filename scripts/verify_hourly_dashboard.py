"""Full standalone validation: immutable Parquet, APIs, raw-cell gas references."""
import asyncio
from collections import defaultdict
from datetime import datetime, timezone
import json
from math import isclose
from pathlib import Path
from time import perf_counter
import numpy as np
import pyarrow.parquet as pq
from httpx import AsyncClient, ASGITransport
from app.etl.eac4 import DEFAULT_INPUT  # imports PROJ before ecCodes
import eccodes as ec
from app.core.config import DEFAULT_PARQUET_PATH, Settings
from app.main import create_app
from app.repositories.parquet.dashboard import ParquetDashboardRepository
from app.services.temporal import DashboardQuery


def raw_field(path, instant):
    """Seek fixed-size local GRIB messages, checking the actual resulting timestamp."""
    with path.open('rb') as stream:
        h=ec.codes_grib_new_from_file(stream)
        try:
            size=ec.codes_get_message_size(h)
            start=datetime.strptime(f"{ec.codes_get(h,'validityDate'):08d}{ec.codes_get(h,'validityTime'):04d}",'%Y%m%d%H%M').replace(tzinfo=timezone.utc)
        finally:ec.codes_release(h)
        index=int((instant-start).total_seconds()/3600)
        stream.seek(index*size)
        h=ec.codes_grib_new_from_file(stream)
        try:
            actual=datetime.strptime(f"{ec.codes_get(h,'validityDate'):08d}{ec.codes_get(h,'validityTime'):04d}",'%Y%m%d%H%M').replace(tzinfo=timezone.utc)
            if actual!=instant:
                raise ValueError('GRIB is not fixed-size/hourly; use a validated timestamp index')
            values=ec.codes_get_values(h)
            if ec.codes_get(h,'bitmapPresent'):
                values[np.asarray(ec.codes_get_array(h,'bitmap'))==0]=np.nan
            return values,ec.codes_get_array(h,'pv') if ec.codes_get(h,'NV') else None
        finally:ec.codes_release(h)


async def main():
    root=DEFAULT_PARQUET_PATH
    generation=(root/'CURRENT').read_text().strip()
    folder=root/'runs'/generation
    manifest=json.loads((folder/'manifest.json').read_text())
    assert manifest['province_count'] == 34
    assert {p['code'] for p in manifest['provinces']}.isdisjoint({'20333','22736'})
    assert manifest['processing_version']=='eac4-l60-moist-density-v1'
    assert manifest['cadence_hours']==1 and manifest['temporal_origin']=='interpolated'
    assert {s['name'] for s in manifest['sources']} >= {'co','no2','so2','o3','pm1','pm25','pm10'}
    physical_rows=0
    reused_partitions=0
    for source in manifest['sources']:
        files=sorted((folder/'observations'/source['name']).glob('*/*.parquet'))
        count=sum(pq.ParquetFile(p).metadata.num_rows for p in files)
        assert count==source['rows']
        physical_rows+=count
        if source.get('reused_from_generation'):
            previous=root/'runs'/source['reused_from_generation']/'observations'/source['name']
            if previous.exists():
                for file in files:
                    old=previous/file.relative_to(folder/'observations'/source['name'])
                    assert file.stat().st_ino==old.stat().st_ino
                    reused_partitions+=1
    repo=ParquetDashboardRepository(root)
    timings={}
    for name in ['cold','warm']:
        started=perf_counter();data=repo.get_dashboard(DashboardQuery('hourly'))
        timings[name]=round((perf_counter()-started)*1000,2)
    app=create_app(Settings(),repo)
    responses={};probes=[]
    async with AsyncClient(transport=ASGITransport(app=app),base_url='http://test') as client:
        for endpoint in ['/api/dashboard','/api/admin/dashboard']:
            response=await client.get(endpoint,params=dict(resolution='hourly',start='2025-12-30',end='2025-12-30'))
            assert response.status_code==200,response.text
            payload=response.json()
            assert len(payload['provinceSnapshots']) == 34
            assert {r['provinceCode'] for r in payload['provinceSnapshots']}.isdisjoint({'20333','22736'})
            hours=sorted({r['date'][11:13] for r in payload['dashboardTrendRecords']})
            assert hours==[f'{h:02}' for h in range(24)]
            assert payload['metadata']['generation']==generation
            assert all(r['aqi'] is None for r in payload['provinceSnapshots'])
            for metric in ('co','no2','so2','o3'):
                meta=payload['metadata']['metrics'][metric]
                assert meta['unit']==('mg/m³' if metric=='co' else 'µg/m³')
                assert meta['mmrMassBasis']=='moist_air' and meta['sourceLevel']==60
                for key in ('metricId','displayName','quantityType','sourceUnit','displayUnit','sourceParamId','sourceLevel','conversionMethod','qualityStatus','sourceResolution','displayResolution'):
                    assert meta[key] is not None,(metric,key)
            responses[endpoint]=dict(rows=len(payload['dashboardTrendRecords']),hours=hours,bytes=len(response.content),gas_metadata_verified=True)
        # Independent raw references across the GRIB PV encoding boundaries and final years.
        codes=[p['code'] for p in manifest['provinces']]
        gas_source=next(s for s in manifest['sources'] if s['name']=='co')
        weight_rows=pq.read_table(folder/'weights'/f"{gas_source['grid_id']}.parquet").to_pylist()
        weights=np.zeros((len(codes),575))
        for row in weight_rows:weights[codes.index(row['province_code']),row['cell_index']]=row['province_fraction']
        for iso in ['2003-01-01T01:00:00Z','2012-12-31T23:00:00Z','2013-01-01T00:00:00Z','2016-12-31T23:00:00Z','2017-01-01T00:00:00Z','2025-12-30T01:00:00Z']:
            instant=datetime.fromisoformat(iso.replace('Z','+00:00'))
            raw={};pvs={}
            for key in ('t_model','q_model','sp','co','no2','so2','o3'):
                raw[key],pvs[key]=raw_field(DEFAULT_INPUT/f'{key}_2003_2025_vietnam.grib',instant)
            for key in ('t_model','q_model','no2','so2','o3'):np.testing.assert_array_equal(pvs[key],pvs['co'])
            pv=pvs['co'];n=len(pv)//2
            # Explicit independent half/full pressure, mixture and cell product.
            above=pv[59]+pv[n+59]*raw['sp'];below=pv[60]+pv[n+60]*raw['sp']
            pressure=(above+below)/2
            rho=pressure/(((1-raw['q_model'])*287.05+raw['q_model']*461.5)*raw['t_model'])
            assert np.all((pressure>0)&(pressure<raw['sp'])&(rho>0))
            response=await client.get('/api/dashboard',params=dict(resolution='hourly',start=iso,end=iso))
            assert response.status_code==200,response.text
            by_code={row['provinceCode']:row for row in response.json()['dashboardTrendRecords']}
            for metric,scale in [('co',1e6),('no2',1e9),('so2',1e9),('o3',1e9)]:
                grid=raw[metric]*rho*scale
                for index,code in enumerate(codes):
                    finite=np.isfinite(grid);coverage=float(weights[index,finite].sum())
                    expected=float(np.dot(grid[finite],weights[index,finite])/coverage) if coverage>=manifest['minimum_coverage'] else None
                    actual=by_code[code][metric]
                    assert actual is None if expected is None else isclose(actual,expected,rel_tol=1e-11,abs_tol=1e-10),(iso,code,metric,actual,expected)
            probes.append(dict(timestamp=iso,regions=len(codes),gas_metrics=4,density_min=float(rho.min()),density_max=float(rho.max()),raw_reference_match=True))
        # Check time aggregation for all seven pollutants, independently from hourly API rows.
        hourly=await client.get('/api/dashboard',params=dict(resolution='hourly',start='2025-12-01',end='2025-12-31'))
        assert hourly.status_code==200
        reference=defaultdict(list)
        for row in hourly.json()['dashboardTrendRecords']:
            for metric in ('pm1','pm25','pm10','co','no2','so2','o3'):
                if row[metric] is not None:reference[(row['provinceCode'],row['date'][:10],metric)].append(row[metric])
        for resolution in ('daily','monthly'):
            response=await client.get('/api/dashboard',params=dict(resolution=resolution,start='2025-12-01',end='2025-12-31'))
            assert response.status_code==200,response.text
            for row in response.json()['dashboardTrendRecords']:
                for metric in ('pm1','pm25','pm10','co','no2','so2','o3'):
                    samples=reference.get((row['provinceCode'],row['date'],metric),[]) if resolution=='daily' else [v for (code,_,name),values in reference.items() if code==row['provinceCode'] and name==metric for v in values]
                    threshold=18 if resolution=='daily' else 31*24*.75
                    expected=sum(samples)/len(samples) if len(samples)>=threshold else None
                    assert row[metric] is None if expected is None else isclose(row[metric],expected,rel_tol=1e-10,abs_tol=1e-10)
            responses[resolution]=dict(rows=len(response.json()['dashboardTrendRecords']),all_seven_pollutants_recomputed_from_hourly=True)
        response=await client.get('/api/dashboard/analytics',params=dict(resolution='hourly',metric='co',start='2025-12-30',end='2025-12-30'))
        assert response.status_code==200,response.text
        responses['analytics']=response.json()['summary']
    result=dict(generation=generation,source=manifest['input_directory'],temporal_origin=manifest['temporal_origin'],
        processing_version=manifest['processing_version'],start=min(s['start'] for s in manifest['sources']),end=max(s['end'] for s in manifest['sources']),
        province_count=manifest['province_count'],metric_count=len(manifest['sources']),physical_rows=physical_rows,
        reused_partitions_checked=reused_partitions,remaining_generations=sorted(p.name for p in (root/'runs').iterdir() if p.is_dir()),timings_ms=timings,responses=responses,raw_gas_reference_probes=probes)
    for path in ['reports/dashboard/hourly-integration.json','reports/dashboard/science/integration.json']:
        Path(path).write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))


if __name__=='__main__':asyncio.run(main())
