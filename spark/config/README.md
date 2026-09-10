# Spark configuration

`spark-defaults.conf` is mounted into both Spark containers, keeping the
Iceberg, Nessie, and MinIO settings in one visible place. It reads MinIO
credentials from the container environment, which Compose supplies from `.env`.
