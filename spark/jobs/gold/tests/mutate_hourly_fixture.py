"""Destructive mutations confined to the explicitly isolated test Silver table."""
import argparse
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from runtime import spark_session
from pyspark.sql import functions as F


def main():
    p=argparse.ArgumentParser()
    p.add_argument('mode',choices=['change','restore'])
    args=p.parse_args()
    spark=spark_session()
    table='nessie.gold_test_silver.hourly_concentration'
    try:
        if args.mode=='change':
            spark.sql("UPDATE "+table+" SET value=100.0 WHERE pollutant='pm25' AND hour_start_utc=TIMESTAMP '2026-01-02 16:00:00'")
            spark.sql("UPDATE "+table+" SET quality_status='invalid',missing_reason='fixture_qc_rejected' WHERE pollutant='so2' AND hour_start_utc=TIMESTAMP '2026-01-02 10:00:00'")
            spark.sql("DELETE FROM "+table+" WHERE pollutant='pm25' AND hour_start_utc=TIMESTAMP '2026-01-03 05:00:00'")
        else:
            spark.sql("UPDATE "+table+" SET quality_status='ok',missing_reason=NULL WHERE pollutant='so2'")
            spark.sql("UPDATE "+table+" SET value=25.0 WHERE pollutant='pm25'")
            if not spark.table(table).filter("pollutant='pm25' AND hour_start_utc=TIMESTAMP '2026-01-03 05:00:00'").count():
                base=spark.table(table).filter("pollutant='pm25'").limit(1).localCheckpoint(eager=True)
                row=base.withColumn('hour_start_utc',F.lit('2026-01-03 05:00:00').cast('timestamp')).withColumn('observed_at_utc',F.lit('2026-01-03 05:00:00').cast('timestamp'))
                row.writeTo(table).append()
        print('FIXTURE_MUTATED '+args.mode,flush=True)
    finally:spark.stop()

if __name__=='__main__':main()
