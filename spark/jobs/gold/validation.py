"""Hard publication gates. Logical keys and FKs are checked by ETL."""
from pyspark.sql import functions as F

KEYS={
    'dim_admin_unit':['admin_unit_version_id'], 'dim_geo_component':['geo_component_id'],
    'dim_location':['location_id'], 'dim_air_quality_series':['series_id'],
    'dim_metric':['metric_id'], 'bridge_source_variable_metric':['dataset_id','variable_id','metric_id'],
    'dim_date':['calendar_date'], 'dim_hour':['hour_start_utc'], 'dim_aqi_method':['method_version'],
    'ref_aqi_breakpoint':['method_version','pollutant','averaging_basis','breakpoint_order'],
    'fact_air_quality_hourly':['series_id','hour_start_utc','metric_id'],
    'fact_measurement_provenance':['series_id','hour_start_utc','metric_id'],
    'fact_aqi_pollutant_hourly':['series_id','hour_start_utc','pollutant','basis','method_version','applicability_profile'],
    'fact_aqi_hourly':['series_id','hour_start_utc','method_version','applicability_profile'],
    'fact_aqi_pollutant_daily':['series_id','aqi_date_local','pollutant','basis','method_version','applicability_profile'],
    'fact_aqi_daily':['series_id','aqi_date_local','method_version','applicability_profile'],
    'mart_air_quality_hourly':['series_id','hour_start_utc','pollutant'],
    'mart_air_quality_daily':['series_id','aqi_date_local','pollutant'],
    'mart_air_quality_monthly':['series_id','month_local','pollutant'],
    'mart_source_quality_daily':['series_id','date_local','pollutant'],
}


def validate(build):
    counts={}
    for name,keys in KEYS.items():
        rows=build.rows(name)
        nullkey=None
        for key in keys:
            nullkey=F.col(key).isNull() if nullkey is None else nullkey|F.col(key).isNull()
        # One grouped aggregate checks count, duplicates and NULL keys in one
        # action. Do not rescan each materialized table three times.
        stats=rows.groupBy(*keys).count().agg(F.sum('count').alias('rows'),F.max('count').alias('largest_key'),
            F.max(F.when(nullkey,1).otherwise(0)).alias('null_key')).first()
        counts[name]=int(stats['rows'] or 0)
        if (stats['largest_key'] or 0)>1:raise ValueError('Duplicate Gold key: '+name)
        if stats['null_key']:raise ValueError('NULL logical key: '+name)
    if 'fact_measurement_provenance' in build.outputs:
        fields=['series_id','hour_start_utc','metric_id']
        if build.rows('fact_measurement_provenance').join(build.rows('fact_air_quality_hourly').select(*fields),fields,'left_anti').limit(1).count():
            raise ValueError('Orphan measurement provenance')
    facts=build.rows('fact_air_quality_hourly')
    if not counts['fact_air_quality_hourly']:
        raise ValueError('Refuse to publish empty source scope')
    if facts.filter((F.col('value').isNull() & F.col('missing_reason').isNull()) |
                    (F.col('value').isNotNull() & F.col('missing_reason').isNotNull()) |
                    F.isnan('value') | (F.abs(F.col('value'))==float('inf')) | (F.col('value')<0) |
                    (F.col('source_resolution_minutes')<=0) |
                    (~F.col('spatial_coverage_ratio').between(0,1.00001))).limit(1).count():
        raise ValueError('Invalid concentration/QC/coverage contract')
    for child,field,parent in [('fact_air_quality_hourly','series_id','dim_air_quality_series'),
                               ('fact_air_quality_hourly','metric_id','dim_metric'),
                               ('fact_air_quality_hourly','hour_start_utc','dim_hour'),
                               ('dim_air_quality_series','location_id','dim_location')]:
        if build.rows(child).join(build.rows(parent).select(field),field,'left_anti').limit(1).count():
            raise ValueError('Orphan Gold reference: '+child+'.'+field)
    for period in ['hourly','daily']:
        table=build.rows('fact_aqi_'+period)
        if table.filter((F.col('aqi').isNull() & F.col('missing_reason').isNull()) |
                        (F.col('aqi').isNotNull() & ((F.col('status')!='valid') | F.col('missing_reason').isNotNull())) |
                        (F.col('aqi')<0) | (F.col('aqi')>500)).count():
            raise ValueError('Invalid AQI status/range')
        if table.filter((F.col('aqi_origin')!='computed') | F.col('aqi_provider').isNotNull()
                        | F.col('provider_aqi_scheme').isNotNull()).limit(1).count():
            raise ValueError('Computed AQI fact has provider origin metadata')
    series_count=counts['dim_air_quality_series']
    expected_hours=int((build.end-build.start).total_seconds()/3600)
    declared_metrics=build.contract.get('metric_policies') or build.contract.get('pollutants')
    if declared_metrics and counts['mart_air_quality_hourly']!=series_count*expected_hours*len(declared_metrics):
        raise ValueError('Missing declared series/hour/pollutant status rows')
    if counts['fact_aqi_hourly']!=series_count*expected_hours:
        raise ValueError('Missing AQI hour status rows')
    if build.rows('mart_air_quality_daily').filter('valid_hours+missing_hours<>24').count():
        raise ValueError('Incorrect daily slot completeness')
    counts['aqi_hourly_valid']=build.rows('fact_aqi_hourly').filter('aqi IS NOT NULL').count()
    counts['aqi_daily_valid']=build.rows('fact_aqi_daily').filter('aqi IS NOT NULL').count()
    return counts
