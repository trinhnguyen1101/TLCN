"""Isolated metadata-head correctness probe; no published/source tables touched."""
from pathlib import Path
import json
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from runtime import spark_session,snapshot
spark=spark_session(master='local[1]')
try:
    spark.sql('CREATE NAMESPACE IF NOT EXISTS nessie.gold_test_perf_probe')
    table='nessie.gold_test_perf_probe.snapshot_head'
    spark.sql('CREATE TABLE IF NOT EXISTS '+table+" (id INT) USING iceberg LOCATION 's3a://lakehouse/gold_test_perf_probe/snapshot_head'")
    spark.sql('INSERT INTO '+table+' VALUES (1)')
    iceberg=spark._jvm.org.apache.iceberg.spark.Spark3Util.loadIcebergTable(spark._jsparkSession,table)
    iceberg.refresh();old=int(iceberg.currentSnapshot().snapshotId())
    spark.sql('INSERT INTO '+table+' VALUES (2)');iceberg.refresh();new=int(iceberg.currentSnapshot().snapshotId())
    spark.sql("CALL nessie.system.rollback_to_snapshot(table => 'gold_test_perf_probe.snapshot_head', snapshot_id => "+str(old)+')')
    iceberg.refresh();actual=int(iceberg.currentSnapshot().snapshotId());helper=snapshot(spark,table)
    assert actual==old and old!=new
    result=dict(current_snapshot=actual,latest_created_snapshot=new,helper_snapshot=helper,helper_matches_head=helper==actual,
                scope='isolated unregistered test table; all snapshots retained')
    print('SNAPSHOT_HEAD_PROBE '+json.dumps(result),flush=True)
    assert helper==actual, result
finally:spark.stop()
