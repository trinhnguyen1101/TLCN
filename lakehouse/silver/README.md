# Silver layer

`silver.sql` defines the cleaned, standardized layer as Apache Iceberg tables
in the `nessie.silver` namespace. It is Spark SQL, not PostgreSQL SQL.

## Design rules

- Bronze files remain immutable. File-derived rows carry source file lineage,
  or (for CAMS cube rows) join through `bronze_batch_id` and
  `cams_cube_standard_source` to `source_file` and `source_file_sha256`.
  Native `cams_cube`/`cams_cube_source` are preserved legacy tables.
- Business/entity IDs stored as `STRING` are deterministic UUIDs or hashes.
  `ingestion_run.run_id` is the deliberate exception: it identifies one
  physical attempt and is a new UUID for every retry.
- Primary and foreign keys in this document are logical constraints. Bronze to
  Silver jobs must validate them because Iceberg does not enforce relational
  constraints.
- Jobs use `MERGE INTO` on the logical key of each target table. Replaying
  an already successful logical run must not add rows or alter fact values.
- Spark Silver sessions use `Asia/Ho_Chi_Minh` (UTC+07:00). Source UTC instants
  are converted for display and calendar partitioning. WAQI `date` is a
  Vietnam-local calendar date; it must not be shifted. Explicit `*_utc`
  columns retain their UTC meaning. Store source timezone separately when known.
- Exact duplicate source rows are removed and counted. Conflicting rows with
  the same logical key fail the run and are written to `data_quality_issue`.
- Missing measurements remain `NULL` with a `missing_reason`; they are never
  converted to zero.
- `CREATE TABLE IF NOT EXISTS` bootstraps an empty environment only. Schema
  changes to existing Iceberg tables require explicit `ALTER TABLE` migrations.

## Dataset, file and run identity

`dataset_id` identifies a logical dataset/release. Retrieving the same
`source_system`, `dataset_name` and `source_version` again keeps the same
`dataset_id`; the physical Bronze snapshots are distinguished by
`bronze_batch_id`, `input_fingerprint` and `ingestion_run`.

For deterministic IDs, normalize key strings with Unicode NFC and trim outer
whitespace. Lowercase only controlled identifiers such as `source_system` and
`pipeline_name`; never change the case of an opaque native ID. Serialize the
normalized components as a compact UTF-8 JSON array, including an ID namespace
and version, then store the lowercase SHA-256 hex digest. Do not use Spark row
order, partition IDs, Python's `hash()`, or `monotonically_increasing_id()`.

Examples of canonical hash inputs:

```text
dataset_id     = sha256_json(["silver-dataset-v1", source_system,
                              dataset_name, source_version_or_empty])
logical_run_id = sha256_json(["silver-run-v1", dataset_id, bronze_batch_id,
                              pipeline_name, pipeline_version])
```

`logical_run_id` groups retries of the same work. `run_id` is a UUIDv4 for one
physical attempt and `attempt_number` starts at 1 within a logical run. Before
starting another attempt, the orchestrator must check for a succeeded attempt;
if one exists, it exits without rewriting facts. Fact rows reference the
successful attempt's `run_id`.

`source_file` is always the POSIX relative path beneath
`<ingestion_run.bronze_path>/files/`, never a basename or an absolute Landing
path. The complete Bronze object is reconstructed as
`<bronze_path>/files/<source_file>`. `source_file_sha256` is copied from Bronze
`_file_metadata` and is required on file-derived Silver rows. Recommended
record locators are `csv:line=<n>`, `json:pointer=<pointer>`, and
`grib:message=<n>`.

## Required controlled values

ETL code should reject or quarantine values outside these initial sets. Extend
the lists deliberately when onboarding a new source.

| Column | Initial accepted values |
| --- | --- |
| `ingestion_run.status` | `running`, `succeeded`, `failed`, `partial` |
| `data_quality_issue.severity` | `info`, `warning`, `error`, `fatal` |
| `qc_flag` | `ok`, `missing`, `invalid`, `out_of_range`, `duplicate`, `corrected` |
| `period_type` | `year`, `month` |
| `aggregation_level` | `totals`, `sectors`, `subsectors` |
| `period_status` | `actual`, `partial`, `estimated`, `projected` |
| `metadata_status` | `complete`, `partial`, `derived`, `unresolved` |
| `spatial_representation` | `city_proxy` |

## Logical keys used by MERGE

| Table | Logical key |
| --- | --- |
| `dataset` | `source_system, dataset_name, coalesce(source_version, '')` |
| `ingestion_run` | `run_id`; unique attempt: `logical_run_id, attempt_number` |
| `variable` | `source_system, source_variable, measurement_kind` |
| `admin_unit` | `admin_unit_version_id` |
| `admin_unit_source` | `admin_unit_version_id, dataset_id, source_admin_code, source_record_locator` |
| `admin_boundary` | `boundary_id` |
| `cams_grid` | `grid_id` |
| `cams_grid_point` | `grid_id, grid_point_id` |
| `cams_cube_source` | `dataset_id, bronze_batch_id, column_name` |
| `cams_cube` | `dataset_id, valid_time, grid_id` |
| `cams_cube_standard_source` | `dataset_id, bronze_batch_id, column_name` |
| `cams_cube_standard` | `dataset_id, valid_time, grid_id` |
| `waqi_station` | `station_id` |
| `waqi_station_source` | `dataset_id, source_station_key` |
| `waqi_station_variable` | `dataset_id, station_id, variable_id` |
| `waqi_daily_observation` | `dataset_id, station_id, observation_date, variable_id` |
| `waqi_hourly_observation` | `dataset_id, station_id, observation_time_utc` |
| `waqi_hourly_measurement` | `dataset_id, station_id, observation_time_utc, variable_id` |
| `emission_aggregate` | `aggregate_id` |
| `emission_source` | `source_id` |
| `emission_source_observation` | `dataset_id, source_id, year_label, variable_id` |
| `province_air_quality_location` | `dataset_id, source_location_id` |
| `province_air_quality_hourly_observation` | `dataset_id, proxy_location_id, snapshot_hour_utc` |
| `province_air_quality_hourly_measurement` | `observation_id, variable_id` |

The `province_air_quality_*` tables store the Supabase API Ninjas output. The
city proxy location keeps the exact queried coordinates and a checked
`admin_unit_version_id`.

## Source-specific normalization

### WAQI historical CSV

- Parse `date` explicitly using `yyyy/M/d`; do not rely on locale inference.
- Trim column names and cell values. Empty strings become `NULL`.
- Require nonblank AQI values to be finite, nonnegative integers within the
  SQL INT range before casting; never saturate overflow or turn NaN into zero.
- The pollutant columns contain daily AQI values, not concentrations.
- Each historical CSV represents exactly one station. The current files have
  no provider station ID. Build `station_id` from dataset ID and normalized
  full relative filename, reject colliding normalized names, and keep the
  original filename in `waqi_station_source`. This keeps distinct stations
  separate even if display names are similar.
- Set `waqi_station.timezone` to `Asia/Ho_Chi_Minh` for these Vietnam files.
  Their daily `date` values are local dates, not UTC timestamps.
- Populate `waqi_station_variable` for both present and absent canonical WAQI
  columns so schema differences between station files remain observable.

### CAMS EAC4 GRIB

- Validate `paramId`, source unit, level, step type and data type from GRIB
  metadata rather than from the filename.
- Derive `grid_id` from GRIB `md5GridSection`; never assume all future files use
  the same grid.
- Match all 20 inputs by GRIB `paramId` and `shortName`, then require each
  time/grid step to have exactly one aligned message from every field.
- The six added fields (`co`, `no2`, `o3`, `so2`, `t_model`, `q_model`) must
  use hybrid model level 60. Surface and hybrid GRIB grid section hashes may
  differ; validate identical ordered coordinates and shape before aligning
  the fields to the reference surface grid ID.
- Store one `cams_cube_standard` row per time/grid with 20 `ARRAY<FLOAT>` standard fields.
  Array position is zero-based `cams_grid_point.grid_point_id`. Float32 reduces
  storage; conversion uses decoded float64 before rounding. The unchanged GRIB is the
  exact-value source of record.
- Pipeline v4 uses new standard tables to keep legacy native cube values
  separate. No historical rows are automatically converted or backfilled.
- `cams_cube_standard_source` stores one row per original GRIB file, its SHA-256, unit,
  variable ID, and conversion `native * standard_scale + standard_offset`.
  Gas scale/offset are NULL because the factor depends on aligned local
  density. `conversion_method` and `conversion_metadata` document L60 A/B,
  their source, pressure/temperature/humidity inputs, Rd and epsilon.
- PM and four model-level gases (including CO) are stored in `ug/m3`;
  total columns in `mg/m2`; temperatures in `degC`; pressures in `hPa`;
  wind in `m/s`; `q_model` in `kg/kg`; AOD in `1`. Do not rescale these arrays.
  Gas density uses `(p_half59+p_half60)/2`, Kelvin temperature and specific
  humidity, with validated L60 GRIB coefficients preferred to the official
  six-decimal ECMWF table. Missing/invalid inputs fail without defaults or
  concentration fabrication. See [job contract and formulas](../../spark/jobs/silver/README.md#cams-cube).
- GRIB validity times are UTC instants. Spark displays `cams_cube_standard.valid_time`
  in Vietnam time. Duplicate or out-of-order source times fail the run.
  Instantaneous analysis step zero and 3-hour UTC timestamps are required;
  gaps are kept without interpolation. Read standard cube rows only when
  their `ingestion_run` has `status='succeeded'`, since failed runs can have
  already committed earlier valid chunks. Provenance quality is interpreted
  together with this run status.
- The old point-per-row `cams_observation` table, if present, is legacy data;
  this schema does not delete or migrate it.

### Administrative reference data

- Preserve administrative codes as strings so leading zeroes are not lost.
- Store postal codes as an array rather than a comma-separated string.
- `admin_unit` is the conformed, versioned entity. Each contributing source is
  recorded in `admin_unit_source`; boundary lineage is recorded directly in
  `admin_boundary`.
- Do not label a source snapshot date as a legal effective date unless the
  source provides that fact. `valid_from` and `valid_to` may remain `NULL`.

### Climate TRACE

- Normalize blank `sector` and `subsector` cells to `NULL`.
- Generate `aggregate_id` after normalization, using explicit sentinels for
  nullable hierarchy fields as documented in `silver.sql`.
- Namespace point-source IDs with the source system.
- The current source file contains exact duplicate source observations. Remove
  exact duplicates before `MERGE`, count them in `duplicate_rows`, and reject
  any duplicate logical key whose non-key values conflict.

### API Ninjas province air quality

- Register the live dataset with `source_system=api_ninjas` and
  `dataset_name=province_air_quality`; keep it separate from WAQI datasets and
  tables.
- Each source row is a reading at the configured `query_city` coordinate used
  as a proxy for `province_name_source`. Set `spatial_representation` to
  `city_proxy`; never describe the value as a province-wide spatial average.
- Generate `location_id` deterministically from the dataset ID plus normalized
  source province name, query city and country. Coordinates are observed
  attributes and are not part of the identity, so minor coordinate corrections
  do not create a second logical location.
- API Ninjas supplies no observation timestamp for this dataset. Parse
  `collected_at_utc` as an offset-aware instant and derive
  `snapshot_hour_utc` by truncating that instant to its UTC hour. Never truncate
  it in the Spark session's display timezone.
- Generate `snapshot_id` from `(dataset_id, location_id, snapshot_hour_utc)`.
  When retries produce multiple rows for that key, retain the row with the
  greatest `collected_at_utc`. If the latest timestamp is tied and values
  conflict, fail the run rather than choosing nondeterministically.
- Keep pollutant concentration and AQI columns distinct. Preserve documented
  API units without guessing or converting units from the magnitude alone.
- A null metric must have an entry in `missing_reasons`; a present metric must
  not. Source zeroes remain zero and must not be treated as missing.
- Resolve `admin_unit_version_id` against the province version active for the
  snapshot when possible. An unresolved match remains null and must produce a
  data-quality finding; the original province name is always retained.
- Require `snapshot_hour_utc` to equal the UTC-hour truncation of
  `collected_at_utc`; concentrations must be non-negative when present.

## Data-quality invariants

At minimum, each pipeline run must validate:

- referenced dataset, run, variable, station, grid, administrative unit and
  emission source IDs exist;
- latitude is between -90 and 90, longitude is between -180 and 180, and bounding
  boxes have minimum values no greater than maximum values;
- row counts are non-negative, `finished_at >= started_at`, and a succeeded run
  has a finish time;
- `attempt_number` is positive and unique within a `logical_run_id`, and at most
  one attempt per logical run has status `succeeded`;
- required SHA-256 values are 64 lowercase hexadecimal characters, and
  `source_file` is a normalized relative POSIX path without `..` segments;
- Bronze file metadata has no null identity/hash/size fields, duplicate file
  paths, or object paths outside the declared batch's `files/` prefix;
- `valid_to` is null or no earlier than `valid_from`;
- `admin_match_confidence` is null or between 0 and 1;
- `aqi_value` is not silently rounded from a non-integral source value;
- a missing measurement has a `missing_reason`, while a present measurement
  does not;
- aggregate hierarchy matches its level: totals have no sector/subsector,
  sectors have a sector and no subsector, and subsectors have both;
- `period_end >= period_start` and the dates agree with `period_type`.
- Climate TRACE quantities are finite; signed finite emission values are
  retained without assuming that all native quantities are positive. Year
  labels must be four-digit valid years and agree with monthly periods.

## Initial physical layout

Large fact tables are partitioned by Iceberg time transforms. `cams_cube_standard`
uses `year(valid_time)`; each row holds all 20 variables. API Ninjas hourly
snapshots use `month(snapshot_hour_utc)`.
`ingestion_run` and small dimensions are intentionally
unpartitioned. `data_quality_issue` remains day-partitioned because row/field
findings may grow much faster than run metadata; Iceberg partition evolution
can remove that partition later if measured volume stays small.
Monitor file counts and query plans after the first full load, then add Iceberg
sort orders or adjust target file size based on measured workloads rather than
creating relational indexes.
