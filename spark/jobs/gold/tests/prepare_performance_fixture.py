"""Generate benchmark data with Spark, not a large Python driver list. TEST ONLY."""
import argparse
from datetime import date
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from runtime import spark_session,snapshot,identifier
from aqi.engine import local_day_bounds
from pyspark.sql import functions as F

p=argparse.ArgumentParser();p.add_argument('--namespace',required=True,type=identifier)
p.add_argument('--provinces',type=int,choices=[1,34],default=34);p.add_argument('--days',type=int,default=31)
p.add_argument('--start-date',default='2026-05-01');a=p.parse_args()
if not a.namespace.startswith('gold_test') or not 1<=a.days<=31:raise ValueError('Isolated bounded fixture required')
spark=spark_session()
try:
    prefix='nessie.'+a.namespace+'.';spark.sql('CREATE NAMESPACE IF NOT EXISTS nessie.'+a.namespace)
    for name in ['admin_unit','admin_boundary','ingestion_run']:
        if not spark.catalog.tableExists(prefix+name):
            pinned=snapshot(spark,'nessie.silver.'+name)
            spark.sql('CREATE TABLE '+prefix+name+" USING iceberg LOCATION 's3a://lakehouse/"+a.namespace+'/'+name+"' AS SELECT * FROM nessie.silver."+name+' VERSION AS OF '+str(pinned))
            print('FIXTURE_GEOGRAPHY '+name+' snapshot='+str(pinned),flush=True)
    table=prefix+'hourly_concentration'
    if spark.catalog.tableExists(table):
        print('FIXTURE_REPLAY '+str(spark.table(table).count()),flush=True)
    else:
        start=local_day_bounds(date.fromisoformat(a.start_date))[0]
        admins=spark.table(prefix+'admin_unit').where('is_current AND parent_code IS NULL').select('admin_code').distinct().orderBy('admin_code').limit(a.provinces)
        if admins.count()!=a.provinces:raise ValueError('Expected real reporting geography')
        hours=spark.range(-11,a.days*24).select(F.col('id').alias('slot'))
        pollutants=spark.createDataFrame([('pm25',25.),('pm10',40.),('co',300.),('no2',20.),('so2',10.),('o3',60.)],['pollutant','base'])
        rows=hours.crossJoin(F.broadcast(admins)).crossJoin(F.broadcast(pollutants))
        rows=rows.withColumn('hour_start_utc',(F.lit(int(start.timestamp()))+F.col('slot')*3600).cast('timestamp'))
        # Missing PM and O3 slots are physically absent. Source NULL/QC invalid
        # remain present records, allowing missingness to be distinguished.
        absent=((F.col('admin_code')=='01') & (F.col('slot')==36) & (F.col('pollutant')=='pm25')) | ((F.col('admin_code')=='48') & (F.col('slot')==47) & (F.col('pollutant')=='o3'))
        invalid=(F.col('admin_code')=='01') & (F.col('slot')==12) & (F.col('pollutant')=='so2')
        missing=(F.col('admin_code')=='01') & (F.col('slot')==13) & (F.col('pollutant')=='no2')
        rows=(rows.filter(~absent).select(
            F.lit('benchmark_hourly_only').alias('dataset_id'),'admin_code','pollutant','hour_start_utc',
            (F.col('hour_start_utc')+F.expr('INTERVAL 1 HOUR')).alias('observed_at_utc'),
            F.when(missing,F.lit(None).cast('double')).otherwise(F.col('base')+F.pmod('slot',F.lit(24))*0.1).alias('value'),
            F.lit('ug/m3').alias('unit'),F.lit(60).alias('source_resolution_minutes'),F.lit('hourly_mean').alias('temporal_support'),
            F.lit('area_estimate').alias('spatial_representation'),F.lit('model_surface').alias('vertical_support'),
            F.lit(False).alias('reference_eligible'),F.when(invalid,'invalid').when(missing,'missing').otherwise('ok').alias('quality_status'),
            F.when(missing,'source_missing_value').otherwise(F.lit(None).cast('string')).alias('missing_reason'),
            F.lit(1.).alias('spatial_coverage_ratio'),F.lit(1).alias('grid_cells'),F.lit(1.).alias('effective_cells'),
            F.array(F.lit('fixture_hourly_benchmark')).alias('input_run_ids'),F.lit('benchmark-hourly-v1').alias('source_version'),
            (F.col('hour_start_utc')+F.expr('INTERVAL 65 MINUTES')).alias('collected_at_utc'),
            (F.col('hour_start_utc')+F.expr('INTERVAL 1 HOUR')).alias('scheduled_at_utc'),
            F.col('hour_start_utc').alias('measurement_start_utc'),(F.col('hour_start_utc')+F.expr('INTERVAL 1 HOUR')).alias('measurement_end_utc'),
            F.lit('interval_end').alias('observation_time_kind')))
        rows.coalesce(2).writeTo(table).using('iceberg').tableProperty('format-version','2').tableProperty('write.parquet.compression-codec','zstd').tableProperty('location','s3a://lakehouse/'+a.namespace+'/hourly_concentration').create()
        print('FIXTURE_ROWS '+str(spark.table(table).count()),flush=True)
finally:spark.stop()
