"""Independent ecCodes -> conversion -> spatial weights -> Trino comparison."""
import json
import math
from pathlib import Path
import sys
import eccodes as ec
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from app.repositories.gold.client import TrinoClient
ROOT=Path(__file__).resolve().parents[1]
import argparse
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--schema',default='gold_test_medallion_hourly')
parser.add_argument('--output',type=Path,default=ROOT/'reports/medallion_migration/numerical-gold.json')
args=parser.parse_args()
if not args.schema.replace('_','').isalnum():raise ValueError('Unsafe schema')
client=TrinoClient('http://127.0.0.1:8083',timeout=90)
prefix='iceberg.'+args.schema+'.'
release=client.query('SELECT * FROM '+prefix+"gold_current_release WHERE channel='air_quality'")[0]
rid=release['release_id']
weights=client.query('SELECT location_id,grid_point_id,area_fraction FROM '+prefix+'bridge_cams_region_weight')
byloc={}
for w in weights:byloc.setdefault(w['location_id'],[]).append((w['grid_point_id'],w['area_fraction']))
native={};pv=None
for path in sorted((ROOT/'data/landing/CAMS/EAC4').glob('*.grib')):
    key=path.name.split('_2003')[0]
    values=[]
    with path.open('rb') as stream:
        for _ in range(3):
            h=ec.codes_grib_new_from_file(stream)
            try:
                values.append(ec.codes_get_values(h))
                if key=='co':pv=ec.codes_get_array(h,'pv')
            finally:ec.codes_release(h)
    native[key]=values
units={'aod550':('1',1.,0.),**{k:('mg/m2',1e6,0.) for k in ('co_column','no2_column','so2_column','o3_column')},**{k:('degC',1.,-273.15) for k in ('t2m','d2m','t_model')},**{k:('hPa',.01,0.) for k in ('sp','mslp')},**{k:('m/s',1.,0.) for k in ('u10','v10')},'q_model':('kg/kg',1.,0.),**{k:('ug/m3',1e9,0.) for k in ('pm1','pm2p5','pm10')}}
facts=client.query('SELECT series_id,hour_start_utc,value,m.pollutant metric FROM '+prefix+'fact_air_quality_hourly f JOIN '+prefix+'dim_metric m ON f.metric_id=m.metric_id AND f.release_id=m.release_id WHERE f.release_id=\''+rid+'\'')
locations={r['series_id']:r['location_id'] for r in client.query('SELECT series_id,location_id FROM '+prefix+"dim_air_quality_series WHERE release_id='"+rid+"'")}
for f in facts:f['location_id']=locations[f['series_id']]
facts+=client.query('SELECT location_id,hour_start_utc,value,metric FROM '+prefix+"fact_environmental_hourly WHERE release_id='"+rid+"'")
errors=[];examples=[]
for row in facts:
    metric='pm2p5' if row['metric']=='pm25' else row['metric']
    hour=int(row['hour_start_utc'][11:13])
    points=byloc[row['location_id']]
    coverage=sum(w for _,w in points)
    expected=0.
    for point,w in points:
        value=float(native[metric][hour][point])
        if metric in ('co','no2','o3','so2'):
            sp=float(native['sp'][hour][point]);t=float(native['t_model'][hour][point]);q=float(native['q_model'][hour][point])
            p=((pv[59]+pv[120]*sp)+(pv[60]+pv[121]*sp))/2
            value*=p/(287.05*t*(1+(1-.621981)/.621981*q))*1e9
        else:
            _,factor,offset=units[metric];value=value*factor+offset
        expected+=value*w
    expected/=coverage
    assert row['value'] is not None
    error=abs(row['value']-expected)/max(1.,abs(expected))
    errors.append(error)
    assert error<1e-6,(row,expected,error)
    if metric not in {e['metric'] for e in examples}:examples.append(dict(metric=metric,native_point_0=float(native[metric][hour][0]),gold=row['value'],independent_area_mean=expected,spatial_weight_sum=coverage,relative_error=error))
assert len(facts)==34*3*20,len(facts)
assert client.query('SELECT count(*) n FROM '+prefix+"fact_aqi_hourly WHERE release_id='"+rid+"' AND aqi IS NOT NULL")[0]['n']==0
period_checks={}
for grain in ('daily','monthly'):
    # Pilot is contained in one local day and one month. Compare sufficient statistics.
    query="SELECT count(*) n FROM "+prefix+'mart_environmental_'+grain+" m JOIN (SELECT location_id,metric,sum(value) s,count(value) n FROM "+prefix+"fact_environmental_hourly WHERE release_id='"+rid+"' GROUP BY 1,2) h ON m.location_id=h.location_id AND m.metric=h.metric WHERE m.release_id='"+rid+"' AND (m.valid_samples<>h.n OR abs(m.value_sum-h.s)>1e-8 OR abs(m.value-h.s/h.n)>1e-8)"
    assert client.query(query)[0]['n']==0
    period_checks[grain]='passed_sum_count_average'
files=client.query('SELECT count(*) files,sum(file_size_in_bytes) bytes FROM '+prefix+'"fact_environmental_hourly$files"')
out=dict(period_checks=period_checks,environmental_storage=files,release_id=rid,compared_values=len(facts),metrics=len(examples),max_relative_error=max(errors),examples=examples,release=release)
args.output.write_text(json.dumps(out,indent=2))
print(json.dumps({k:v for k,v in out.items() if k not in ('examples','release')}))
