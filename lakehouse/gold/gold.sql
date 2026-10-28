-- Spark 3.5 / Iceberg 1.7.1. Replace {{schema}} only with validated identifier.
CREATE NAMESPACE IF NOT EXISTS nessie.{{schema}};

CREATE TABLE IF NOT EXISTS nessie.{{schema}}.dim_admin_unit (
    release_id STRING NOT NULL,
    admin_unit_version_id STRING NOT NULL,
    admin_code STRING NOT NULL,
    name_vi STRING NOT NULL,
    parent_admin_unit_version_id STRING,
    admin_level INT NOT NULL,
    snapshot_date DATE NOT NULL,
    boundary_hash STRING
) USING iceberg
PARTITIONED BY (release_id)
LOCATION 's3a://lakehouse/{{schema}}/dim_admin_unit'
TBLPROPERTIES ('format-version'='2', 'write.parquet.compression-codec'='zstd', 'write.target-file-size-bytes'='134217728');

CREATE TABLE IF NOT EXISTS nessie.{{schema}}.dim_geo_component (
    release_id STRING NOT NULL,
    geo_component_id STRING NOT NULL,
    parent_admin_unit_version_id STRING NOT NULL,
    component_kind STRING NOT NULL,
    component_name STRING NOT NULL,
    geometry_hash STRING NOT NULL,
    area_m2 DOUBLE NOT NULL,
    boundary_wkb BINARY NOT NULL,
    geography_policy_version STRING NOT NULL
) USING iceberg
PARTITIONED BY (release_id)
LOCATION 's3a://lakehouse/{{schema}}/dim_geo_component'
TBLPROPERTIES ('format-version'='2', 'write.parquet.compression-codec'='zstd', 'write.target-file-size-bytes'='134217728');

CREATE TABLE IF NOT EXISTS nessie.{{schema}}.dim_location (
    release_id STRING NOT NULL,
    location_id STRING NOT NULL,
    admin_unit_version_id STRING,
    name STRING NOT NULL,
    admin_code STRING,
    location_kind STRING NOT NULL,
    spatial_representation STRING NOT NULL,
    mapping_status STRING NOT NULL
) USING iceberg
PARTITIONED BY (release_id)
LOCATION 's3a://lakehouse/{{schema}}/dim_location'
TBLPROPERTIES ('format-version'='2', 'write.parquet.compression-codec'='zstd', 'write.target-file-size-bytes'='134217728');

CREATE TABLE IF NOT EXISTS nessie.{{schema}}.dim_air_quality_series (
    release_id STRING NOT NULL,
    series_id STRING NOT NULL,
    dataset_id STRING NOT NULL,
    location_id STRING NOT NULL,
    source_system STRING NOT NULL,
    source_contract_version STRING NOT NULL,
    source_resolution_minutes INT NOT NULL,
    temporal_support STRING NOT NULL,
    applicability_profile STRING NOT NULL,
    spatial_policy_version STRING NOT NULL
) USING iceberg
PARTITIONED BY (release_id)
LOCATION 's3a://lakehouse/{{schema}}/dim_air_quality_series'
TBLPROPERTIES ('format-version'='2', 'write.parquet.compression-codec'='zstd', 'write.target-file-size-bytes'='134217728');

CREATE TABLE IF NOT EXISTS nessie.{{schema}}.dim_metric (
    release_id STRING NOT NULL,
    metric_id STRING NOT NULL,
    pollutant STRING NOT NULL,
    measurement_kind STRING NOT NULL,
    unit STRING NOT NULL,
    vertical_support STRING NOT NULL,
    unit_policy_version STRING NOT NULL
) USING iceberg
PARTITIONED BY (release_id)
LOCATION 's3a://lakehouse/{{schema}}/dim_metric'
TBLPROPERTIES ('format-version'='2', 'write.parquet.compression-codec'='zstd', 'write.target-file-size-bytes'='134217728');

CREATE TABLE IF NOT EXISTS nessie.{{schema}}.bridge_source_variable_metric (
    release_id STRING NOT NULL,
    dataset_id STRING NOT NULL,
    variable_id STRING NOT NULL,
    source_column STRING NOT NULL,
    metric_id STRING NOT NULL,
    source_unit STRING NOT NULL,
    standard_unit STRING NOT NULL,
    metric_policy_version STRING NOT NULL
) USING iceberg
PARTITIONED BY (release_id)
LOCATION 's3a://lakehouse/{{schema}}/bridge_source_variable_metric'
TBLPROPERTIES ('format-version'='2', 'write.parquet.compression-codec'='zstd', 'write.target-file-size-bytes'='134217728');

CREATE TABLE IF NOT EXISTS nessie.{{schema}}.dim_date (
    release_id STRING NOT NULL,
    calendar_date DATE NOT NULL,
    calendar_year INT NOT NULL,
    calendar_month INT NOT NULL,
    calendar_quarter INT NOT NULL,
    days_in_month INT NOT NULL
) USING iceberg
PARTITIONED BY (release_id)
LOCATION 's3a://lakehouse/{{schema}}/dim_date'
TBLPROPERTIES ('format-version'='2', 'write.parquet.compression-codec'='zstd', 'write.target-file-size-bytes'='134217728');

CREATE TABLE IF NOT EXISTS nessie.{{schema}}.dim_hour (
    release_id STRING NOT NULL,
    hour_start_utc TIMESTAMP NOT NULL,
    hour_end_utc TIMESTAMP NOT NULL,
    date_utc DATE NOT NULL,
    date_vn DATE NOT NULL,
    hour_vn INT NOT NULL
) USING iceberg
PARTITIONED BY (release_id)
LOCATION 's3a://lakehouse/{{schema}}/dim_hour'
TBLPROPERTIES ('format-version'='2', 'write.parquet.compression-codec'='zstd', 'write.target-file-size-bytes'='134217728');

CREATE TABLE IF NOT EXISTS nessie.{{schema}}.dim_aqi_method (
    release_id STRING NOT NULL,
    method_version STRING NOT NULL,
    reference_url STRING NOT NULL,
    reference_sha256 STRING NOT NULL,
    calendar_timezone STRING NOT NULL,
    policies_json STRING NOT NULL
) USING iceberg
PARTITIONED BY (release_id)
LOCATION 's3a://lakehouse/{{schema}}/dim_aqi_method'
TBLPROPERTIES ('format-version'='2', 'write.parquet.compression-codec'='zstd', 'write.target-file-size-bytes'='134217728');

CREATE TABLE IF NOT EXISTS nessie.{{schema}}.ref_aqi_breakpoint (
    release_id STRING NOT NULL,
    method_version STRING NOT NULL,
    pollutant STRING NOT NULL,
    averaging_basis STRING NOT NULL,
    breakpoint_order INT NOT NULL,
    concentration_breakpoint DOUBLE NOT NULL,
    index_breakpoint INT NOT NULL
) USING iceberg
PARTITIONED BY (release_id)
LOCATION 's3a://lakehouse/{{schema}}/ref_aqi_breakpoint'
TBLPROPERTIES ('format-version'='2', 'write.parquet.compression-codec'='zstd', 'write.target-file-size-bytes'='134217728');

CREATE TABLE IF NOT EXISTS nessie.{{schema}}.fact_air_quality_hourly (
    release_id STRING NOT NULL,
    series_id STRING NOT NULL,
    hour_start_utc TIMESTAMP NOT NULL,
    metric_id STRING NOT NULL,
    pollutant STRING NOT NULL,
    value DOUBLE,
    unit STRING NOT NULL,
    observed_at_utc TIMESTAMP NOT NULL,
    source_resolution_minutes INT NOT NULL,
    temporal_support STRING NOT NULL,
    spatial_representation STRING NOT NULL,
    vertical_support STRING NOT NULL,
    reference_eligible BOOLEAN NOT NULL,
    source_dataset STRING NOT NULL,
    quality_status STRING NOT NULL,
    missing_reason STRING,
    spatial_coverage_ratio DOUBLE,
    grid_cells INT,
    effective_cells DOUBLE,
    input_run_ids ARRAY<STRING> NOT NULL,
    input_snapshot_id BIGINT NOT NULL
) USING iceberg
PARTITIONED BY (release_id, months(hour_start_utc))
LOCATION 's3a://lakehouse/{{schema}}/fact_air_quality_hourly'
TBLPROPERTIES ('format-version'='2', 'write.parquet.compression-codec'='zstd', 'write.target-file-size-bytes'='134217728');

CREATE TABLE IF NOT EXISTS nessie.{{schema}}.fact_aqi_pollutant_hourly (
    release_id STRING NOT NULL,
    series_id STRING NOT NULL,
    pollutant STRING NOT NULL,
    basis STRING NOT NULL,
    concentration DOUBLE,
    sub_index INT,
    raw_index DOUBLE,
    bp_low DOUBLE,
    bp_high DOUBLE,
    index_low INT,
    index_high INT,
    input_count INT NOT NULL,
    expected_count INT NOT NULL,
    completeness DOUBLE NOT NULL,
    weight DOUBLE,
    window_start TIMESTAMP NOT NULL,
    window_end TIMESTAMP NOT NULL,
    status STRING NOT NULL,
    missing_reason STRING,
    method_version STRING NOT NULL,
    applicability_profile STRING NOT NULL,
    input_lineage_json STRING NOT NULL,
    hour_start_utc TIMESTAMP NOT NULL
) USING iceberg
PARTITIONED BY (release_id, months(hour_start_utc))
LOCATION 's3a://lakehouse/{{schema}}/fact_aqi_pollutant_hourly'
TBLPROPERTIES ('format-version'='2', 'write.parquet.compression-codec'='zstd', 'write.target-file-size-bytes'='134217728');

CREATE TABLE IF NOT EXISTS nessie.{{schema}}.fact_aqi_hourly (
    release_id STRING NOT NULL,
    series_id STRING NOT NULL,
    aqi INT,
    dominant_pollutants ARRAY<STRING> NOT NULL,
    status STRING NOT NULL,
    missing_reason STRING,
    category STRING,
    category_label STRING,
    color STRING,
    method_version STRING NOT NULL,
    applicability_profile STRING NOT NULL,
    input_lineage_json STRING NOT NULL,
    hour_start_utc TIMESTAMP NOT NULL
) USING iceberg
PARTITIONED BY (release_id, months(hour_start_utc))
LOCATION 's3a://lakehouse/{{schema}}/fact_aqi_hourly'
TBLPROPERTIES ('format-version'='2', 'write.parquet.compression-codec'='zstd', 'write.target-file-size-bytes'='134217728');

CREATE TABLE IF NOT EXISTS nessie.{{schema}}.fact_aqi_pollutant_daily (
    release_id STRING NOT NULL,
    series_id STRING NOT NULL,
    pollutant STRING NOT NULL,
    basis STRING NOT NULL,
    concentration DOUBLE,
    sub_index INT,
    raw_index DOUBLE,
    bp_low DOUBLE,
    bp_high DOUBLE,
    index_low INT,
    index_high INT,
    input_count INT NOT NULL,
    expected_count INT NOT NULL,
    completeness DOUBLE NOT NULL,
    weight DOUBLE,
    window_start TIMESTAMP NOT NULL,
    window_end TIMESTAMP NOT NULL,
    status STRING NOT NULL,
    missing_reason STRING,
    method_version STRING NOT NULL,
    applicability_profile STRING NOT NULL,
    input_lineage_json STRING NOT NULL,
    aqi_date_local DATE NOT NULL
) USING iceberg
PARTITIONED BY (release_id, months(aqi_date_local))
LOCATION 's3a://lakehouse/{{schema}}/fact_aqi_pollutant_daily'
TBLPROPERTIES ('format-version'='2', 'write.parquet.compression-codec'='zstd', 'write.target-file-size-bytes'='134217728');

CREATE TABLE IF NOT EXISTS nessie.{{schema}}.fact_aqi_daily (
    release_id STRING NOT NULL,
    series_id STRING NOT NULL,
    aqi INT,
    dominant_pollutants ARRAY<STRING> NOT NULL,
    status STRING NOT NULL,
    missing_reason STRING,
    category STRING,
    category_label STRING,
    color STRING,
    method_version STRING NOT NULL,
    applicability_profile STRING NOT NULL,
    input_lineage_json STRING NOT NULL,
    aqi_date_local DATE NOT NULL
) USING iceberg
PARTITIONED BY (release_id, months(aqi_date_local))
LOCATION 's3a://lakehouse/{{schema}}/fact_aqi_daily'
TBLPROPERTIES ('format-version'='2', 'write.parquet.compression-codec'='zstd', 'write.target-file-size-bytes'='134217728');

CREATE TABLE IF NOT EXISTS nessie.{{schema}}.mart_air_quality_hourly (
    release_id STRING NOT NULL,
    series_id STRING NOT NULL,
    location_id STRING NOT NULL,
    admin_code STRING,
    source STRING NOT NULL,
    source_resolution_minutes INT NOT NULL,
    temporal_support STRING NOT NULL,
    spatial_representation STRING NOT NULL,
    applicability_profile STRING NOT NULL,
    pollutant STRING NOT NULL,
    unit STRING NOT NULL,
    value DOUBLE,
    quality_status STRING NOT NULL,
    missing_reason STRING,
    coverage DOUBLE,
    aqi INT,
    aqi_category STRING,
    aqi_color STRING,
    dominant_pollutants ARRAY<STRING> NOT NULL,
    aqi_method_version STRING NOT NULL,
    aqi_status STRING NOT NULL,
    aqi_missing_reason STRING,
    aqi_origin STRING NOT NULL,
    sub_index INT,
    provider_aqi INT,
    hour_start_utc TIMESTAMP NOT NULL,
    observation_time TIMESTAMP,
    grid_cells INT,
    effective_cells DOUBLE
) USING iceberg
PARTITIONED BY (release_id, months(hour_start_utc))
LOCATION 's3a://lakehouse/{{schema}}/mart_air_quality_hourly'
TBLPROPERTIES ('format-version'='2', 'write.parquet.compression-codec'='zstd', 'write.target-file-size-bytes'='134217728');

CREATE TABLE IF NOT EXISTS nessie.{{schema}}.mart_air_quality_daily (
    release_id STRING NOT NULL,
    series_id STRING NOT NULL,
    location_id STRING NOT NULL,
    admin_code STRING,
    source STRING NOT NULL,
    source_resolution_minutes INT NOT NULL,
    temporal_support STRING NOT NULL,
    spatial_representation STRING NOT NULL,
    applicability_profile STRING NOT NULL,
    pollutant STRING NOT NULL,
    unit STRING NOT NULL,
    value DOUBLE,
    quality_status STRING NOT NULL,
    missing_reason STRING,
    coverage DOUBLE,
    aqi INT,
    aqi_category STRING,
    aqi_color STRING,
    dominant_pollutants ARRAY<STRING> NOT NULL,
    aqi_method_version STRING NOT NULL,
    aqi_status STRING NOT NULL,
    aqi_missing_reason STRING,
    aqi_origin STRING NOT NULL,
    sub_index INT,
    provider_aqi INT,
    aqi_date_local DATE NOT NULL,
    concentration_sum DOUBLE,
    valid_hours INT NOT NULL,
    expected_hours INT NOT NULL,
    missing_hours INT NOT NULL,
    completeness_ratio DOUBLE NOT NULL,
    minimum DOUBLE,
    maximum DOUBLE,
    aggregation_policy STRING NOT NULL
) USING iceberg
PARTITIONED BY (release_id, months(aqi_date_local))
LOCATION 's3a://lakehouse/{{schema}}/mart_air_quality_daily'
TBLPROPERTIES ('format-version'='2', 'write.parquet.compression-codec'='zstd', 'write.target-file-size-bytes'='134217728');

CREATE TABLE IF NOT EXISTS nessie.{{schema}}.mart_air_quality_monthly (
    release_id STRING NOT NULL,
    series_id STRING NOT NULL,
    location_id STRING NOT NULL,
    admin_code STRING,
    source STRING NOT NULL,
    pollutant STRING NOT NULL,
    unit STRING NOT NULL,
    month_local DATE NOT NULL,
    value DOUBLE,
    concentration_sum DOUBLE,
    valid_hours BIGINT NOT NULL,
    expected_hours BIGINT NOT NULL,
    valid_days BIGINT NOT NULL,
    aqi_valid_days BIGINT NOT NULL,
    aqi_category_counts MAP<STRING,BIGINT> NOT NULL,
    completeness_ratio DOUBLE NOT NULL,
    aggregation_policy STRING NOT NULL
) USING iceberg
PARTITIONED BY (release_id, months(month_local))
LOCATION 's3a://lakehouse/{{schema}}/mart_air_quality_monthly'
TBLPROPERTIES ('format-version'='2', 'write.parquet.compression-codec'='zstd', 'write.target-file-size-bytes'='134217728');

CREATE TABLE IF NOT EXISTS nessie.{{schema}}.mart_source_quality_daily (
    release_id STRING NOT NULL,
    series_id STRING NOT NULL,
    source STRING NOT NULL,
    date_local DATE NOT NULL,
    pollutant STRING NOT NULL,
    expected_hours INT NOT NULL,
    observed_slots INT NOT NULL,
    valid_measurements INT NOT NULL,
    invalid_measurements INT NOT NULL,
    missing_hours INT NOT NULL,
    measurement_coverage DOUBLE NOT NULL,
    latest_observation_time TIMESTAMP,
    source_resolution_minutes INT NOT NULL,
    temporal_support STRING NOT NULL,
    collection_attempts BIGINT,
    failed_ingestions BIGINT,
    quality_scope STRING NOT NULL
) USING iceberg
PARTITIONED BY (release_id, months(date_local))
LOCATION 's3a://lakehouse/{{schema}}/mart_source_quality_daily'
TBLPROPERTIES ('format-version'='2', 'write.parquet.compression-codec'='zstd', 'write.target-file-size-bytes'='134217728');

-- Immutable cache keyed by geometry/grid/method, reused across releases.
CREATE TABLE IF NOT EXISTS nessie.{{schema}}.bridge_cams_region_weight (
    cache_key STRING NOT NULL, grid_id STRING NOT NULL, grid_point_id BIGINT NOT NULL,
    location_id STRING NOT NULL, boundary_hash STRING NOT NULL, method_version STRING NOT NULL,
    intersection_area_m2 DOUBLE NOT NULL, region_area_m2 DOUBLE NOT NULL,
    area_fraction DOUBLE NOT NULL, latitude_increment DOUBLE NOT NULL, longitude_increment DOUBLE NOT NULL
) USING iceberg
LOCATION 's3a://lakehouse/{{schema}}/bridge_cams_region_weight'
TBLPROPERTIES ('format-version'='2', 'write.parquet.compression-codec'='zstd');

CREATE TABLE IF NOT EXISTS nessie.{{schema}}.gold_release (
    release_id STRING NOT NULL, channel STRING NOT NULL, scope_start_utc TIMESTAMP NOT NULL,
    scope_end_utc TIMESTAMP NOT NULL, input_snapshots_json STRING NOT NULL,
    output_snapshots_json STRING NOT NULL, method_version STRING NOT NULL,
    contract_sha256 STRING NOT NULL, code_sha256 STRING NOT NULL, published_at TIMESTAMP NOT NULL,
    validation_json STRING NOT NULL
) USING iceberg
LOCATION 's3a://lakehouse/{{schema}}/gold_release'
TBLPROPERTIES ('format-version'='2', 'write.parquet.compression-codec'='zstd');

CREATE TABLE IF NOT EXISTS nessie.{{schema}}.gold_current_release (
    channel STRING NOT NULL, release_id STRING NOT NULL, output_snapshots_json STRING NOT NULL,
    scope_start_utc TIMESTAMP NOT NULL, scope_end_utc TIMESTAMP NOT NULL, published_at TIMESTAMP NOT NULL
) USING iceberg
LOCATION 's3a://lakehouse/{{schema}}/gold_current_release'
TBLPROPERTIES ('format-version'='2', 'write.parquet.compression-codec'='zstd');

-- Independent native branches. Native quantities with unknown units are not tonnes.
CREATE TABLE IF NOT EXISTS nessie.{{schema}}.fact_waqi_station_daily_native (
    release_id STRING NOT NULL, dataset_id STRING NOT NULL, station_id STRING NOT NULL,
    observation_date DATE NOT NULL, variable_id STRING NOT NULL, pollutant STRING NOT NULL,
    provider_aqi INT, aqi_origin STRING NOT NULL, aqi_scheme STRING NOT NULL,
    quality_status STRING NOT NULL, missing_reason STRING, calendar_timezone STRING NOT NULL,
    input_run_id STRING NOT NULL, input_snapshot_id BIGINT NOT NULL
) USING iceberg PARTITIONED BY (release_id, years(observation_date))
LOCATION 's3a://lakehouse/{{schema}}/fact_waqi_station_daily_native'
TBLPROPERTIES ('format-version'='2','write.parquet.compression-codec'='zstd');

CREATE TABLE IF NOT EXISTS nessie.{{schema}}.fact_emission_aggregate_native (
    release_id STRING NOT NULL, aggregate_id STRING NOT NULL, dataset_id STRING NOT NULL,
    country_code STRING NOT NULL, period_type STRING NOT NULL, period_start DATE NOT NULL,
    period_end DATE NOT NULL, period_status STRING NOT NULL, aggregation_level STRING NOT NULL,
    sector STRING, subsector STRING, pollutant STRING NOT NULL, quantity_native DOUBLE NOT NULL,
    unit STRING, unit_status STRING NOT NULL, input_run_id STRING NOT NULL, input_snapshot_id BIGINT NOT NULL
) USING iceberg PARTITIONED BY (release_id, years(period_start))
LOCATION 's3a://lakehouse/{{schema}}/fact_emission_aggregate_native'
TBLPROPERTIES ('format-version'='2','write.parquet.compression-codec'='zstd');

CREATE TABLE IF NOT EXISTS nessie.{{schema}}.fact_emission_source_native (
    release_id STRING NOT NULL, dataset_id STRING NOT NULL, source_id STRING NOT NULL,
    year_label INT NOT NULL, period_start DATE NOT NULL, period_end DATE NOT NULL,
    period_status STRING NOT NULL, pollutant STRING NOT NULL, quantity_native DOUBLE NOT NULL,
    source_type STRING NOT NULL, sector STRING NOT NULL, subsector STRING NOT NULL,
    latitude DOUBLE NOT NULL, longitude DOUBLE NOT NULL, admin_code STRING,
    geographic_mapping_status STRING NOT NULL, unit STRING, unit_status STRING NOT NULL,
    input_run_id STRING NOT NULL, input_snapshot_id BIGINT NOT NULL
) USING iceberg PARTITIONED BY (release_id, years(period_start))
LOCATION 's3a://lakehouse/{{schema}}/fact_emission_source_native'
TBLPROPERTIES ('format-version'='2','write.parquet.compression-codec'='zstd');

CREATE TABLE IF NOT EXISTS nessie.{{schema}}.mart_emission_country_period_native (
    release_id STRING NOT NULL, dataset_id STRING NOT NULL, country_code STRING NOT NULL,
    period_type STRING NOT NULL, period_start DATE NOT NULL, period_end DATE NOT NULL,
    period_status STRING NOT NULL, pollutant STRING NOT NULL, quantity_native DOUBLE NOT NULL,
    unit STRING, unit_status STRING NOT NULL, aggregation_level STRING NOT NULL
) USING iceberg PARTITIONED BY (release_id, years(period_start))
LOCATION 's3a://lakehouse/{{schema}}/mart_emission_country_period_native'
TBLPROPERTIES ('format-version'='2','write.parquet.compression-codec'='zstd');

-- Historical view identity. Pointer embeds the complete manifest for atomic reads.
CREATE TABLE IF NOT EXISTS nessie.{{schema}}.gold_timeline (
    timeline_id STRING NOT NULL, channel STRING NOT NULL, parent_timeline_id STRING,
    operation STRING NOT NULL, trigger_release_id STRING,
    manifest_json STRING NOT NULL, published_at TIMESTAMP NOT NULL
) USING iceberg
LOCATION 's3a://lakehouse/{{schema}}/gold_timeline'
TBLPROPERTIES ('format-version'='2','write.parquet.compression-codec'='zstd');

CREATE TABLE IF NOT EXISTS nessie.{{schema}}.gold_timeline_current (
    channel STRING NOT NULL, timeline_id STRING NOT NULL,
    manifest_json STRING NOT NULL, published_at TIMESTAMP NOT NULL
) USING iceberg
LOCATION 's3a://lakehouse/{{schema}}/gold_timeline_current'
TBLPROPERTIES ('format-version'='2','write.parquet.compression-codec'='zstd');

-- Additive provenance sidecar for adapters with explicit measurement intervals.
CREATE TABLE IF NOT EXISTS nessie.{{schema}}.fact_measurement_provenance (
    release_id STRING NOT NULL, series_id STRING NOT NULL, hour_start_utc TIMESTAMP NOT NULL,
    metric_id STRING NOT NULL, source_version STRING NOT NULL,
    observed_at_utc TIMESTAMP, collected_at_utc TIMESTAMP, scheduled_at_utc TIMESTAMP,
    measurement_start_utc TIMESTAMP, measurement_end_utc TIMESTAMP,
    observation_time_kind STRING NOT NULL
) USING iceberg PARTITIONED BY (release_id, months(hour_start_utc))
LOCATION 's3a://lakehouse/{{schema}}/fact_measurement_provenance'
TBLPROPERTIES ('format-version'='2','write.parquet.compression-codec'='zstd');
