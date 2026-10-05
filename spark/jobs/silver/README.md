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

Apply a job to one completed Bronze batch. Examples use the verified batches
documented in `docs/landing-to-bronze.md`:

```powershell
docker compose exec -T spark-master /opt/spark/bin/spark-submit --master local[1] /opt/spark/work-dir/jobs/silver/waqi_bronze_to_silver.py --bronze-path s3a://lakehouse/bronze/waqi/historical/ingestion_date=2026-10-03/batch_id=raw-waqi-001

docker compose exec -T spark-master /opt/spark/bin/spark-submit --master local[1] /opt/spark/work-dir/jobs/silver/cams_bronze_to_silver.py --bronze-path s3a://lakehouse/bronze/cams/eac4/ingestion_date=2026-10-03/batch_id=raw-cams-001

docker compose exec -T spark-master /opt/spark/bin/spark-submit --master local[1] /opt/spark/work-dir/jobs/silver/climate_trace_bronze_to_silver.py --bronze-path s3a://lakehouse/bronze/climate_trace/climate_trace_vietnam/ingestion_date=2026-10-03/batch_id=raw-climate-trace-001

docker compose exec -T spark-master /opt/spark/bin/spark-submit --master local[1] /opt/spark/work-dir/jobs/silver/admin_bronze_to_silver.py --bronze-path s3a://lakehouse/bronze/reference/vietnam_administrative_divisions/ingestion_date=2026-10-03/batch_id=raw-reference-admin-001

docker compose exec -T spark-master /opt/spark/bin/spark-submit --master local[1] /opt/spark/work-dir/jobs/silver/admin_bronze_to_silver.py --bronze-path s3a://lakehouse/bronze/reference/vietnamese-provinces-database/ingestion_date=2026-10-03/batch_id=raw-reference-geojson-001
```

Use `--master spark://spark-master:7077` when the worker is running. The image
installs ecCodes for streaming GRIB decoding and Shapely for GeoJSON-to-WKB
conversion on both driver and executors.

Every job skips a logical run that already succeeded. A new physical attempt
gets a UUID run ID; exact duplicates are counted, while conflicting logical
keys produce `data_quality_issue` rows and fail the attempt.
