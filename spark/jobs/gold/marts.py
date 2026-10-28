"""Materialized hourly/daily/monthly/quality marts. Long grain avoids join fanout."""
from pyspark.sql import functions as F
from aqi.reference import METHOD_VERSION


def materialize(build):
    spark=build.spark
    for name in ("fact_air_quality_hourly","dim_air_quality_series","dim_location","dim_metric",
                 "fact_aqi_hourly","fact_aqi_daily","fact_aqi_pollutant_hourly","fact_aqi_pollutant_daily","dim_hour"):
        build.rows(name).createOrReplaceTempView("g_"+name)
    # Expected spine only in selected serving mart, never dense concentration facts.
    start=build.start.strftime("%Y-%m-%d %H:%M:%S")
    end=build.end.strftime("%Y-%m-%d %H:%M:%S")
    expected_scope=('SELECT s.series_id,m.metric_id FROM g_dim_air_quality_series s CROSS JOIN g_dim_metric m'
                    if build.contract.get('metric_policies') or build.contract.get('pollutants')
                    else 'SELECT DISTINCT series_id,metric_id FROM g_fact_air_quality_hourly')
    hourly=spark.sql(f"""
    SELECT s.release_id,s.series_id,s.location_id,l.admin_code,s.source_system source,
           s.source_resolution_minutes,s.temporal_support,l.spatial_representation,s.applicability_profile,
           m.pollutant,m.unit,f.value,coalesce(f.quality_status,'missing') quality_status,
           CASE WHEN f.hour_start_utc IS NULL THEN 'no_source_observation' ELSE f.missing_reason END missing_reason,
           f.spatial_coverage_ratio coverage,a.aqi,a.category aqi_category,a.color aqi_color,
           a.dominant_pollutants,a.method_version aqi_method_version,a.status aqi_status,
           a.missing_reason aqi_missing_reason,a.aqi_origin,a.aqi_provider,a.provider_aqi_scheme,
           p.sub_index,cast(NULL AS INT) provider_aqi,
           h.hour_start_utc,f.observed_at_utc observation_time,f.grid_cells,f.effective_cells
    FROM g_dim_air_quality_series s JOIN g_dim_location l ON l.location_id=s.location_id
    CROSS JOIN g_dim_hour h
    JOIN ({expected_scope}) scope ON scope.series_id=s.series_id
    JOIN g_dim_metric m ON m.metric_id=scope.metric_id
    LEFT JOIN g_fact_air_quality_hourly f ON f.series_id=s.series_id AND f.hour_start_utc=h.hour_start_utc AND f.metric_id=m.metric_id
    JOIN g_fact_aqi_hourly a ON a.series_id=s.series_id AND a.hour_start_utc=h.hour_start_utc
    JOIN g_fact_aqi_pollutant_hourly p ON p.series_id=s.series_id AND p.hour_start_utc=h.hour_start_utc AND p.pollutant=m.pollutant
    WHERE h.hour_start_utc>=TIMESTAMP '{start}' AND h.hour_start_utc<TIMESTAMP '{end}'
    """)
    build.write("mart_air_quality_hourly",hourly)
    build.rows("mart_air_quality_hourly").createOrReplaceTempView("g_hourly")
    # Daily values are statistics of available samples, explicitly distinguished
    # from complete mean24h inputs used by the AQI engine.
    daily=spark.sql("""
    WITH stats AS (
      SELECT release_id,series_id,location_id,admin_code,source,source_resolution_minutes,
             temporal_support,spatial_representation,applicability_profile,pollutant,unit,
             to_date(from_utc_timestamp(hour_start_utc,'Asia/Ho_Chi_Minh')) aqi_date_local,
             avg(value) value,sum(value) concentration_sum,count(value) valid_hours,
             min(value) minimum,max(value) maximum,avg(coverage) coverage
      FROM g_hourly GROUP BY ALL
    ), selected AS (
      SELECT series_id,aqi_date_local,pollutant,CASE WHEN pollutant='o3' AND min(input_count)<24 THEN NULL ELSE max(sub_index) END sub_index
      FROM g_fact_aqi_pollutant_daily GROUP BY 1,2,3
    )
    SELECT s.release_id,s.series_id,s.location_id,s.admin_code,s.source,s.source_resolution_minutes,
           s.temporal_support,s.spatial_representation,s.applicability_profile,s.pollutant,s.unit,
           s.value,CASE WHEN s.valid_hours=24 THEN 'complete' WHEN s.valid_hours>0 THEN 'partial' ELSE 'missing' END quality_status,
           CASE WHEN s.valid_hours<24 THEN 'incomplete_hour_slots' END missing_reason,s.coverage,
           a.aqi,a.category aqi_category,a.color aqi_color,a.dominant_pollutants,a.method_version aqi_method_version,
           a.status aqi_status,a.missing_reason aqi_missing_reason,a.aqi_origin,a.aqi_provider,a.provider_aqi_scheme,
           p.sub_index,cast(NULL AS INT) provider_aqi,
           s.aqi_date_local,s.concentration_sum,cast(s.valid_hours AS INT) valid_hours,24 expected_hours,
           cast(24-s.valid_hours AS INT) missing_hours,s.valid_hours/24.0 completeness_ratio,
           s.minimum,s.maximum,'available_native_samples_v1_calendar_vn' aggregation_policy
    FROM stats s JOIN g_fact_aqi_daily a ON a.series_id=s.series_id AND a.aqi_date_local=s.aqi_date_local
    JOIN selected p ON p.series_id=s.series_id AND p.aqi_date_local=s.aqi_date_local AND p.pollutant=s.pollutant
    """)
    build.write("mart_air_quality_daily",daily)
    build.rows("mart_air_quality_daily").createOrReplaceTempView("g_daily")
    monthly=spark.sql("""
    WITH category_counts AS (
      SELECT series_id,pollutant,cast(date_trunc('month',aqi_date_local) AS DATE) month_local,
             aqi_category,count(*) n FROM g_daily WHERE aqi_category IS NOT NULL GROUP BY 1,2,3,4
    ), categories AS (
      SELECT series_id,pollutant,month_local,map_from_entries(collect_list(struct(aqi_category,n))) counts
      FROM category_counts GROUP BY 1,2,3
    ), stats AS (
      SELECT release_id,series_id,location_id,admin_code,source,pollutant,unit,
             cast(date_trunc('month',aqi_date_local) AS DATE) month_local,
             sum(concentration_sum) concentration_sum,sum(valid_hours) valid_hours,
             cast(day(last_day(min(aqi_date_local)))*24 AS BIGINT) expected_hours,
             count_if(valid_hours=24) valid_days,count_if(aqi IS NOT NULL) aqi_valid_days
      FROM g_daily GROUP BY ALL
    )
    SELECT s.release_id,s.series_id,s.location_id,s.admin_code,s.source,s.pollutant,s.unit,s.month_local,
           s.concentration_sum/nullif(s.valid_hours,0) value,s.concentration_sum,s.valid_hours,s.expected_hours,
           s.valid_days,s.aqi_valid_days,coalesce(c.counts,cast(map() AS MAP<STRING,BIGINT>)) aqi_category_counts,
           s.valid_hours/cast(s.expected_hours AS DOUBLE) completeness_ratio,
           'sample_weighted_month_to_release_scope_v1_calendar_vn' aggregation_policy
    FROM stats s LEFT JOIN categories c USING(series_id,pollutant,month_local)
    """)
    build.write("mart_air_quality_monthly",monthly)
    quality=spark.sql("""
    SELECT release_id,series_id,source,aqi_date_local date_local,pollutant,24 expected_hours,
           cast(count(observation_time) AS INT) observed_slots,
           cast(count(value) AS INT) valid_measurements,
           cast(count_if(quality_status NOT IN ('ok','missing')) AS INT) invalid_measurements,
           cast(24-count(value) AS INT) missing_hours,count(value)/24.0 measurement_coverage,
           max(observation_time) latest_observation_time,source_resolution_minutes,temporal_support,
           cast(NULL AS BIGINT) collection_attempts,cast(NULL AS BIGINT) failed_ingestions,
           'measurement_only_collection_telemetry_unavailable' quality_scope
    FROM g_hourly
    GROUP BY release_id,series_id,source,to_date(from_utc_timestamp(hour_start_utc,'Asia/Ho_Chi_Minh')),
             pollutant,source_resolution_minutes,temporal_support
    """.replace("aqi_date_local date_local","to_date(from_utc_timestamp(hour_start_utc,'Asia/Ho_Chi_Minh')) date_local"))
    build.write("mart_source_quality_daily",quality)
