"""Small in-memory Spark check for Supabase Silver duplicate and retry logic."""

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from pyspark.sql import SparkSession, types as T

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import supabase_bronze_to_silver as job


def main():
    spark = SparkSession.builder.master("local[1]").appName("supabase-silver-join-check").getOrCreate()
    try:
        schema = T.StructType([
            T.StructField("dataset_id", T.StringType(), False),
            T.StructField("source_system", T.StringType(), False),
            T.StructField("source_variable", T.StringType(), False),
            T.StructField("measurement_kind", T.StringType(), False),
            T.StructField("native_unit", T.StringType(), True),
            T.StructField("standard_unit", T.StringType(), True),
        ])
        existing = spark.createDataFrame([("dataset", "api_ninjas", "pm25_aqi", "pollutant_aqi", "AQI", "AQI")], schema)

        class Session:
            def table(self, _):
                return existing

            def createDataFrame(self, rows, target_schema):
                return spark.createDataFrame(rows, target_schema)

        session = Session()
        keys = ["source_system", "source_variable", "measurement_kind"]
        compare = ["native_unit", "standard_unit"]
        same = [dict(zip(schema.fieldNames(), ("dataset", "api_ninjas", "pm25_aqi", "pollutant_aqi", "AQI", "AQI")))]
        run = SimpleNamespace(dataset_id="dataset")
        with patch.object(job, "merge_dataframe") as merged:
            job.merge_checked(session, "variable", same, keys, compare, run)
            assert merged.call_count == 1
        changed = [dict(same[0], native_unit="ug/m3")]
        with patch.object(job, "write_quality_issues"):
            try:
                job.merge_checked(session, "variable", changed, keys, compare, run)
            except job.DataQualityError:
                pass
            else:
                raise AssertionError("Conflicting existing variable was not rejected")
        print("supabase_silver_spark_join=ok")
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
