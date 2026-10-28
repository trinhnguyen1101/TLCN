"""Isolated history test corrections/deletions; production namespaces are hard rejected."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from runtime import spark_session
spark=spark_session()
try:
    from runtime import identifier
    schema=identifier(sys.argv[2]) if len(sys.argv)>2 else 'gold_test_history_silver'
    if not schema.startswith('gold_test'):raise ValueError('Fixtures only')
    table='nessie.'+schema+'.hourly_concentration'
    if sys.argv[1]=='correct':
        spark.sql("UPDATE "+table+" SET value=75.0 WHERE pollutant='pm25' AND hour_start_utc=TIMESTAMP '2025-12-30 16:00:00'")
    elif sys.argv[1]=='delete':
        spark.sql("DELETE FROM "+table+" WHERE (pollutant='pm25' AND hour_start_utc=TIMESTAMP '2025-12-31 05:00:00') OR (pollutant='o3' AND hour_start_utc=TIMESTAMP '2025-12-31 16:00:00')")
    else:raise ValueError('Unknown action')
finally:spark.stop()
