"""Single-writer local orchestration/backfill for bounded Gold releases.

No Docker socket is mounted into Airflow. Run on the Compose host. Each
backfill chunk is a separate inspectable release; current pointer is the last
published chunk for legacy diagnostics. Historical serving resolves the atomic timeline.
"""
import argparse
from datetime import date,timedelta
import fcntl
import json
from pathlib import Path
import subprocess
import time


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--schema',default='gold')
    p.add_argument('--dataset-id',required=True)
    p.add_argument('--start-date',required=True)
    p.add_argument('--end-date',required=True)
    p.add_argument('--chunk-days',type=int,default=7)
    p.add_argument('--allow-validation',action='store_true')
    p.add_argument('--adapter',choices=['cams','normalized_hourly'],default='cams')
    p.add_argument('--silver-schema',default='silver')
    p.add_argument('--contract')
    p.add_argument('--fixture',action='store_true')
    args=p.parse_args()
    if args.adapter=='normalized_hourly' and not args.contract:
        raise ValueError('Normalized backfill requires an explicit source contract')
    if args.fixture and not (args.schema.startswith('gold_test') and args.silver_schema.startswith('gold_test')):
        raise ValueError('Fixtures require isolated input/output namespaces')
    if not 1<=args.chunk_days<=31:
        raise ValueError('chunk-days must be 1..31')
    directory=Path('reports/gold')
    directory.mkdir(parents=True,exist_ok=True)
    # Advisory lock shared by all invocations of this host runner.
    with open('/tmp/tlcn-gold-orchestration.lock','w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        start,end=date.fromisoformat(args.start_date),date.fromisoformat(args.end_date)
        if start>=end:
            raise ValueError('Nonempty scope required')
        while start<end:
            stop=min(start+timedelta(days=args.chunk_days),end)
            cmd=['docker','compose','exec','-T','spark-master','/opt/spark/bin/spark-submit',
                 '--master','local[1]','--driver-memory','2g','/opt/spark/work-dir/jobs/gold/run.py',
                 '--schema',args.schema,'--dataset-id',args.dataset_id,'--start-date',str(start),'--end-date',str(stop)]
            cmd+=['--adapter',args.adapter,'--silver-schema',args.silver_schema]
            if args.contract:cmd+=['--contract',args.contract]
            if args.fixture:cmd.append('--fixture')
            if args.allow_validation:cmd.append('--allow-validation')
            log=directory/(str(start)+'-'+args.schema+'.log')
            begin=time.monotonic()
            with log.open('w') as handle:
                result=subprocess.run(cmd,stdout=handle,stderr=subprocess.STDOUT)
            elapsed=time.monotonic()-begin
            summary=dict(start_date=str(start),end_date=str(stop),seconds=round(elapsed,3),exit_code=result.returncode,log=str(log))
            print(json.dumps(summary),flush=True)
            if result.returncode:
                raise SystemExit(result.returncode)
            start=stop


if __name__=='__main__':main()
