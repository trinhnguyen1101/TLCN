# Bronze to Silver Spark jobs

These jobs read completed Bronze batches and write Iceberg tables in
`nessie.silver`. Spark displays timestamps in `Asia/Ho_Chi_Minh` (UTC+07:00).
Bronze GRIB validity times are UTC instants; WAQI daily dates are already
Vietnam-local calendar dates.

| Job | Input | Main Silver tables |
| --- | --- | --- |
| `admin_bronze_to_silver.py` | Administrative JSON/CSV/GeoJSON | `admin_unit`, `admin_unit_source`, `admin_boundary` |
| `cams_bronze_to_silver.py` | 20 aligned EAC4 GRIB files | `variable`, `cams_grid`, `cams_grid_point`, `cams_cube_standard_source`, `cams_cube_standard` |
| `waqi_bronze_to_silver.py` | 17 historical CSV files, one station per file | `variable`, `waqi_station`, `waqi_station_source`, `waqi_station_variable`, `waqi_daily_observation` |
| `climate_trace_bronze_to_silver.py` | Annual/monthly emissions CSV | `variable`, `emission_aggregate`, `emission_source`, `emission_source_observation` |
| `supabase_bronze_to_silver.py` | Supabase private raw API JSON + provider manifests | WAQI hourly tables or `province_air_quality_*` |

## Supabase live ingestion

`supabase_bronze_to_silver.py` accepts `--source waqi` or
`--source api_ninjas` and a completed Bronze batch path. WAQI uses provider
`data.time.iso` as observation time; API Ninjas uses the collection run's
scheduled UTC hour. The API Ninjas city proxy is mapped to the current
`admin_unit` province by name and checked against `admin_boundary` geometry.
One existing Nha Trang point is about 160 m outside the Khánh Hoà polygon;
named matches within 250 m are accepted with `mapping_confidence=0.9` and a
`province_proxy_near_boundary` warning. Greater mismatches and missing or
ambiguous province mapping fail with a quality issue. The 2026-10-26 04:00 UTC
batch was verified with 34 observations and 408
measurements. A second run of the same batch was skipped without adding rows.

AQI and concentration are separate variable IDs. API Ninjas concentration
`standard_unit` and `value_standard` stay NULL until the provider unit is
confirmed. WAQI IAQI is recorded as AQI, not mass concentration. Invalid
provider responses remain in Bronze; the Silver job records quality issues
and skips those observations. `partial` responses retain missing fields with
their reason. Conflicting logical keys fail the run.
The proxy location row points to the provider manifest that supplied its
query coordinates; observation rows point to raw response files.

Build the Spark image after the dependency change. Run the following entire
block in one Bash terminal. The example selects the UTC hour 04:00–05:00 on
2026-10-26; change the date and hour together for another run. Silver starts
only after Bronze succeeds:

```bash
docker compose build spark-master spark-worker
docker compose up -d --force-recreate spark-master spark-worker

window_start=2026-10-26T04:00:00Z
window_end=2026-10-26T05:00:00Z
ingestion_date=2026-10-27
batch_id=waqi-live-20261026-04
bronze_path="s3a://lakehouse/bronze/waqi/live/ingestion_date=$ingestion_date/batch_id=$batch_id"

if docker compose exec -T spark-master /opt/spark/bin/spark-submit \
     --master 'local[1]' --driver-memory 1g \
     /opt/spark/work-dir/jobs/bronze/supabase_to_bronze.py \
     --source waqi --window-start "$window_start" --window-end "$window_end" \
     --batch-id "$batch_id" --ingestion-date "$ingestion_date"; then
  docker compose exec -T spark-master /opt/spark/bin/spark-submit \
    --master 'local[1]' --driver-memory 1g \
    --py-files /opt/spark/work-dir/jobs/silver/common.py \
    /opt/spark/work-dir/jobs/silver/supabase_bronze_to_silver.py \
    --source waqi --bronze-path "$bronze_path"
fi
```

Replace `waqi` with `api_ninjas` and use the corresponding
`bronze/api_ninjas/province_air_quality/...` path for the second source.
Windows are half open UTC intervals. Reuse the same window and batch ID when
retrying; an existing complete batch is checked against the source fingerprint.
The run records and row lineage are kept in `nessie.silver.ingestion_run`.

## CAMS cube

The 20-file input covers native EAC4 time steps on a 23 × 25 grid.
`cams_cube_standard` stores one row per time/grid with 20 `ARRAY<FLOAT>` columns.
The historical 2003–2025 input has 67,208 time steps per variable. Index 0 in
each array is `cams_grid_point.grid_point_id = 0`; the same index convention
continues through all 575 points. The job validates every file's GRIB
`paramId` and `shortName`, aligned times, grid identity, coordinates,
finite values, and complete message counts.

The six model-level fields are `co` (210123/co), `no2` (210121/no2),
`o3` (210203/go3), `so2` (210122/so2), `t_model` (130/t), and
`q_model` (133/q). All six must be at hybrid model level 60. GRIB grid
section hashes differ between the surface and model-level files because of
vertical metadata. The job requires identical ordered latitude/longitude
coordinates and shape before aligning their arrays to the reference surface
grid. It retains the reference grid ID used by the older 14-field cube.

Pipeline v4 writes standard values directly, using float64 for calculations
and float32 only for final arrays. The native `cams_cube` and
`cams_cube_source` tables from v2/v3 remain unchanged; they are legacy input
contracts, not standard concentrations. New output goes only to the standard
tables, with the same column names and logical keys. No historical backfill
is automatic. Consumers moving to `cams_cube_standard` must remove any unit
scaling they previously applied to native arrays.

| Columns | Native GRIB unit | Stored standard unit | Conversion |
| --- | --- | --- | --- |
| `pm1`, `pm2p5`, `pm10` | kg m⁻³ | ug/m3 | × 10⁹ |
| `co`, `no2`, `so2`, `o3` | kg kg⁻¹ | ug/m3 | × local air density × 10⁹ |
| `co_column`, `no2_column`, `so2_column`, `o3_column` | kg m⁻² | mg/m2 | × 10⁶ |
| `t2m`, `d2m`, `t_model` | K | degC | − 273.15 |
| `sp`, `mslp` | Pa | hPa | ÷ 100 |
| `u10`, `v10` | m s⁻¹ | m/s | unchanged |
| `q_model` | kg kg⁻¹ | kg/kg | unchanged |
| `aod550` | ~ or 1 | 1 | unchanged |

Gas conversion happens at each aligned time/grid point, before aggregation:

```text
p_half[k] = A[k] + B[k] * sp_Pa
p_full[60] = (p_half[59] + p_half[60]) / 2
Tv_K = t_model_K * (1 + (1 - 0.621981) / 0.621981 * q_model)
rho_kg_m3 = p_full[60] / (287.05 * Tv_K)
gas_ug_m3 = native_kg_kg * rho_kg_m3 * 1e9
```

`pv` must contain 61 A [Pa], then 61 B [1] coefficients, indexed 0..60.
Every supplied coefficient is checked against the official
[ECMWF L60 table](https://confluence.ecmwf.int/spaces/UDOC/pages/108117131/L60+model+level+definitions).
Validated GRIB coefficients take precedence; only their absence permits the
published table (six decimal places). Invalid supplied coefficients fail the
run. L137, conflicting coefficients, changing coefficients, nonpositive
pressure/temperature, q outside [0,1), negative concentrations, missing or
nonfinite values fail without substitution or clipping. `mslp` is never used
for density. Reference and valid times must agree, with analysis step zero
on the 3-hour UTC grid; gaps are retained, without interpolation.

GRIB is retained in Bronze for exact source values. The job verifies SHA-256
and file size after copying each source. `cams_cube_standard_source` holds
the 20 file paths and hashes, source and stored units, conversion method,
coefficients and their reference, and quality policy. Linear conversions use
`native * standard_scale + standard_offset`. Gas scale/offset are NULL
because density varies; their conversion metadata identifies the three
aligned density inputs, Rd and epsilon. Join cube -> source on dataset/batch,
then source -> ingestion_run -> Bronze manifest to locate original GRIB;
cube time and grid-point index locate the original value. No raw-value
arrays are duplicated in the new tables. Failures are recorded in
`ingestion_run` and `data_quality_issue`, preserving Bronze for retry.

The job copies each Bronze GRIB file to the
container's temporary disk, reads the files in lockstep, and commits bounded
512-time-step Iceberg `MERGE` chunks. Allow at least 3 GB temporary disk.
Progress appears as `CAMS cube committed N time/grid rows`.

The CAMS pipeline version is `4.0.0`, so an older successful native run
does not cause this job to skip. Old 14-file Bronze batches cannot be
processed by v4; ingest a new full 20-file batch first. Successful runs of
the same version/batch are skipped. Retry after failure MERGEs the logical
key `(dataset_id, valid_time, grid_id)`; all conversions read Bronze again,
never Silver. New writes align fields by name even when the physical schema
has a different column order. `input_rows` counts scalar source values;
`output_rows` counts time/grid cube rows, so a complete 575-point batch has
`input_rows = output_rows * 20 * 575`, with no filtering.
WAQI pipeline `2.1.0` additionally rejects nonfinite, negative, fractional
and out-of-INT-range AQI before casting. Climate TRACE pipeline `1.1.0`
rejects nonfinite quantities and inconsistent year/month periods, and
allows absent optional `asset_type` metadata without fabricating a value.

The complete five-dataset manual sequence, including both administrative
sources and their shared tables, is in [docs/RUN.md](../../../docs/RUN.md).

## Run from Bash

Start the required services:

```bash
docker compose up -d minio minio-init nessie spark-master
```

Ingest the current 20-file Landing input as a new Bronze batch first:

```bash
ingestion_date=$(date -u +%F)
batch_id="cams-20-$(date -u +%Y%m%dT%H%M%SZ)"
docker compose exec -T spark-master \
  /opt/spark/bin/spark-submit \
  --master 'local[1]' --driver-memory 512m \
  /opt/spark/work-dir/jobs/bronze/landing_to_bronze.py \
  --dataset CAMS/EAC4 --batch-id "$batch_id" --ingestion-date "$ingestion_date"
```

After Bronze completes successfully, run Silver against that same batch:

```bash
docker compose exec -T spark-master \
  /opt/spark/bin/spark-submit \
  --master 'local[1]' \
  --driver-memory 1g \
  --conf spark.sql.shuffle.partitions=4 \
  --py-files /opt/spark/work-dir/jobs/silver/common.py,/opt/spark/work-dir/jobs/silver/cams_physics.py \
  /opt/spark/work-dir/jobs/silver/cams_bronze_to_silver.py \
  --bronze-path "s3a://lakehouse/bronze/cams/eac4/ingestion_date=$ingestion_date/batch_id=$batch_id"
```

To select the latest completed Bronze batch automatically, use this Bash
helper in the same terminal session. It excludes `cams-validation-*` test
batches and requires `jq` on the host:

```bash
invoke_latest_silver_batch() {
  local prefix="${1:?Bronze prefix required}"
  local job="${2:?Silver job required}"
  local memory="${3:-768m}"
  local command output key bronze_path

  command="mc alias set local http://minio:9000 \"\$MINIO_ROOT_USER\" \"\$MINIO_ROOT_PASSWORD\" >/dev/null && mc find local/lakehouse/bronze/$prefix --name _SUCCESS --json"
  output=$(docker compose run --rm --no-deps --entrypoint /bin/sh minio-init -c "$command") || return
  key=$(printf '%s\n' "$output" |
    jq -Rr 'fromjson? | select(.status == "success" and (.key | endswith("/_ingestion_manifest/_SUCCESS")) and (.key | contains("/batch_id=cams-validation-") | not)) | [.lastModified, .key] | @tsv' |
    LC_ALL=C sort -r | head -n 1 | cut -f 2-)
  if [[ -z "$key" ]]; then
    echo "No completed Bronze batch under $prefix" >&2
    return 1
  fi
  bronze_path="s3a://lakehouse/${key#local/lakehouse/}"
  bronze_path="${bronze_path%/_ingestion_manifest/_SUCCESS}"
  docker compose exec -T spark-master /opt/spark/bin/spark-submit \
    --master 'local[1]' --driver-memory "$memory" \
    --conf spark.sql.shuffle.partitions=4 \
    --py-files /opt/spark/work-dir/jobs/silver/common.py,/opt/spark/work-dir/jobs/silver/cams_physics.py \
    "/opt/spark/work-dir/jobs/silver/$job" --bronze-path "$bronze_path"
}

invoke_latest_silver_batch "cams/eac4" "cams_bronze_to_silver.py" "1g"
invoke_latest_silver_batch "waqi/historical" "waqi_bronze_to_silver.py"
```

Only one CAMS Silver run should write to `cams_cube_standard` at a time. After
completion, check `nessie.silver.ingestion_run` for `status='succeeded'`
and `output_rows` near 67,208. A failed or interrupted attempt may have
committed earlier chunks; the next attempt uses the cube's logical key to
update those rows instead of inserting duplicates.

## Querying one grid point in Trino

Trino array subscripts start at 1; `cams_grid_point.grid_point_id` starts
at 0:

```sql
SET TIME ZONE 'Asia/Ho_Chi_Minh';

SELECT c.valid_time, p.latitude, p.longitude,
       c.pm2p5[CAST(p.grid_point_id + 1 AS integer)] AS pm2p5_ug_m3
FROM iceberg.silver.cams_cube_standard AS c
JOIN iceberg.silver.cams_grid_point AS p ON c.grid_id = p.grid_id
JOIN iceberg.silver.ingestion_run AS r ON c.ingestion_run_id = r.run_id
WHERE p.grid_point_id = 0 AND r.status = 'succeeded'
ORDER BY c.valid_time
LIMIT 10;
```

See [the Silver data contract](../../../lakehouse/silver/README.md) for
logical keys, provenance, and timezone rules.

Driver regression checks (no Spark JVM required), from the repository root:

```bash
docker compose exec -T spark-master python3 -m unittest discover -s /opt/spark/work-dir/jobs/silver/tests -v
```

```powershell
.\backend\.venv\Scripts\python.exe -m unittest discover -s spark/jobs/silver/tests -v
```

These cover physical formulas, invalid inputs, 20-stream alignment, unit
contracts and column ordering. They mock Spark writes. To verify actual
Bronze files and Iceberg commits with the first three messages of each real
Landing GRIB (no full backfill), run:

```bash
docker compose exec -T spark-master /opt/spark/bin/spark-submit --master 'local[1]' --driver-memory 1g --conf spark.sql.shuffle.partitions=2 /opt/spark/work-dir/jobs/silver/tests/integration_cams.py
```

This opt-in check retains a unique `cams-validation-*` Bronze batch and an
isolated `EAC4-validation-*` dataset version for inspection. It checks all
20 normalized arrays, source hashes, times/coordinates, units, counts, real
MERGE replay and successful-run skipping. Production dataset IDs are not
updated. `--timesteps` accepts 1..8; `--source-dir` selects another complete
20-file input. Use `--bronze-path` to replay an existing `cams-validation-*`
batch instead of creating a new one, with `--timesteps` matching its size:

```bash
docker compose exec -T spark-master /opt/spark/bin/spark-submit --master 'local[1]' --driver-memory 1g --conf spark.sql.shuffle.partitions=2 /opt/spark/work-dir/jobs/silver/tests/integration_cams.py --bronze-path "s3a://lakehouse/bronze/cams/eac4/ingestion_date=$ingestion_date/batch_id=$batch_id" --timesteps 3
```

For this command, set the two variables to the existing validation batch,
not a production batch. The check rejects batch IDs without the validation
prefix. It reports source GRIB message count, cube row count, array count,
actual scalar counts, null/invalid counts, and valid zero PM values separately.
Inspect `CAMS_INTEGRATION_RESULT` in the output. These checks
do not establish the integrity of the entire historical archive.

Verified on 2026-10-26 with the retained batch
`cams-validation-30fffe54da92`: 20 real GRIB files, 60 messages, three UTC
timestamps at 3-hour intervals, and 575 points per grid. Iceberg contains
three cube rows, 60 arrays and 34,500 finite normalized values, with zero
null/invalid/filtered values and 15 valid PM zeros preserved. All 20 source
SHA-256 hashes matched before/after MERGE replay, normalized payloads were
identical, and the successful v4 run was skipped on rerun. Legacy table
snapshot histories were unchanged. Maximum relative rounding error from
float32 storage was 5.96e-8. All 26 unit/regression tests passed on both the
host and the Spark container's Python 3.8. This verifies the small batch only.

The backend's `app.etl.eac4`/`metrics.py` is a separate Landing -> province
Parquet path; it does not read this Silver cube. Its 14 linear conversions
remain appropriate for its native inputs, and it rejects unsupported
model-level gases. There is no Gold/API consumer of the Silver cube in this
repository. Total columns remain column masses, and PM1 is not one of the six
VN_AQI pollutants. This job does not calculate AQI.


```bash
invoke_latest_silver_batch \
  "reference/vietnam_administrative_divisions" \
  "admin_bronze_to_silver.py"

invoke_latest_silver_batch \
  "reference/vietnamese-provinces-database" \
  "admin_bronze_to_silver.py"

invoke_latest_silver_batch \
  "waqi/historical" \
  "waqi_bronze_to_silver.py"

invoke_latest_silver_batch \
  "climate_trace/climate_trace_vietnam" \
  "climate_trace_bronze_to_silver.py"

invoke_latest_silver_batch \
  "cams/eac4" \
  "cams_bronze_to_silver.py" \
  "1g"
```

## Audit all five datasets

`tests/integration_silver.py` is a read-only Spark audit of completed batches.
It validates Bronze sidecars and hashes every source file, checks logical
keys and references, compares administrative names/parents and WAQI values
against Bronze, reconciles Climate TRACE duplicate counts, and checks CAMS
array values are finite. It also executes Spark regression cases for
null/NaN/Infinity, valid zeroes, fractional AQI, INT overflow and path validation.
Use `integration_cams.py` above for independent CAMS physics verification.

Pass each completed batch explicitly; the five paths may have different
batch IDs. The audit does not ingest, transform, backfill or modify tables:

```bash
docker compose exec -T spark-master /opt/spark/bin/spark-submit --master 'local[1]' --driver-memory 1g --conf spark.sql.shuffle.partitions=4 /opt/spark/work-dir/jobs/silver/tests/integration_silver.py \
  --bronze-path "s3a://lakehouse/bronze/reference/vietnam_administrative_divisions/ingestion_date=$ingestion_date/batch_id=$batch_id" \
  --bronze-path "s3a://lakehouse/bronze/reference/vietnamese-provinces-database/ingestion_date=$ingestion_date/batch_id=$batch_id" \
  --bronze-path "s3a://lakehouse/bronze/waqi/historical/ingestion_date=$ingestion_date/batch_id=$batch_id" \
  --bronze-path "s3a://lakehouse/bronze/climate_trace/climate_trace_vietnam/ingestion_date=$ingestion_date/batch_id=$batch_id" \
  --bronze-path "s3a://lakehouse/bronze/cams/eac4/ingestion_date=$ingestion_date/batch_id=$batch_id" \
  --snapshot-output /tmp/silver-before.json
```

To check replay, rerun the five job commands with the same arguments, then
run this audit again using `--compare /tmp/silver-before.json` instead of
`--snapshot-output`. `SILVER_REPLAY_IDENTICAL=true` confirms that source
hashes, run IDs, counts and fact snapshot histories have not changed.
Dataset registry refresh timestamps are excluded. Run without concurrent
writers. The snapshot file is local to this container.

Verified on 2026-10-26 against existing Bronze batch
`raw-20261026T141739Z` for the four non-CAMS datasets and the retained
`cams-validation-30fffe54da92` batch for CAMS:

| Dataset | Input count | Output count |
| --- | --- | --- |
| Open Admin Data | 3,355 units | 3,355 units |
| Provinces database | 3,355 units + 3,355 features | 3,355 units + 3,355 boundaries |
| WAQI | 29,725 CSV rows | 179,843 daily measurements, including 55,495 source blanks |
| Climate TRACE | 61,818 CSV rows | 17,280 aggregates + 32,384 source observations |
| CAMS validation | 34,500 scalar values | 3 cube rows, 60 arrays, 34,500 values |

Climate TRACE removes 12,154 identical duplicate observations from its native
source CSV, as recorded in `ingestion_run.duplicate_rows`; no distinct
observation keys were lost. All 3,414 Bronze source-file hashes matched both
before and after replay. The five successful job reruns kept run IDs, counts
and fact snapshot histories unchanged (`SILVER_REPLAY_IDENTICAL=true`). No
full CAMS historical backfill was performed. The 26 CAMS unit tests and
the Spark numeric/path regression cases also passed.
