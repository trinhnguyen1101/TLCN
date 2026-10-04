# Spark configuration

`spark-defaults.conf` is mounted into both Spark containers, keeping the
Iceberg, Nessie, and MinIO settings in one visible place. It reads MinIO
credentials from the container environment, which Compose supplies from `.env`.
The custom JARs are baked into the Spark image and listed in `spark.jars`.
Compose mounts `data/landing` read-only in both Spark containers so executors
can read the same input paths as the driver.
