# Bronze to Silver Spark jobs

These jobs implement only Bronze-to-Silver transformation. They read immutable
raw objects plus `_file_metadata` and `_ingestion_manifest` from a completed
Bronze batch, and write Apache Iceberg tables in `nessie.silver` with `MERGE
INTO`. They do not read Landing and do not implement Airflow, Gold, or retry
orchestration.

## Confirmed Bronze inputs and mappings

| Job | Bronze input | Main mapping and transform | Silver targets |
| --- | --- | --- | --- |
| `admin_bronze_to_silver.py` | `reference/vietnam_administrative_divisions`: 34 provinces and 3,321 wards in JSON; `reference/vietnamese-provinces-database`: the same entity levels plus 3,355 GeoJSON files | Preserve codes as strings, retain postal codes as arrays, version by code + source snapshot, convert GeoJSON to WKB, retain source bbox/area and EPSG:4326 | `admin_unit`, `admin_unit_source`, `admin_boundary` |
| `cams_bronze_to_silver.py` | 14 EAC4 GRIB files | Read `paramId`, unit, level, step/data type and `md5GridSection` with ecCodes; separate grid/points from observations; apply only registered physical unit conversions | `variable`, `cams_grid`, `cams_grid_point`, `cams_observation` |
| `waqi_bronze_to_silver.py` | 17 historical CSV files | Parse `yyyy/M/d`, use normalized full relative filename as missing station identity, preserve blank measurements as NULL, unpivot daily AQI columns, record both present and absent canonical columns | `variable`, `waqi_station`, `waqi_station_source`, `waqi_station_variable`, `waqi_daily_observation` |
| `climate_trace_bronze_to_silver.py` | Annual/monthly aggregate CSV and annual point-source CSV | Keep totals/sectors/subsectors separate, namespace native source IDs, derive periods and deterministic aggregate IDs, remove exact duplicates and reject conflicts | `variable`, `emission_aggregate`, `emission_source`, `emission_source_observation` |

The current 14 CAMS files contain 940,912 GRIB messages. At 575 native grid
points per message they expand to 541,024,400 Silver observation rows. The CAMS
job therefore streams one local Bronze copy at a time and merges bounded
100,000-row chunks; it never constructs a whole-file observation list in
driver memory.

The Climate TRACE CSV does not declare an emissions unit. The native quantity
is therefore retained and `emission_quantity_standard` remains NULL instead of
performing an unsupported conversion. `period_status` is `actual` when the
period is complete at Bronze ingestion time and `partial` when its end date is
still in the future.

## Run

Build/start the data services and Spark master first:

```powershell
docker compose up -d --build minio minio-init nessie spark-master
```

The following PowerShell helper discovers the most recently modified completed
Bronze batch. It selects only batches containing
`_ingestion_manifest/_SUCCESS`, builds the full `s3a://` path, and passes that
path to the requested Silver job. The ingestion date and batch ID never need
to be copied from MinIO manually.

```powershell
function Invoke-LatestSilverBatch {
    param(
        [Parameter(Mandatory)] [string] $BronzePrefix,
        [Parameter(Mandatory)] [string] $Job,
        [string] $DriverMemory = "768m"
    )

    $findCommand = 'mc alias set local http://minio:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" >/dev/null && ' +
        "mc find local/lakehouse/bronze/$BronzePrefix --name _SUCCESS --json"

    $rawOutput = & docker compose run --rm --no-deps --entrypoint /bin/sh `
        minio-init -c $findCommand 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "Could not list Bronze batches for $BronzePrefix`: $($rawOutput -join [Environment]::NewLine)"
    }

    $latest = $rawOutput |
        ForEach-Object {
            try { $_ | ConvertFrom-Json -ErrorAction Stop } catch { $null }
        } |
        Where-Object {
            $_.status -eq "success" -and
            $_.key -like "*/_ingestion_manifest/_SUCCESS"
        } |
        Sort-Object { [DateTimeOffset] $_.lastModified } -Descending |
        Select-Object -First 1

    if (-not $latest) {
        throw "No completed Bronze batch found below bronze/$BronzePrefix"
    }

    $relativeBatch = $latest.key -replace '^local/lakehouse/', '' `
                                      -replace '/_ingestion_manifest/_SUCCESS$', ''
    $bronzePath = "s3a://lakehouse/$relativeBatch"
    Write-Host "Running $Job with latest completed batch: $bronzePath"

    & docker compose exec -T spark-master /opt/spark/bin/spark-submit `
        --master "local[1]" `
        --driver-memory $DriverMemory `
        --conf "spark.sql.shuffle.partitions=4" `
        "/opt/spark/work-dir/jobs/silver/$Job" `
        --bronze-path $bronzePath

    if ($LASTEXITCODE -ne 0) {
        throw "Silver ETL failed for $bronzePath"
    }
}
```

Run the latest completed WAQI batch:

```powershell
Invoke-LatestSilverBatch -BronzePrefix "waqi/historical" -Job "waqi_bronze_to_silver.py"
```

Run the latest completed batch for every currently supported Bronze dataset:

```powershell
Invoke-LatestSilverBatch -BronzePrefix "waqi/historical" -Job "waqi_bronze_to_silver.py"
Invoke-LatestSilverBatch -BronzePrefix "cams/eac4" -Job "cams_bronze_to_silver.py" -DriverMemory "1g"
Invoke-LatestSilverBatch -BronzePrefix "climate_trace/climate_trace_vietnam" -Job "climate_trace_bronze_to_silver.py"
Invoke-LatestSilverBatch -BronzePrefix "reference/vietnam_administrative_divisions" -Job "admin_bronze_to_silver.py"
Invoke-LatestSilverBatch -BronzePrefix "reference/vietnamese-provinces-database" -Job "admin_bronze_to_silver.py"
```

Define the helper and call it in the same PowerShell session. Before a large
local run, optional services can be stopped to leave more memory for Spark:

```powershell
docker compose stop airflow-webserver airflow-scheduler trino spark-worker postgres
```

Bring the complete stack back afterwards with `docker compose up -d`. Use
`--master spark://spark-master:7077` instead of `local[1]` when deliberately
running against the worker. The image installs ecCodes for streaming GRIB
decoding and Shapely for GeoJSON-to-WKB conversion on both driver and
executors.

Every job skips a logical run that already succeeded. A new physical attempt
gets a UUID run ID; exact duplicates are counted, while conflicting logical
keys produce `data_quality_issue` rows and fail the attempt.
