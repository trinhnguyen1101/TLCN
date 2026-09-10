# Basic local health checks. Run after `docker compose up -d --build`.
$ErrorActionPreference = 'Stop'
docker compose ps
Invoke-WebRequest "http://localhost:$env:AIRFLOW_PORT/health" -UseBasicParsing | Select-Object StatusCode
Invoke-WebRequest "http://localhost:$env:SPARK_MASTER_UI_PORT" -UseBasicParsing | Select-Object StatusCode
Invoke-WebRequest "http://localhost:$env:MINIO_API_PORT/minio/health/live" -UseBasicParsing | Select-Object StatusCode
Invoke-WebRequest "http://localhost:$env:NESSIE_PORT/api/v2/config" -UseBasicParsing | Select-Object StatusCode
Invoke-WebRequest "http://localhost:$env:TRINO_PORT/v1/info" -UseBasicParsing | Select-Object StatusCode
