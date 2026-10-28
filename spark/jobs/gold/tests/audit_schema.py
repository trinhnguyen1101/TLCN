"""Compare deployed Spark schemas to executable DDL; optional additive bootstrap only."""
import argparse
import json
import re
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from runtime import spark_session,bootstrap,identifier
from pyspark.sql.types import StructType

p=argparse.ArgumentParser();p.add_argument('--schemas',nargs='+',required=True);p.add_argument('--bootstrap',action='store_true')
a=p.parse_args();spark=spark_session()
try:
    ddl=Path('/opt/spark/work-dir/lakehouse/gold/gold.sql').read_text()
    expected={name:StructType.fromJson(json.loads(spark._jsparkSession.sessionState().sqlParser().parseTableSchema(columns).json()))
              for name,columns in re.findall(r'CREATE TABLE IF NOT EXISTS nessie\.\{\{schema\}\}\.(\w+)\s*\((.*?)\)\s*USING iceberg',ddl,re.S)}
    report={}
    for schema in a.schemas:
        identifier(schema)
        if a.bootstrap:bootstrap(spark,schema,'/opt/spark/work-dir/lakehouse/gold/gold.sql')
        differences={}
        for name,definition in expected.items():
            table='nessie.'+schema+'.'+name
            if not spark.catalog.tableExists(table):differences[name]='missing';continue
            actual=spark.table(table).schema
            # Spark read schemas mark Iceberg fields nullable; compare ordered names/types.
            if [(f.name,f.dataType.simpleString()) for f in actual]!=[(f.name,f.dataType.simpleString()) for f in definition]:
                differences[name]=dict(expected=definition.simpleString(),actual=actual.simpleString())
        report[schema]=dict(table_definitions=len(expected),differences=differences)
    print('GOLD_SCHEMA_AUDIT '+json.dumps(report),flush=True)
    if any(r['differences'] for r in report.values()):raise ValueError('Physical schema drift')
finally:spark.stop()
