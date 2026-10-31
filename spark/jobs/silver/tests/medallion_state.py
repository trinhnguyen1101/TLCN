"""Read-only runtime evidence, including independently selected completed batches."""
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from common import create_spark
s=create_spark('medallion-runtime-state')
try:
    for name in ['dataset','ingestion_run']:
        rows=s.table('nessie.silver.'+name).collect()
        print('MEDALLION_'+name.upper()+'='+json.dumps([r.asDict() for r in rows],default=str),flush=True)
    paths=s.sql("""SELECT bronze_path FROM (
        SELECT bronze_path,row_number() OVER (PARTITION BY dataset_id ORDER BY started_at DESC) n
        FROM nessie.silver.ingestion_run WHERE status='succeeded' AND pipeline_name NOT LIKE 'cams%'
    ) WHERE n=1""").collect()
    print('MEDALLION_PATHS='+json.dumps(sorted({r.bronze_path for r in paths})),flush=True)
finally:s.stop()
