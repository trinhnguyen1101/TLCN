"""Minimal Spark smoke test; does not create an Iceberg table or ingest data."""
from pyspark.sql import SparkSession

spark = SparkSession.builder.appName("lakehouse-smoke-test").getOrCreate()
print("Spark version:", spark.version)
print("Nessie catalog configured:", spark.conf.get("spark.sql.catalog.nessie"))
spark.range(1).show()
spark.stop()
