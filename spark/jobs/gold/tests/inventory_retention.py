"""Read-only, streaming registry inventory; no destructive maintenance commands."""
import argparse
import fcntl
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from runtime import spark_session,identifier,snapshot
from retention import references,dry_run
from pyspark.sql import functions as F
p=argparse.ArgumentParser();p.add_argument('--schema',required=True,type=identifier);p.add_argument('--output',required=True);a=p.parse_args()
with open('/tmp/tlcn-gold-writer.lock','w') as lock:
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    # Metadata inspection runs on the configured development driver. Submitting
    # it to standalone executors requires a separate executor S3 credential and
    # region transport, which this host-runner deployment does not configure.
    spark=spark_session(master='local[1]')
    try:
        prefix='nessie.'+a.schema+'.'
        def stream(name):
            # One immutable manifest at a time, not all historical JSON in a list.
            for i,row in enumerate(spark.table(prefix+name).toLocalIterator()):
                if i>=10000:raise ValueError('Metadata inventory budget exceeded')
                yield row.asDict(recursive=True)
        refs=references(prefix,stream('gold_release'),stream('gold_timeline'),stream('gold_current_release'))
        tables=set(refs['kept']);tables.update(prefix+n for n in ['gold_release','gold_timeline','gold_timeline_current','gold_current_release'])
        inventory=[];files={};complete=True
        for table in sorted(tables):
            current=snapshot(spark,table)
            named={}
            for row in spark.table(table+'.refs').select('name','snapshot_id').collect():named.setdefault(row.snapshot_id,[]).append(row.name)
            rows=spark.table(table+'.snapshots').select('snapshot_id','committed_at').limit(100001).collect()
            if len(rows)>100000:complete=False;rows=rows[:100000]
            inventory.extend(dict(table=table,snapshot_id=int(r.snapshot_id),committed_at=r.committed_at.isoformat(),is_head=r.snapshot_id==current,named_refs=named.get(r.snapshot_id,[])) for r in rows)
            frame=spark.table(table+'.files')
            size=frame.agg(F.count('*').alias('files'),F.sum('file_size_in_bytes').alias('head_bytes'),F.sum('record_count').alias('head_records')).first().asDict()
            size['scope']='head files only; not retained-snapshot union or object-store usage'
            if table.startswith(prefix) and 'partition' in frame.columns and 'release_id' in frame.schema['partition'].dataType.names:
                published=spark.createDataFrame([(v,) for v in refs['registered']],'release_id string')
                stages=frame.select(F.col('partition.release_id').alias('release_id'),'file_size_in_bytes').join(F.broadcast(published),'release_id','left_anti')
                size['unregistered_head_files']=stages.count()
                size['unregistered_note']='Possible stages only; never label these orphan files or delete them automatically'
            files[table]=size
        report=dry_run(refs,inventory,inventory_complete=complete);report['files']=files
        Path(a.output).parent.mkdir(parents=True,exist_ok=True);Path(a.output).write_text(json.dumps(report,indent=2))
        print('RETENTION_INVENTORY '+json.dumps(dict(inventory_complete=report['inventory_complete'],protected=len(report['protected_snapshots']),missing=len(report['missing_references']),review=len(report['unreferenced_snapshot_review_candidates']),cleanup_enabled=False)),flush=True)
    finally:spark.stop()
