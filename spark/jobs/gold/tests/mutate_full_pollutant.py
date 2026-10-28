"""Isolated complete-variable withdrawal and incompatible metadata test."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from runtime import spark_session
spark=spark_session()
try:
    table='nessie.gold_test_deletion_silver.hourly_concentration'
    if sys.argv[1]=='restore':
        spark.sql("DELETE FROM "+table+" WHERE pollutant='so2'")
        spark.sql("UPDATE "+table+" SET vertical_support='model_surface' WHERE pollutant='co'")
        rows=[r.asDict() for r in spark.table(table).filter("pollutant='co'").collect()]
        for row in rows:row.update(pollutant='so2',value=10.0)
        spark.createDataFrame(rows,spark.table(table).schema).writeTo(table).append()
    elif sys.argv[1]=='withdraw':spark.sql("DELETE FROM "+table+" WHERE pollutant='so2'")
    elif sys.argv[1]=='incompatible':spark.sql("UPDATE "+table+" SET vertical_support='surface' WHERE pollutant='co'")
    else:raise ValueError('Unknown fixture action')
finally:spark.stop()
