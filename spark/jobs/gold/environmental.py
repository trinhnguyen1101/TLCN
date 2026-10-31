"""Non-AQI intensive CAMS metrics; area means then sample-weighted periods.

Column mass is an areal density, never a volume concentration. Wind components
are averaged separately, never interpreted as direction. No accumulated fields
are admitted by this version. Signed temperature/wind values are valid.
"""
import json
from pyspark.sql import functions as F

POLICIES = {
    'pm1': ('ug/m3','mass_concentration'),
    **{c:('mg/m2','column_mass') for c in ('co_column','no2_column','so2_column','o3_column')},
    **{c:('degC','temperature') for c in ('t2m','d2m','t_model')},
    **{c:('hPa','pressure') for c in ('sp','mslp')},
    **{c:('m/s','wind_component') for c in ('u10','v10')},
    'q_model':('kg/kg','specific_humidity'), 'aod550':('1','optical_depth'),
}

def materialize_environmental(build,dataset_id):
    table=build.prefix+'fact_environmental_hourly'
    # Additive evolution leaves older release snapshots readable.
    for column,kind in [('vertical_support','STRING'),('source_resolution_minutes','INT'),('quality_status','STRING'),('missing_reason','STRING')]:
        if column not in build.spark.table(table).columns:
            build.spark.sql('ALTER TABLE '+table+' ADD COLUMN '+column+' '+kind)
    source=build.read('cams_cube_standard_source').filter(F.col('dataset_id')==dataset_id)
    success=build.read('ingestion_run').filter("status='succeeded'").select(F.col('run_id').alias('ingestion_run_id'))
    metadata=source.join(success,'ingestion_run_id').collect()
    for metric,(unit,quantity) in POLICIES.items():
        rows=[r for r in metadata if r.column_name==metric]
        if not rows or any(r.standard_unit!=unit or r.quality_status!='validated' or json.loads(r.conversion_metadata)['source_time']['stepType']!='instant' for r in rows):
            raise ValueError('Environmental Silver unit/statistic unverified: '+metric)
    cube=build.read('cams_cube_standard').filter((F.col('dataset_id')==dataset_id)&(F.col('valid_time')>=F.lit(build.start))&(F.col('valid_time')<F.lit(build.end))).join(success,'ingestion_run_id')
    joined=cube.join(F.broadcast(build.bridge),'grid_id')
    frames=[]
    for metric,(unit,quantity) in POLICIES.items():
        value=F.element_at(F.col(metric),F.col('grid_point_id').cast('int')+1).cast('double')
        ok=value.isNotNull()&(~F.isnan(value))&(F.abs(value)!=float('inf'))
        if quantity not in ('temperature','wind_component'):ok=ok&(value>=0)
        frames.append(joined.select('valid_time','location_id','ingestion_run_id','area_fraction',F.lit(metric).alias('metric'),F.lit(unit).alias('unit'),F.lit(quantity).alias('physical_quantity'),F.when(ok,value).alias('v')))
    data=frames[0]
    for frame in frames[1:]:data=data.unionByName(frame)
    grouped=data.groupBy('valid_time','location_id','metric','unit','physical_quantity').agg(F.sum(F.col('v')*F.col('area_fraction')).alias('numerator'),F.sum(F.when(F.col('v').isNotNull(),F.col('area_fraction')).otherwise(0.)).alias('spatial_coverage'),F.sort_array(F.collect_set('ingestion_run_id')).alias('input_run_ids'))
    hourly=grouped.select(F.lit(build.release_id).alias('release_id'),F.lit(dataset_id).alias('dataset_id'),'location_id',F.col('valid_time').alias('hour_start_utc'),'metric','unit','physical_quantity',F.when(F.col('spatial_coverage')>=build.contract['minimum_spatial_coverage'],F.col('numerator')/F.col('spatial_coverage')).alias('value'),'spatial_coverage','input_run_ids',F.lit(build.inputs[build.silver+'cams_cube_standard']).cast('long').alias('input_snapshot_id'),F.lit('instantaneous').alias('temporal_support'),F.lit('area_intensive_mean_v1').alias('aggregation_policy'),F.when(F.col('metric').isin('t_model','q_model'),F.lit('model_level_60')).when(F.col('metric').endswith('_column') | (F.col('metric')=='aod550'),F.lit('atmospheric_column')).when(F.col('metric').isin('t2m','d2m'),F.lit('height_2m')).when(F.col('metric').isin('u10','v10'),F.lit('height_10m')).otherwise(F.lit('surface_field')).alias('vertical_support'),F.lit(build.contract['source_resolution_minutes']).alias('source_resolution_minutes'))
    hourly=hourly.withColumn('quality_status',F.when(F.col('value').isNotNull(),F.lit('ok')).otherwise(F.lit('insufficient_spatial_coverage'))).withColumn('missing_reason',F.when(F.col('value').isNull(),F.lit('spatial_coverage_below_policy')))
    build.write('fact_environmental_hourly',hourly)
    rows=build.rows('fact_environmental_hourly')
    if rows.groupBy('dataset_id','location_id','hour_start_utc','metric').count().filter('count>1').limit(1).count():raise ValueError('Duplicate environmental observation')
    if rows.filter(F.isnan('value')|(F.abs(F.col('value'))==float('inf'))).limit(1).count():raise ValueError('Nonfinite environmental value')
    for grain,expr in [('daily',F.to_date(F.from_utc_timestamp('hour_start_utc','Asia/Ho_Chi_Minh'))),('monthly',F.to_date(F.date_trunc('month',F.from_utc_timestamp('hour_start_utc','Asia/Ho_Chi_Minh'))))]:
        mart=rows.withColumn('period_start_local',expr).groupBy('release_id','dataset_id','location_id','metric','unit','physical_quantity','period_start_local').agg(F.sum('value').alias('value_sum'),F.count('value').alias('valid_samples'),F.min('value').alias('minimum'),F.max('value').alias('maximum')).withColumn('value',F.col('value_sum')/F.when(F.col('valid_samples')>0,F.col('valid_samples'))).withColumn('aggregation_policy',F.lit('available_instantaneous_samples_v1'))
        build.write('mart_environmental_'+grain,mart)
