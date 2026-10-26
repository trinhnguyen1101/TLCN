# Bronze to Silver Spark jobs

These jobs read completed Bronze batches and write Iceberg tables in
`nessie.silver`. Spark displays timestamps in `Asia/Ho_Chi_Minh` (UTC+07:00).
Bronze GRIB validity times are UTC instants; WAQI daily dates are already
Vietnam-local calendar dates.

| Job | Input | Main Silver tables |
| --- | --- | --- |
| `admin_bronze_to_silver.py` | Administrative JSON/CSV/GeoJSON | `admin_unit`, `admin_unit_source`, `admin_boundary` |
| `cams_bronze_to_silver.py` | 20 aligned EAC4 GRIB files | `variable`, `cams_grid`, `cams_grid_point`, `cams_cube_source`, `cams_cube` |
| `waqi_bronze_to_silver.py` | 17 historical CSV files, one station per file | `variable`, `waqi_station`, `waqi_station_source`, `waqi_station_variable`, `waqi_daily_observation` |
| `climate_trace_bronze_to_silver.py` | Annual/monthly emissions CSV | `variable`, `emission_aggregate`, `emission_source`, `emission_source_observation` |

## CAMS cube

The 20-file input covers native EAC4 time steps on a 23 × 25 grid.
`cams_cube` stores one row per time/grid with 20 `ARRAY<FLOAT>` columns.
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
Gases retain their native mass mixing ratio in `kg kg**-1`; `q_model` is
specific humidity in the same unit. They are not converted to concentrations.

Native values are stored as float32. GRIB is retained in Bronze for exact
source values. `cams_cube_source` holds the 20 file paths and hashes plus
scale/offset for standard units. The job copies each Bronze GRIB file to the
container's temporary disk, reads the files in lockstep, and commits bounded
512-time-step Iceberg `MERGE` chunks. Allow at least 3 GB temporary disk.
Progress appears as `CAMS cube committed N time/grid rows`.

The CAMS pipeline version is `3.0.0`, so an older successful 14-field run
does not cause this job to skip. At startup the job explicitly adds any of
the six missing model-level array columns to an existing `cams_cube` with
`ALTER TABLE ADD COLUMNS`. Historical rows retain `NULL` in those columns
until their time range is reprocessed from a completed 20-file Bronze batch.
New writes align fields by name even when Iceberg appends migrated columns
after existing lineage columns. Original arrays and legacy
`cams_observation` data are retained. Old 14-file Bronze batches cannot be
processed by v3; ingest a new full 20-file batch first.
The new WAQI pipeline version is also `2.0.0` so rerunning it updates
existing station rows with their Vietnam timezone.

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
  --py-files /opt/spark/work-dir/jobs/silver/common.py \
  /opt/spark/work-dir/jobs/silver/cams_bronze_to_silver.py \
  --bronze-path "s3a://lakehouse/bronze/cams/eac4/ingestion_date=$ingestion_date/batch_id=$batch_id"
```

To select the latest completed Bronze batch automatically, use this Bash
helper in the same terminal session. It requires `jq` on the host:

```bash
invoke_latest_silver_batch() {
  local prefix="${1:?Bronze prefix required}"
  local job="${2:?Silver job required}"
  local memory="${3:-768m}"
  local command output key bronze_path

  command="mc alias set local http://minio:9000 \"\$MINIO_ROOT_USER\" \"\$MINIO_ROOT_PASSWORD\" >/dev/null && mc find local/lakehouse/bronze/$prefix --name _SUCCESS --json"
  output=$(docker compose run --rm --no-deps --entrypoint /bin/sh minio-init -c "$command") || return
  key=$(printf '%s\n' "$output" |
    jq -Rr 'fromjson? | select(.status == "success" and (.key | endswith("/_ingestion_manifest/_SUCCESS"))) | [.lastModified, .key] | @tsv' |
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
    --py-files /opt/spark/work-dir/jobs/silver/common.py \
    "/opt/spark/work-dir/jobs/silver/$job" --bronze-path "$bronze_path"
}

invoke_latest_silver_batch "cams/eac4" "cams_bronze_to_silver.py" "1g"
invoke_latest_silver_batch "waqi/historical" "waqi_bronze_to_silver.py"
```

Only one CAMS Silver run should write to `cams_cube` at a time. After
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
       c.pm2p5[CAST(p.grid_point_id + 1 AS integer)] AS pm2p5_native
FROM iceberg.silver.cams_cube AS c
JOIN iceberg.silver.cams_grid_point AS p ON c.grid_id = p.grid_id
WHERE p.grid_point_id = 0
ORDER BY c.valid_time
LIMIT 10;
```

See [the Silver data contract](../../../lakehouse/silver/README.md) for
logical keys, provenance, and timezone rules.

Driver regression checks (no Spark JVM required), from the repository root:

```powershell
.\backend\.venv\Scripts\python.exe -m unittest discover -s spark/jobs/silver/tests -v
```

These cover 20-stream alignment, native units, schema migration and migrated
column ordering. They mock Spark writes; a running lakehouse is required to
validate actual Iceberg commits.


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
