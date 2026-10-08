# Air Quality Lakehouse (local bootstrap)

This repository contains a local Docker Compose foundation for an air-quality
Lakehouse, a React dashboard, and a FastAPI backend using Python 3.12.
The backend serves the current temporary CAMS EAC4 sample from
`backend/data/samples/`. It has not passed the official processing/validation
pipeline and is not Gold data. The dashboard uses the Parquet source directly.
The dashboard now reads native 3-hour UTC observations by default, with daily
and monthly views for longer periods. The portable sample includes native
2024–2025 rows; the local dataset retains full 2003–2025 native history.

## Run the dashboard

See [Hướng dẫn thiết lập web dashboard](docs/setup-web-dashboard.md) for prerequisites,
ETL, backend/frontend startup, time filters, checks, and deployment.
The dashboard does not require the Docker Compose lakehouse services below.

## Architecture

`Airflow` orchestrates future jobs. `Spark` will read/write Iceberg tables.
Iceberg metadata is catalogued by `Nessie`, while the physical data lives in
the `lakehouse` bucket in `MinIO` (`bronze/`, `silver/`, and `gold/` prefixes).
`Trino` queries the same Nessie catalog and MinIO warehouse as Spark.
`PostgreSQL` is only Airflow's metadata database.

## Version set

| Component | Version | Reason |
|---|---:|---|
| Apache Spark | 3.5.4 / Scala 2.12 / Java 17 | Stable Spark 3.5 line; the Iceberg runtime artifact targets exactly this binary API. |
| Apache Iceberg | 1.7.1 | `iceberg-spark-runtime-3.5_2.12` supplies Spark extensions and Nessie catalog support. |
| Project Nessie | 0.104.5 | Used through the current REST API v2 at `/api/v2`. |
| Trino | 476 | Includes the Iceberg connector and Nessie catalog support. |
| Airflow | 2.10.5 / Python 3.12 | Uses PostgreSQL metadata storage. |
| PostgreSQL | 16.6 | Airflow metadata database. |
| MinIO | RELEASE.2025-02-18T16-25-55Z | S3-compatible object store. |

The Spark image downloads only the three JARs documented in `spark/jars/README.md`.
Iceberg is a library/table format, **not** a Compose service.

## Start and stop

1. Review local credentials and ports in `.env` (these are development-only sample values).
2. Start the stack:

   ```powershell
   docker compose config
   docker compose up -d --build
   docker compose ps
   ```

3. Stop containers while retaining data:

   ```powershell
   docker compose down
   ```

4. Reset all persisted state (destructive):

   ```powershell
   docker compose down -v
   ```

## Local endpoints

| Service | URL | Default local port |
|---|---|---:|
| Airflow | http://localhost:8080 | 8080 |
| Spark Master UI | http://localhost:8081 | 8081 |
| Spark Worker UI | http://localhost:8082 | 8082 |
| MinIO API | http://localhost:9000 | 9000 |
| MinIO Console | http://localhost:9001 | 9001 |
| Nessie API | http://localhost:19120/api/v2/config | 19120 |
| Trino | http://localhost:8083 | 8083 |

Airflow uses `AIRFLOW_ADMIN_USER` and `AIRFLOW_ADMIN_PASSWORD`; MinIO uses
`MINIO_ROOT_USER` and `MINIO_ROOT_PASSWORD`, all from `.env`.

## Basic checks

```powershell
docker compose ps
.\scripts\health-check.ps1
.\scripts\test-trino.ps1
.\scripts\test-spark.ps1
docker compose logs --tail=100 trino
```

The one-shot `minio-init` service creates the `lakehouse` bucket plus marker
objects below `bronze/`, `silver/`, and `gold/`. Its successful `Exited (0)`
state is expected.

## Next integration check (not part of this bootstrap)

Create a tiny Iceberg table in Spark using catalog `nessie`, write it to the
`s3a://lakehouse/` warehouse, then run `SHOW SCHEMAS FROM iceberg` and a
`SELECT` in Trino. Both engines are already configured to use the same Nessie
API v2 endpoint and MinIO bucket, so neither has a separate metastore.
