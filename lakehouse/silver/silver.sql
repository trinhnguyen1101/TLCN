-- Silver-layer Apache Iceberg schema for Spark 3.5 + Nessie.
--
-- Physical primary keys, foreign keys and secondary indexes are intentionally
-- absent: Iceberg does not enforce them. Every table documents the logical key
-- that Bronze -> Silver jobs must enforce with validation and MERGE.
-- Timestamps are stored and interpreted in UTC.

SET spark.sql.session.timeZone=UTC;

CREATE NAMESPACE IF NOT EXISTS nessie.silver;

-- ---------------------------------------------------------------------------
-- 1. Dataset registry
-- Logical key: (source_system, dataset_name, coalesce(source_version, ''))
-- dataset_id should be a deterministic UUID/string generated from that key.
-- It identifies the logical dataset/release, not one physical retrieval. Each
-- Bronze snapshot and processing attempt is represented by ingestion_run.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS nessie.silver.dataset (
    dataset_id       STRING NOT NULL,
    dataset_name     STRING NOT NULL,
    source_system    STRING NOT NULL,
    source_version   STRING,
    source_uri       STRING,
    landing_path     STRING,
    license_name     STRING,
    retrieved_at     TIMESTAMP,
    registered_at    TIMESTAMP NOT NULL,
    description      STRING
)
USING iceberg
TBLPROPERTIES (
    'format-version' = '2',
    'write.parquet.compression-codec' = 'zstd'
);

-- ---------------------------------------------------------------------------
-- 2. Attempts of a Bronze -> Silver logical run
-- Logical run key: (dataset_id, bronze_batch_id, pipeline_name, pipeline_version)
-- Row key: run_id. Secondary logical key: (logical_run_id, attempt_number).
-- bronze_batch_id, input_fingerprint and bronze_path come from the Bronze
-- manifest produced by landing_to_bronze.py. logical_run_id is deterministic;
-- run_id is a unique UUID for one physical attempt so retry history is kept.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS nessie.silver.ingestion_run (
    run_id                  STRING NOT NULL,
    logical_run_id          STRING NOT NULL,
    attempt_number          INT NOT NULL,
    dataset_id              STRING NOT NULL,
    bronze_batch_id         STRING NOT NULL,
    bronze_ingestion_date   DATE NOT NULL,
    bronze_path             STRING NOT NULL,
    input_fingerprint       STRING NOT NULL,
    pipeline_name           STRING NOT NULL,
    pipeline_version        STRING NOT NULL,
    started_at              TIMESTAMP NOT NULL,
    finished_at             TIMESTAMP,
    input_file_count        BIGINT,
    input_rows              BIGINT,
    output_rows             BIGINT,
    duplicate_rows          BIGINT,
    invalid_rows            BIGINT,
    quarantined_rows        BIGINT,
    status                  STRING NOT NULL,
    error_message           STRING,
    created_at              TIMESTAMP NOT NULL
)
USING iceberg
TBLPROPERTIES (
    'format-version' = '2',
    'write.parquet.compression-codec' = 'zstd'
);

-- ---------------------------------------------------------------------------
-- 3. Row/field-level data-quality findings
-- Logical key: issue_id. A recommended issue_id is a hash of
-- (ingestion_run_id, rule_id, source_file, source_record_locator, column_name).
-- raw_record_json is STRING because Spark/Iceberg has no shared native JSON
-- type that is consistently exposed to Trino.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS nessie.silver.data_quality_issue (
    issue_id                 STRING NOT NULL,
    ingestion_run_id         STRING NOT NULL,
    dataset_id               STRING NOT NULL,
    detected_at              TIMESTAMP NOT NULL,
    source_file              STRING,
    source_record_locator    STRING,
    record_key               STRING,
    column_name              STRING,
    rule_id                  STRING NOT NULL,
    issue_type               STRING NOT NULL,
    severity                 STRING NOT NULL,
    description              STRING,
    original_value           STRING,
    normalized_value         STRING,
    raw_record_json          STRING
)
USING iceberg
PARTITIONED BY (day(detected_at))
TBLPROPERTIES (
    'format-version' = '2',
    'write.parquet.compression-codec' = 'zstd'
);

-- ---------------------------------------------------------------------------
-- 4. Canonical variable registry
-- Logical key: (source_system, source_variable, measurement_kind)
-- measurement_kind prevents WAQI PM2.5 AQI from being confused with CAMS PM2.5
-- mass concentration or Climate TRACE PM2.5 emissions.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS nessie.silver.variable (
    variable_id       STRING NOT NULL,
    source_system     STRING NOT NULL,
    source_variable   STRING NOT NULL,
    canonical_name    STRING NOT NULL,
    variable_type     STRING NOT NULL,
    measurement_kind  STRING NOT NULL,
    native_unit       STRING,
    standard_unit     STRING,
    param_id          INT,
    short_name        STRING,
    description       STRING,
    created_at        TIMESTAMP NOT NULL
)
USING iceberg
TBLPROPERTIES (
    'format-version' = '2',
    'write.parquet.compression-codec' = 'zstd'
);

-- ---------------------------------------------------------------------------
-- 5. Versioned, conformed administrative units
-- Logical key: admin_unit_version_id.
-- Secondary logical key: (admin_code, snapshot_date).
-- A new version is inserted when the hierarchy/name/codes change; ETL closes
-- the previous version by setting valid_to and is_current=false.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS nessie.silver.admin_unit (
    admin_unit_version_id         STRING NOT NULL,
    admin_code                    STRING NOT NULL,
    parent_admin_unit_version_id  STRING,
    parent_code                   STRING,
    admin_level                   INT NOT NULL,
    unit_type                     STRING NOT NULL,
    name_vi                       STRING NOT NULL,
    name_en                       STRING,
    full_name_vi                  STRING,
    full_name_en                  STRING,
    slug                          STRING,
    postal_codes                  ARRAY<STRING>,
    snapshot_date                 DATE NOT NULL,
    valid_from                    DATE,
    valid_to                      DATE,
    is_current                    BOOLEAN NOT NULL,
    created_by_run_id             STRING NOT NULL,
    created_at                    TIMESTAMP NOT NULL
)
USING iceberg
TBLPROPERTIES (
    'format-version' = '2',
    'write.parquet.compression-codec' = 'zstd'
);

-- ---------------------------------------------------------------------------
-- 6. Source-to-canonical mapping for administrative units
-- Logical key:
-- (admin_unit_version_id, dataset_id, source_admin_code, source_record_locator)
-- This table allows attributes and boundaries to originate from different
-- reference datasets without losing lineage.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS nessie.silver.admin_unit_source (
    admin_unit_version_id   STRING NOT NULL,
    dataset_id              STRING NOT NULL,
    source_admin_code       STRING NOT NULL,
    source_record_locator   STRING NOT NULL,
    source_version          STRING,
    source_snapshot_date    DATE,
    source_file             STRING NOT NULL,
    source_file_sha256      STRING NOT NULL,
    ingestion_run_id        STRING NOT NULL,
    is_preferred_source     BOOLEAN NOT NULL,
    loaded_at               TIMESTAMP NOT NULL
)
USING iceberg
TBLPROPERTIES (
    'format-version' = '2',
    'write.parquet.compression-codec' = 'zstd'
);

-- ---------------------------------------------------------------------------
-- 7. Versioned administrative boundaries
-- Logical key: boundary_id. A recommended boundary_id is a hash of
-- (admin_unit_version_id, dataset_id, source_file_sha256, geometry_index).
-- Geometry is WKB so Spark and Trino can read it without requiring PostGIS.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS nessie.silver.admin_boundary (
    boundary_id            STRING NOT NULL,
    admin_unit_version_id  STRING NOT NULL,
    admin_code             STRING NOT NULL,
    boundary_wkb           BINARY NOT NULL,
    geometry_type          STRING NOT NULL,
    area_km2               DOUBLE,
    bbox_min_lon           DOUBLE,
    bbox_min_lat           DOUBLE,
    bbox_max_lon           DOUBLE,
    bbox_max_lat           DOUBLE,
    srid                   INT NOT NULL,
    dataset_id             STRING NOT NULL,
    source_file            STRING NOT NULL,
    source_file_sha256     STRING NOT NULL,
    source_geometry_index  INT,
    ingestion_run_id       STRING NOT NULL,
    snapshot_date          DATE NOT NULL,
    loaded_at              TIMESTAMP NOT NULL
)
USING iceberg
TBLPROPERTIES (
    'format-version' = '2',
    'write.parquet.compression-codec' = 'zstd'
);

-- ---------------------------------------------------------------------------
-- 8. CAMS grid definitions
-- Logical key: grid_id. For GRIB input, md5_grid_section should be the source
-- identity and grid_id should be deterministically derived from it.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS nessie.silver.cams_grid (
    grid_id                STRING NOT NULL,
    md5_grid_section       STRING NOT NULL,
    grid_type              STRING NOT NULL,
    row_count              INT NOT NULL,
    column_count           INT NOT NULL,
    latitude_increment     DOUBLE,
    longitude_increment    DOUBLE,
    bbox_min_lon           DOUBLE,
    bbox_min_lat           DOUBLE,
    bbox_max_lon           DOUBLE,
    bbox_max_lat           DOUBLE,
    srid                   INT NOT NULL,
    dataset_id             STRING NOT NULL,
    ingestion_run_id       STRING NOT NULL,
    created_at             TIMESTAMP NOT NULL
)
USING iceberg
TBLPROPERTIES (
    'format-version' = '2',
    'write.parquet.compression-codec' = 'zstd'
);

-- ---------------------------------------------------------------------------
-- 9. CAMS points within a grid
-- Logical key: (grid_id, grid_point_id)
-- Secondary logical key: (grid_id, row_index, column_index)
-- grid_point_id is the stable flattened array index within a grid.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS nessie.silver.cams_grid_point (
    grid_id        STRING NOT NULL,
    grid_point_id  BIGINT NOT NULL,
    row_index      INT NOT NULL,
    column_index   INT NOT NULL,
    latitude       DOUBLE NOT NULL,
    longitude      DOUBLE NOT NULL
)
USING iceberg
TBLPROPERTIES (
    'format-version' = '2',
    'write.parquet.compression-codec' = 'zstd'
);

-- ---------------------------------------------------------------------------
-- 10. CAMS observations at native grid resolution
-- Logical key:
-- (dataset_id, valid_time, grid_id, grid_point_id, variable_id)
-- Reprocessed values MERGE into this key; Iceberg snapshots retain table-level
-- history. Conflicting duplicates within one run fail data-quality checks.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS nessie.silver.cams_observation (
    dataset_id          STRING NOT NULL,
    valid_time          TIMESTAMP NOT NULL,
    grid_id             STRING NOT NULL,
    grid_point_id       BIGINT NOT NULL,
    variable_id         STRING NOT NULL,
    value_native        DOUBLE NOT NULL,
    value_standard      DOUBLE,
    qc_flag             STRING NOT NULL,
    source_file         STRING NOT NULL,
    source_file_sha256  STRING NOT NULL,
    ingestion_run_id    STRING NOT NULL,
    loaded_at           TIMESTAMP NOT NULL
)
USING iceberg
PARTITIONED BY (month(valid_time), variable_id)
TBLPROPERTIES (
    'format-version' = '2',
    'write.parquet.compression-codec' = 'zstd',
    'write.distribution-mode' = 'hash',
    'write.target-file-size-bytes' = '268435456'
);

-- ---------------------------------------------------------------------------
-- 11. Canonical WAQI stations
-- Logical key: station_id. station_id must not be derived from display name
-- alone; use the source mapping table when source IDs are missing.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS nessie.silver.waqi_station (
    station_id              STRING NOT NULL,
    station_name            STRING NOT NULL,
    location_label          STRING NOT NULL,
    admin_unit_version_id   STRING,
    admin_code              STRING,
    latitude                DOUBLE,
    longitude               DOUBLE,
    timezone                STRING,
    metadata_status         STRING NOT NULL,
    admin_match_method      STRING,
    admin_match_confidence  DOUBLE,
    first_seen_date         DATE,
    last_seen_date          DATE,
    created_by_run_id       STRING NOT NULL,
    updated_by_run_id       STRING NOT NULL,
    created_at              TIMESTAMP NOT NULL,
    updated_at              TIMESTAMP NOT NULL
)
USING iceberg
TBLPROPERTIES (
    'format-version' = '2',
    'write.parquet.compression-codec' = 'zstd'
);

-- ---------------------------------------------------------------------------
-- 12. WAQI source identity/alias mapping
-- Logical key: (dataset_id, source_station_key)
-- source_station_key is source_station_id when available; otherwise it is a
-- normalized, deterministic key derived from the original file/station label.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS nessie.silver.waqi_station_source (
    dataset_id             STRING NOT NULL,
    source_station_key     STRING NOT NULL,
    station_id             STRING NOT NULL,
    source_station_id      STRING,
    source_station_name    STRING,
    source_location_label  STRING,
    source_file            STRING NOT NULL,
    source_file_sha256     STRING NOT NULL,
    ingestion_run_id       STRING NOT NULL,
    first_seen_date        DATE,
    last_seen_date         DATE,
    loaded_at              TIMESTAMP NOT NULL
)
USING iceberg
TBLPROPERTIES (
    'format-version' = '2',
    'write.parquet.compression-codec' = 'zstd'
);

-- ---------------------------------------------------------------------------
-- 13. Variable availability by station and dataset
-- Logical key: (dataset_id, station_id, variable_id)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS nessie.silver.waqi_station_variable (
    dataset_id              STRING NOT NULL,
    station_id              STRING NOT NULL,
    variable_id             STRING NOT NULL,
    source_column_name      STRING NOT NULL,
    is_available            BOOLEAN NOT NULL,
    first_observation_date  DATE,
    last_observation_date   DATE,
    last_seen_run_id        STRING NOT NULL,
    updated_at              TIMESTAMP NOT NULL
)
USING iceberg
TBLPROPERTIES (
    'format-version' = '2',
    'write.parquet.compression-codec' = 'zstd'
);

-- ---------------------------------------------------------------------------
-- 14. WAQI daily pollutant AQI observations (long format)
-- Logical key: (dataset_id, station_id, observation_date, variable_id)
-- Missing source values may be retained with a NULL aqi_value only when
-- missing_reason is populated; they must never be converted to zero.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS nessie.silver.waqi_daily_observation (
    dataset_id             STRING NOT NULL,
    station_id             STRING NOT NULL,
    observation_date       DATE NOT NULL,
    variable_id            STRING NOT NULL,
    aqi_value              INT,
    missing_reason         STRING,
    qc_flag                STRING NOT NULL,
    source_file            STRING NOT NULL,
    source_file_sha256     STRING NOT NULL,
    source_record_locator  STRING,
    ingestion_run_id       STRING NOT NULL,
    loaded_at              TIMESTAMP NOT NULL
)
USING iceberg
PARTITIONED BY (year(observation_date))
TBLPROPERTIES (
    'format-version' = '2',
    'write.parquet.compression-codec' = 'zstd',
    'write.distribution-mode' = 'hash'
);

-- ---------------------------------------------------------------------------
-- 15. WAQI hourly observation header
-- Logical key: (dataset_id, station_id, observation_time_utc)
-- observation_id is a deterministic hash of that key.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS nessie.silver.waqi_hourly_observation (
    observation_id                  STRING NOT NULL,
    dataset_id                      STRING NOT NULL,
    station_id                      STRING NOT NULL,
    observation_time_utc            TIMESTAMP NOT NULL,
    overall_aqi                     INT,
    dominant_pollutant_variable_id  STRING,
    source_timezone                 STRING,
    collected_at_utc                TIMESTAMP NOT NULL,
    qc_flag                         STRING NOT NULL,
    source_file                     STRING NOT NULL,
    source_file_sha256              STRING NOT NULL,
    ingestion_run_id                STRING NOT NULL,
    loaded_at                       TIMESTAMP NOT NULL
)
USING iceberg
PARTITIONED BY (month(observation_time_utc))
TBLPROPERTIES (
    'format-version' = '2',
    'write.parquet.compression-codec' = 'zstd',
    'write.distribution-mode' = 'hash'
);

-- ---------------------------------------------------------------------------
-- 16. WAQI hourly pollutant/weather measurements (long format)
-- Logical key:
-- (dataset_id, station_id, observation_time_utc, variable_id)
-- Pollutant AQI, concentration and meteorological values are distinguished by
-- variable.measurement_kind and its native/standard units. Time and station
-- are repeated intentionally so large measurement queries can prune partitions
-- without first joining the observation header.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS nessie.silver.waqi_hourly_measurement (
    observation_id        STRING NOT NULL,
    dataset_id            STRING NOT NULL,
    station_id            STRING NOT NULL,
    observation_time_utc  TIMESTAMP NOT NULL,
    variable_id           STRING NOT NULL,
    value_native          DOUBLE,
    value_standard        DOUBLE,
    missing_reason        STRING,
    qc_flag               STRING NOT NULL,
    ingestion_run_id      STRING NOT NULL,
    loaded_at             TIMESTAMP NOT NULL
)
USING iceberg
PARTITIONED BY (month(observation_time_utc))
TBLPROPERTIES (
    'format-version' = '2',
    'write.parquet.compression-codec' = 'zstd',
    'write.distribution-mode' = 'hash'
);

-- ---------------------------------------------------------------------------
-- 17. Climate TRACE aggregate emissions
-- Logical key: aggregate_id. Generate it from the normalized values of:
-- (dataset_id, country_code, period_type, period_start, aggregation_level,
--  coalesce(sector, '<TOTAL>'), coalesce(subsector, '<NONE>'), variable_id).
-- This makes NULL hierarchy levels safe for idempotent MERGE operations.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS nessie.silver.emission_aggregate (
    aggregate_id                 STRING NOT NULL,
    dataset_id                   STRING NOT NULL,
    country_code                 STRING NOT NULL,
    period_type                  STRING NOT NULL,
    period_start                 DATE NOT NULL,
    period_end                   DATE NOT NULL,
    period_status                STRING NOT NULL,
    aggregation_level            STRING NOT NULL,
    sector                       STRING,
    subsector                    STRING,
    variable_id                  STRING NOT NULL,
    emission_quantity_native     DOUBLE NOT NULL,
    emission_quantity_standard   DOUBLE,
    source_file                  STRING NOT NULL,
    source_file_sha256           STRING NOT NULL,
    source_record_locator        STRING,
    ingestion_run_id             STRING NOT NULL,
    loaded_at                    TIMESTAMP NOT NULL
)
USING iceberg
PARTITIONED BY (year(period_start))
TBLPROPERTIES (
    'format-version' = '2',
    'write.parquet.compression-codec' = 'zstd',
    'write.distribution-mode' = 'hash'
);

-- ---------------------------------------------------------------------------
-- 18. Climate TRACE point/asset emission sources
-- Logical key: source_id. source_id should be namespaced, for example
-- "climate_trace:25454003", to prevent collisions with future providers.
-- The current row is updated by MERGE; Iceberg snapshots retain prior versions.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS nessie.silver.emission_source (
    source_id              STRING NOT NULL,
    source_system          STRING NOT NULL,
    source_native_id       STRING NOT NULL,
    country_code           STRING NOT NULL,
    latitude               DOUBLE NOT NULL,
    longitude              DOUBLE NOT NULL,
    sector                 STRING NOT NULL,
    subsector               STRING NOT NULL,
    source_type            STRING NOT NULL,
    asset_type             STRING,
    admin_unit_version_id  STRING,
    admin_code             STRING,
    dataset_id             STRING NOT NULL,
    first_seen_year        INT,
    last_seen_year         INT,
    source_file            STRING NOT NULL,
    source_file_sha256     STRING NOT NULL,
    source_record_locator  STRING,
    last_seen_run_id       STRING NOT NULL,
    updated_at             TIMESTAMP NOT NULL
)
USING iceberg
TBLPROPERTIES (
    'format-version' = '2',
    'write.parquet.compression-codec' = 'zstd'
);

-- ---------------------------------------------------------------------------
-- 19. Emission observations for individual sources
-- Logical key: (dataset_id, source_id, year_label, variable_id)
-- Exact duplicate source rows must be removed before MERGE and counted in the
-- corresponding ingestion_run. Conflicting duplicates must fail the run.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS nessie.silver.emission_source_observation (
    dataset_id                   STRING NOT NULL,
    source_id                    STRING NOT NULL,
    year_label                   INT NOT NULL,
    period_start                 DATE NOT NULL,
    period_end                   DATE NOT NULL,
    period_status                STRING NOT NULL,
    variable_id                 STRING NOT NULL,
    emission_quantity_native    DOUBLE NOT NULL,
    emission_quantity_standard  DOUBLE,
    source_file                 STRING NOT NULL,
    source_file_sha256          STRING NOT NULL,
    source_record_locator       STRING,
    ingestion_run_id            STRING NOT NULL,
    loaded_at                   TIMESTAMP NOT NULL
)
USING iceberg
PARTITIONED BY (year(period_start))
TBLPROPERTIES (
    'format-version' = '2',
    'write.parquet.compression-codec' = 'zstd',
    'write.distribution-mode' = 'hash'
);

-- ETL validation rules, controlled values, MERGE keys and source-specific
-- normalization rules are documented in lakehouse/silver/README.md.
