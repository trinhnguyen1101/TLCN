# Spark configuration

`spark-defaults.conf` is mounted into both Spark containers, keeping the
Iceberg, Nessie, and MinIO settings in one visible place. It reads MinIO
credentials from the container environment, which Compose supplies from `.env`.
The custom JARs are baked into the Spark image and listed in `spark.jars`.
Silver Spark sessions use `Asia/Ho_Chi_Minh` (UTC+07:00) for timestamp display
and SQL date/time functions. CAMS GRIB UTC validity times are converted as
instants; WAQI daily `date` values remain Vietnam-local calendar dates.
Iceberg vectorized reads are disabled because they triggered JVM crashes on
the CAMS workload in this environment.
Compose mounts `data/landing` read-only in both Spark containers so executors
can read the same input paths as the driver.
