from trino_probe import query
import json
left='gold_test_perf_before34d7';right='gold_test_perf_after34d7'
rels={s:query('SELECT release_id FROM iceberg.'+s+'.gold_current_release')[0]['release_id'] for s in [left,right]}
sql="SELECT l.series_id,l.pollutant,l.aqi_date_local,l.value left_value,r.value right_value,l.concentration_sum left_sum,r.concentration_sum right_sum,l.aqi left_aqi,r.aqi right_aqi FROM iceberg."+left+".mart_air_quality_daily l JOIN iceberg."+right+".mart_air_quality_daily r ON l.series_id=r.series_id AND l.pollutant=r.pollutant AND l.aqi_date_local=r.aqi_date_local WHERE l.release_id='"+rels[left]+"' AND r.release_id='"+rels[right]+"' AND (l.value IS DISTINCT FROM r.value OR l.concentration_sum IS DISTINCT FROM r.concentration_sum) LIMIT 5"
print(json.dumps(query(sql),indent=2))
