"""Additive legacy migration, explicit withdrawals and retention report. No snapshot deletion."""
import argparse
import fcntl
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from runtime import spark_session,bootstrap,identifier
from publication import current,publish,commit
from timeline import overlay,unpack_manifest


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--schema',required=True,type=identifier)
    p.add_argument('--action',choices=['migrate','withdraw','retention'],default='migrate')
    p.add_argument('--compatibility-id')
    p.add_argument('--start');p.add_argument('--end')
    args=p.parse_args()
    with open('/tmp/tlcn-gold-writer.lock','w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        spark=spark_session()
        try:
            bootstrap(spark,args.schema,'/opt/spark/work-dir/lakehouse/gold/gold.sql')
            prefix='nessie.'+args.schema+'.'
            if args.action=='migrate':
                # Only a visible legacy release is trusted, never every registered stage.
                pointer=spark.table(prefix+'gold_current_release').where("channel='air_quality'").collect()
                if current(spark,prefix,'air_quality') is None and pointer:
                    release=spark.table(prefix+'gold_release').where("release_id='"+pointer[0].release_id+"'").collect()[0].asDict()
                    publish(spark,prefix,release)
            old=current(spark,prefix,'air_quality')
            if args.action=='withdraw':
                if not old or not all([args.start,args.end,args.compatibility_id]):raise ValueError('Withdrawal requires scope and lane')
                from datetime import datetime,time,timedelta,timezone
                for bound in (args.start,args.end):
                    value=datetime.fromisoformat(bound.replace('Z','+00:00'))
                    if value.tzinfo is None or value.astimezone(timezone(timedelta(hours=7))).time()!=time():
                        raise ValueError('Withdrawal bounds require offset and VN midnight alignment')
                manifest=unpack_manifest(json.loads(old['manifest_json']))
                if args.compatibility_id not in {s['compatibility_id'] for s in manifest['segments']}:raise ValueError('Unknown lane')
                previous=next(s for s in manifest['segments'] if s['compatibility_id']==args.compatibility_id)
                tombstone={k:previous[k] for k in ('compatibility_id','series','method_version','contract_sha256') if k in previous}
                tombstone.update(start=args.start,end=args.end,withdrawn=True)
                manifest=overlay(manifest,tombstone)
                old=commit(spark,prefix,'air_quality',manifest,old,'withdraw')
            if args.action=='retention':
                # Conservative protection of ALL immutable rollback views. Never expire.
                keep={}
                for row in spark.table(prefix+'gold_timeline').collect():
                    for segment in json.loads(row.manifest_json)['segments']:
                        for table,snapshot in segment.get('snapshots',{}).items():
                            keep.setdefault(table,set()).add(snapshot)
                # Legacy/native pointers and all registered releases also remain protected.
                for row in spark.table(prefix+'gold_release').collect():
                    for table,snapshot in json.loads(row.output_snapshots_json).items():keep.setdefault(table,set()).add(snapshot)
                print('GOLD_RETENTION '+json.dumps(dict(dry_run=True,cleanup_enabled=False,
                    protected_snapshots={k:sorted(v) for k,v in keep.items()},
                    policy='Keep all registry/rollback references; bound storage only after explicit archive policy approval')),flush=True)
            print('GOLD_TIMELINE '+json.dumps(old,default=str),flush=True)
        finally:spark.stop()
if __name__=='__main__':main()
