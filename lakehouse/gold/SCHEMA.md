# Gold physical schema — 28/10/2026

This file documents the executable implementation only. [gold.sql](gold.sql) is the Spark/Iceberg DDL; [archived v2 design](SCHEMA-v2-ARCHIVE.md) preserves the earlier wide target and decisions. There is no `gold_build_id` column or wide concentration fact in this implementation.

## Storage and identity

Spark `nessie.<schema>`, Trino `iceberg.<schema>`, Nessie main, `s3a://lakehouse/<schema>/<table>`. Iceberg v2, Parquet/Zstd. UTC timestamps; `Asia/Ho_Chi_Minh` local daily/monthly calendar. Source cadence is metadata; the air-quality grain remains `hour_start_utc` even for sparse 3h instantaneous inputs.

All release-scoped keys below include `release_id`. ETL checks uniqueness/null keys/FKs; Iceberg does not enforce relational keys. `series_id` hashes dataset/location/contract/cadence/temporal/spatial semantics. A contract/geometry/unit/method transition requires an explicit compatible-lane selection and rebuild. An unknown provider observation time is not replaced by scheduled/collection time.

## Published historical view

`gold_release` pins input/output snapshot mappings for one validated `[scope_start_utc,scope_end_utc)` chunk. `gold_current_release` remains a legacy single-chunk diagnostic/native pointer. Historical/dashboard readers resolve `gold_timeline_current` **once**, including its complete embedded manifest, then read only recorded table snapshots. They never join a pointer to table heads.

`gold_timeline` is an immutable version graph keyed by `timeline_id`; `parent_timeline_id` records publish/withdraw/rollback ancestry. New manifests use wire version=2: `series_catalog` holds content-addressed semantic metadata and segments carry `series_ref`; snapshot mappings remain inline. Readers also support immutable version=1 manifests with inline series. Both decode to disjoint segments per `compatibility_id`, release/snapshot mappings, source/dataset/series/cadence/profile, method and contract hash. Existing IDs/history are never rewritten. Compatibility hashes also pin metric units/vertical policy and actual administrative boundary hashes. Incompatible lanes coexist and are never silently combined.

A correction replaces its entire scope, including keys absent after deletion. Overlap splits older intervals; outside scope remains visible. A withdrawal is a tombstone, not a fallback. Whole-view rollback creates a new pointer version containing a previously validated immutable manifest. Replay does not undo an explicit rollback. One Compose writer with the existing flock is required; multi-host writers are unsupported.

## Serving contracts and aggregation

`/api/gold/history`: hourly/daily/monthly, exclusive end, source/series/admin/pollutant/method/profile/lane filters, pinned timeline and pagination cursor. Daily/monthly bounds align to VN midnight. Monthly composition aggregates canonical selected daily `concentration_sum`/`valid_hours`, including partial months and corrections. `calendar_expected_hours` is the entire calendar month; `published_expected_hours` is only published series-days. There is no monthly AQI. `valid_days` counts days with all expected slots; `observed_days` separately counts days with at least one valid value.

Cursor v2 pins timeline, filter signature, bounded scope page and row offset.
Hourly/daily pages scan at most16 segments; monthly pages keep whole VN months
and cap32 segments/12months. More than32 segments in one month requires scope
coalescing. Existing cursors are readable when within16segments, otherwise restart
pagination. AQI/quality aggregates merge server-side summaries in32-scan batches.
Missing-scope metadata describes the entire request, not just the current page.
No physical DDL migration accompanies this wire/query optimization.

Quality now distinguishes `absent_slots` (expected minus observed records),
`missing_value_slots` (observed minus valid minus invalid), and invalid values.
For admitted sources every present record has an actual observation timestamp;
do not relax that assumption without the coordinated
[unknown-clock migration](OBSERVATION-TIME-MIGRATION.md). The current fact keeps
`observed_at_utc NOT NULL`; sidecar nullable clocks do not waive that constraint.

For declared sources, serving spine uses contract metric scope even when every observation of a pollutant is withdrawn; concentration facts remain sparse. Per-pollutant QC/observation clocks survive the dashboard wide projection in `metricQuality`. Wide QC summary is partial when a declared pollutant is unavailable; shared spatial coverage is NULL when no single complete per-metric value applies. YoY uses matched province/calendar slots with valid values in both periods; a non-leap-year Feb28 is not reused for Feb29. Long marts repeat overall AQI across pollutant rows. Distribution reads exactly one canonical PM2.5 row per series/day/method (present even for missing PM2.5); it does not count six copies. `/history/aqi-distribution` and `/history/quality` expose pinned timeline identity and missing publication scopes. Quality expected counts describe published series-days, not ingestion attempts or national spatial representativeness. Collection counters remain NULL when unavailable.

Computed AQI method remains `vn-aqi-1459-2019-project-v1`. Instantaneous/provider snapshots stay ineligible at both 60 and 180 minutes. Daily 24/24 completeness is the project gate. Native WAQI AQI has origin=provider and is never relabelled computed VN_AQI. Emissions with unverified unit stay native with unit=NULL.

`fact_measurement_provenance` is an additive sidecar; v2 normalized adapters require explicit intervals/source version; v3 additionally declares the full metric policy independently of measurement presence and retain independent clocks. Production province adapters additionally require declared metric policies and a spatial coverage gate; station/proxy semantics cannot use the province adapter. Production activation requires a reviewed contract and succeeded matching Silver runs. Existing v1 fixtures/old releases remain readable; no old values/methods are rewritten.

## Physical tables

The field lists below are copied from the executable DDL. Per-table partition clauses are exact. Tiny registry/native reference tables are unpartitioned where no partition clause is shown.

### `dim_admin_unit`

Logical key: `release_id, admin_unit_version_id`. Partition: `(release_id)`.

```sql
release_id STRING NOT NULL,
    admin_unit_version_id STRING NOT NULL,
    admin_code STRING NOT NULL,
    name_vi STRING NOT NULL,
    parent_admin_unit_version_id STRING,
    admin_level INT NOT NULL,
    snapshot_date DATE NOT NULL,
    boundary_hash STRING
```

### `dim_geo_component`

Logical key: `release_id, geo_component_id`. Partition: `(release_id)`.

```sql
release_id STRING NOT NULL,
    geo_component_id STRING NOT NULL,
    parent_admin_unit_version_id STRING NOT NULL,
    component_kind STRING NOT NULL,
    component_name STRING NOT NULL,
    geometry_hash STRING NOT NULL,
    area_m2 DOUBLE NOT NULL,
    boundary_wkb BINARY NOT NULL,
    geography_policy_version STRING NOT NULL
```

### `dim_location`

Logical key: `release_id, location_id`. Partition: `(release_id)`.

```sql
release_id STRING NOT NULL,
    location_id STRING NOT NULL,
    admin_unit_version_id STRING,
    name STRING NOT NULL,
    admin_code STRING,
    location_kind STRING NOT NULL,
    spatial_representation STRING NOT NULL,
    mapping_status STRING NOT NULL
```

### `dim_air_quality_series`

Logical key: `release_id, series_id`. Partition: `(release_id)`.

```sql
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
```

### `dim_metric`

Logical key: `release_id, metric_id`. Partition: `(release_id)`.

```sql
release_id STRING NOT NULL,
    metric_id STRING NOT NULL,
    pollutant STRING NOT NULL,
    measurement_kind STRING NOT NULL,
    unit STRING NOT NULL,
    vertical_support STRING NOT NULL,
    unit_policy_version STRING NOT NULL
```

### `bridge_source_variable_metric`

Logical key: `release_id, dataset_id, variable_id, metric_id`. Partition: `(release_id)`.

```sql
release_id STRING NOT NULL,
    dataset_id STRING NOT NULL,
    variable_id STRING NOT NULL,
    source_column STRING NOT NULL,
    metric_id STRING NOT NULL,
    source_unit STRING NOT NULL,
    standard_unit STRING NOT NULL,
    metric_policy_version STRING NOT NULL
```

### `dim_date`

Logical key: `release_id, calendar_date`. Partition: `(release_id)`.

```sql
release_id STRING NOT NULL,
    calendar_date DATE NOT NULL,
    calendar_year INT NOT NULL,
    calendar_month INT NOT NULL,
    calendar_quarter INT NOT NULL,
    days_in_month INT NOT NULL
```

### `dim_hour`

Logical key: `release_id, hour_start_utc`. Partition: `(release_id)`.

```sql
release_id STRING NOT NULL,
    hour_start_utc TIMESTAMP NOT NULL,
    hour_end_utc TIMESTAMP NOT NULL,
    date_utc DATE NOT NULL,
    date_vn DATE NOT NULL,
    hour_vn INT NOT NULL
```

### `dim_aqi_method`

Logical key: `release_id, method_version`. Partition: `(release_id)`.

```sql
release_id STRING NOT NULL,
    method_version STRING NOT NULL,
    reference_url STRING NOT NULL,
    reference_sha256 STRING NOT NULL,
    calendar_timezone STRING NOT NULL,
    policies_json STRING NOT NULL
```

### `ref_aqi_breakpoint`

Logical key: `release_id, method_version, pollutant, averaging_basis, breakpoint_order`. Partition: `(release_id)`.

```sql
release_id STRING NOT NULL,
    method_version STRING NOT NULL,
    pollutant STRING NOT NULL,
    averaging_basis STRING NOT NULL,
    breakpoint_order INT NOT NULL,
    concentration_breakpoint DOUBLE NOT NULL,
    index_breakpoint INT NOT NULL
```

### `fact_air_quality_hourly`

Logical key: `release_id, series_id, hour_start_utc, metric_id`. Partition: `(release_id, months(hour_start_utc))`.

```sql
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
```

### `fact_aqi_pollutant_hourly`

Logical key: `release_id, series_id, hour_start_utc, pollutant, basis, method_version, applicability_profile`. Partition: `(release_id, months(hour_start_utc))`.

```sql
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
```

### `fact_aqi_hourly`

Logical key: `release_id, series_id, hour_start_utc, method_version, applicability_profile`. Partition: `(release_id, months(hour_start_utc))`.

```sql
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
```

### `fact_aqi_pollutant_daily`

Logical key: `release_id, series_id, aqi_date_local, pollutant, basis, method_version, applicability_profile`. Partition: `(release_id, months(aqi_date_local))`.

```sql
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
```

### `fact_aqi_daily`

Logical key: `release_id, series_id, aqi_date_local, method_version, applicability_profile`. Partition: `(release_id, months(aqi_date_local))`.

```sql
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
```

### `mart_air_quality_hourly`

Logical key: `release_id, series_id, hour_start_utc, pollutant`. Partition: `(release_id, months(hour_start_utc))`.

```sql
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
```

### `mart_air_quality_daily`

Logical key: `release_id, series_id, aqi_date_local, pollutant`. Partition: `(release_id, months(aqi_date_local))`.

```sql
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
```

### `mart_air_quality_monthly`

Logical key: `release_id, series_id, month_local, pollutant`. Partition: `(release_id, months(month_local))`.

```sql
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
```

### `mart_source_quality_daily`

Logical key: `release_id, series_id, date_local, pollutant`. Partition: `(release_id, months(date_local))`.

```sql
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
```

### `bridge_cams_region_weight`

Logical key: `cache_key, grid_id, grid_point_id, location_id`. Partition: `none`.

```sql
cache_key STRING NOT NULL, grid_id STRING NOT NULL, grid_point_id BIGINT NOT NULL,
    location_id STRING NOT NULL, boundary_hash STRING NOT NULL, method_version STRING NOT NULL,
    intersection_area_m2 DOUBLE NOT NULL, region_area_m2 DOUBLE NOT NULL,
    area_fraction DOUBLE NOT NULL, latitude_increment DOUBLE NOT NULL, longitude_increment DOUBLE NOT NULL
```

### `gold_release`

Logical key: `release_id`. Partition: `none`.

```sql
release_id STRING NOT NULL, channel STRING NOT NULL, scope_start_utc TIMESTAMP NOT NULL,
    scope_end_utc TIMESTAMP NOT NULL, input_snapshots_json STRING NOT NULL,
    output_snapshots_json STRING NOT NULL, method_version STRING NOT NULL,
    contract_sha256 STRING NOT NULL, code_sha256 STRING NOT NULL, published_at TIMESTAMP NOT NULL,
    validation_json STRING NOT NULL
```

### `gold_current_release`

Logical key: `channel`. Partition: `none`.

```sql
channel STRING NOT NULL, release_id STRING NOT NULL, output_snapshots_json STRING NOT NULL,
    scope_start_utc TIMESTAMP NOT NULL, scope_end_utc TIMESTAMP NOT NULL, published_at TIMESTAMP NOT NULL
```

### `fact_waqi_station_daily_native`

Logical key: `release_id, dataset_id, station_id, observation_date, variable_id`. Partition: `(release_id, years(observation_date))`.

```sql
release_id STRING NOT NULL, dataset_id STRING NOT NULL, station_id STRING NOT NULL,
    observation_date DATE NOT NULL, variable_id STRING NOT NULL, pollutant STRING NOT NULL,
    provider_aqi INT, aqi_origin STRING NOT NULL, aqi_scheme STRING NOT NULL,
    quality_status STRING NOT NULL, missing_reason STRING, calendar_timezone STRING NOT NULL,
    input_run_id STRING NOT NULL, input_snapshot_id BIGINT NOT NULL
```

### `fact_emission_aggregate_native`

Logical key: `release_id, aggregate_id`. Partition: `(release_id, years(period_start))`.

```sql
release_id STRING NOT NULL, aggregate_id STRING NOT NULL, dataset_id STRING NOT NULL,
    country_code STRING NOT NULL, period_type STRING NOT NULL, period_start DATE NOT NULL,
    period_end DATE NOT NULL, period_status STRING NOT NULL, aggregation_level STRING NOT NULL,
    sector STRING, subsector STRING, pollutant STRING NOT NULL, quantity_native DOUBLE NOT NULL,
    unit STRING, unit_status STRING NOT NULL, input_run_id STRING NOT NULL, input_snapshot_id BIGINT NOT NULL
```

### `fact_emission_source_native`

Logical key: `release_id, dataset_id, source_id, year_label, pollutant, source_type`. Partition: `(release_id, years(period_start))`.

```sql
release_id STRING NOT NULL, dataset_id STRING NOT NULL, source_id STRING NOT NULL,
    year_label INT NOT NULL, period_start DATE NOT NULL, period_end DATE NOT NULL,
    period_status STRING NOT NULL, pollutant STRING NOT NULL, quantity_native DOUBLE NOT NULL,
    source_type STRING NOT NULL, sector STRING NOT NULL, subsector STRING NOT NULL,
    latitude DOUBLE NOT NULL, longitude DOUBLE NOT NULL, admin_code STRING,
    geographic_mapping_status STRING NOT NULL, unit STRING, unit_status STRING NOT NULL,
    input_run_id STRING NOT NULL, input_snapshot_id BIGINT NOT NULL
```

### `mart_emission_country_period_native`

Logical key: `release_id, dataset_id, country_code, period_type, period_start, pollutant`. Partition: `(release_id, years(period_start))`.

```sql
release_id STRING NOT NULL, dataset_id STRING NOT NULL, country_code STRING NOT NULL,
    period_type STRING NOT NULL, period_start DATE NOT NULL, period_end DATE NOT NULL,
    period_status STRING NOT NULL, pollutant STRING NOT NULL, quantity_native DOUBLE NOT NULL,
    unit STRING, unit_status STRING NOT NULL, aggregation_level STRING NOT NULL
```

### `gold_timeline`

Logical key: `timeline_id`. Partition: `none`.

```sql
timeline_id STRING NOT NULL, channel STRING NOT NULL, parent_timeline_id STRING,
    operation STRING NOT NULL, trigger_release_id STRING,
    manifest_json STRING NOT NULL, published_at TIMESTAMP NOT NULL
```

### `gold_timeline_current`

Logical key: `channel`. Partition: `none`.

```sql
channel STRING NOT NULL, timeline_id STRING NOT NULL,
    manifest_json STRING NOT NULL, published_at TIMESTAMP NOT NULL
```

### `fact_measurement_provenance`

Logical key: `release_id, series_id, hour_start_utc, metric_id`. Partition: `(release_id, months(hour_start_utc))`.

```sql
release_id STRING NOT NULL, series_id STRING NOT NULL, hour_start_utc TIMESTAMP NOT NULL,
    metric_id STRING NOT NULL, source_version STRING NOT NULL,
    observed_at_utc TIMESTAMP, collected_at_utc TIMESTAMP, scheduled_at_utc TIMESTAMP,
    measurement_start_utc TIMESTAMP, measurement_end_utc TIMESTAMP,
    observation_time_kind STRING NOT NULL
```
