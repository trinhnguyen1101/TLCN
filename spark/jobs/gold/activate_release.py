"""Explicit rollback/activation of a validated registry release; never rewrite data."""
import argparse
import fcntl
import json
from pathlib import Path
import re
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from runtime import spark_session,identifier,Build


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--schema',required=True,type=identifier)
    p.add_argument('--release-id')
    p.add_argument('--timeline-id')
    args=p.parse_args()
    if bool(args.release_id)==bool(args.timeline_id):raise ValueError('Choose release-id or timeline-id')
    if not re.fullmatch('[0-9a-f]{64}',args.release_id or args.timeline_id):raise ValueError('Invalid identity')
    with open('/tmp/tlcn-gold-writer.lock','w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        spark=spark_session()
        try:
            prefix='nessie.'+args.schema+'.'
            from publication import restore
            if args.timeline_id:
                restore(spark,prefix,args.timeline_id)
                print('GOLD_TIMELINE_ROLLBACK '+args.timeline_id,flush=True)
                return
            if spark.catalog.tableExists(prefix+'gold_timeline'):
                views=spark.table(prefix+'gold_timeline').where("trigger_release_id='"+args.release_id+"'").collect()
                if views:restore(spark,prefix,views[0].timeline_id)
            rows=spark.table(prefix+'gold_release').filter("release_id='"+args.release_id+"'").collect()
            if len(rows)!=1:raise ValueError('Unknown validated release')
            row=rows[0].asDict()
            for name,snapshot_id in json.loads(row['output_snapshots_json']).items():
                identifier(name)
                spark.read.option('snapshot-id',str(int(snapshot_id))).table(prefix+name).limit(1).collect()
            build=Build(spark,args.schema,'silver',{},row['scope_start_utc'],row['scope_end_utc'],row['channel'],'')
            build.activate(row)
            print('GOLD_ACTIVATED '+args.release_id,flush=True)
        finally:spark.stop()

if __name__=='__main__':main()
