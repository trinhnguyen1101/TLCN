"""Server-side checksum equivalence, excluding only release identity."""
import json
import sys
import time
from trino_probe import query
left,right=sys.argv[1:3]
if not all(s.startswith('gold_test_') and s.replace('_','').isalnum() for s in [left,right]):raise ValueError('Isolated schemas required')
releases={schema:query('SELECT * FROM iceberg.'+schema+'.gold_current_release')[0] for schema in [left,right]}
result={}
for name in json.loads(releases[left]['output_snapshots_json']):
    columns=[r['column_name'] for r in query("SELECT column_name FROM iceberg.information_schema.columns WHERE table_schema='"+left+"' AND table_name='"+name+"' ORDER BY ordinal_position") if r['column_name']!='release_id']
    approximate=[c for c in columns if name in ('mart_air_quality_daily','mart_air_quality_monthly') and c in ('value','concentration_sum','coverage','completeness_ratio')]
    exact=[c for c in columns if c not in approximate]
    checks={}
    for schema in [left,right]:
        release=releases[schema];snapshots=json.loads(release['output_snapshots_json'])
        sql='SELECT count(*) n,to_hex(checksum(ROW('+','.join('"'+c+'"' for c in exact)+'))) checksum FROM iceberg.'+schema+'.'+name+' FOR VERSION AS OF '+str(snapshots[name])+" WHERE release_id='"+release['release_id']+"'"
        checks[schema]=query(sql)[0]
    if checks[left]!=checks[right]:raise AssertionError((name,checks))
    result[name]=dict(checks[left],exact_fields=len(exact))
    if approximate:
        key=['series_id','pollutant','aqi_date_local' if name.endswith('daily') else 'month_local']
        ctes=[]
        for alias,schema in [('l',left),('r',right)]:
            release=releases[schema];snapshot=json.loads(release['output_snapshots_json'])[name]
            ctes.append(alias+' AS (SELECT * FROM iceberg.'+schema+'.'+name+' FOR VERSION AS OF '+str(snapshot)+" WHERE release_id='"+release['release_id']+"')")
        stats=['count(*) n']
        for field in approximate:
            l,r='l.'+field,'r.'+field
            stats+=['max(abs('+l+'-'+r+')) '+field+'_delta',
                'count_if(('+l+' IS NULL AND '+r+' IS NOT NULL) OR ('+r+' IS NULL AND '+l+' IS NOT NULL) OR abs('+l+'-'+r+')>1e-9+1e-12*greatest(abs('+l+'),abs('+r+'))) '+field+'_bad']
        joined=query('WITH '+','.join(ctes)+' SELECT '+','.join(stats)+' FROM l FULL JOIN r USING('+','.join(key)+')')[0]
        assert joined['n']==checks[left]['n'],joined
        assert not any(joined[f+'_bad'] for f in approximate),joined
        result[name]['float_reduction_check']=joined
result['comparison_policy']=dict(raw_facts_aqi_lineage='exact checksums',sql_float_reductions='absolute 1e-9 + relative 1e-12 only; NULLs and all other fields exact')
print('BENCHMARK_EQUIVALENCE '+json.dumps(result,sort_keys=True),flush=True)
