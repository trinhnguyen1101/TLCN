# Additional JARs

The bootstrap image downloads these compatible dependencies at build time:

- `org.apache.iceberg:iceberg-spark-runtime-3.5_2.12:1.7.1` — Iceberg Spark runtime, including the Nessie catalog integration.
- `org.apache.hadoop:hadoop-aws:3.3.4` — Hadoop S3A client matching Spark's Hadoop line.
- `com.amazonaws:aws-java-sdk-bundle:1.12.262` — transitive AWS SDK v1 bundle needed by Hadoop S3A.

The image keeps these JARs in `/opt/spark/custom-jars`; this host directory is
documentation only. Do not bind-mount it over the image directory.
