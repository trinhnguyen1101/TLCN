# Silver layer

`silver.sql` defines the cleaned, standardized layer as Apache Iceberg tables
in the `nessie.silver` namespace. It is Spark SQL, not PostgreSQL SQL.

## Design rules

- Bronze files remain immutable. Every file-derived Silver row must be
  traceable through `ingestion_run_id`, `source_file`, and
  `source_file_sha256`; conformed rows trace through their source-mapping table.
- Business/entity IDs stored as `STRING` are deterministic UUIDs or hashes.
  `ingestion_run.run_id` is the deliberate exception: it identifies one
  physical attempt and is a new UUID for every retry.
- Primary and foreign keys in this document are logical constraints. Bronze to
  Silver jobs must validate them because Iceberg does not enforce relational
  constraints.
- Jobs must use `MERGE INTO` on the logical key of each target table. Replaying
  an already successful logical run must not add rows or alter fact values.
- Timestamps are UTC. A source timezone is retained separately when it exists.
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
| `cams_observation` | `dataset_id, valid_time, grid_id, grid_point_id, variable_id` |
| `waqi_station` | `station_id` |
| `waqi_station_source` | `dataset_id, source_station_key` |
| `waqi_station_variable` | `dataset_id, station_id, variable_id` |
| `waqi_daily_observation` | `dataset_id, station_id, observation_date, variable_id` |
| `waqi_hourly_observation` | `dataset_id, station_id, observation_time_utc` |
| `waqi_hourly_measurement` | `dataset_id, station_id, observation_time_utc, variable_id` |
| `emission_aggregate` | `aggregate_id` |
| `emission_source` | `source_id` |
| `emission_source_observation` | `dataset_id, source_id, year_label, variable_id` |

## Source-specific normalization

### WAQI historical CSV

- Parse `date` explicitly using `yyyy/M/d`; do not rely on locale inference.
- Trim column names and cell values. Empty strings become `NULL`.
- The pollutant columns contain daily AQI values, not concentrations.
- Build `source_station_key` from the provider station ID when available. For
  the current files, where no ID is present, use a normalized full filename and
  keep the original filename in `waqi_station_source`.
- Populate `waqi_station_variable` for both present and absent canonical WAQI
  columns so schema differences between station files remain observable.

### CAMS EAC4 GRIB

- Validate `paramId`, source unit, level, step type and data type from GRIB
  metadata rather than from the filename.
- Derive `grid_id` from GRIB `md5GridSection`; never assume all future files use
  the same grid.
- Convert native values only through the registered `variable` conversion and
  retain both `value_native` and `value_standard`.
- Within a run, identical duplicate timestamps may be skipped and counted;
  conflicting values for the same observation key fail the run.

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
- `valid_to` is null or no earlier than `valid_from`;
- `admin_match_confidence` is null or between 0 and 1;
- `aqi_value` is not silently rounded from a non-integral source value;
- a missing measurement has a `missing_reason`, while a present measurement
  does not;
- aggregate hierarchy matches its level: totals have no sector/subsector,
  sectors have a sector and no subsector, and subsectors have both;
- `period_end >= period_start` and the dates agree with `period_type`.

## Initial physical layout

Large fact tables are partitioned by Iceberg time transforms; CAMS also uses
the variable identity. `ingestion_run` and small dimensions are intentionally
unpartitioned. `data_quality_issue` remains day-partitioned because row/field
findings may grow much faster than run metadata; Iceberg partition evolution
can remove that partition later if measured volume stays small.
Monitor file counts and query plans after the first full load, then add Iceberg
sort orders or adjust target file size based on measured workloads rather than
creating relational indexes.
