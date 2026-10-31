"""Dataset-aware, resumable Landing -> Bronze -> Silver orchestration.

Inventory is always regenerated. Content-keyed per-dataset checkpoints retain
original Bronze date/batch on replay. Optional Gold execution uses the existing validated release workflow.
CAMS pilot extracts exact GRIB message bytes and publishes only to gold_test*. Unknown sources retain raw bytes but
block a claim of complete normalization. Single host writer; no shell eval.
"""
import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import json
from pathlib import Path
import subprocess
import time
from inventory_landing import run, ROOT

CONTAINER='/opt/spark/work-dir/'

def execute(inventory, state_path, selected=None, include_cams=False, gold=None, cams_pilot=False):
    state=json.loads(state_path.read_text()) if state_path.exists() else {}
    results=[]
    if selected and set(selected)-{d['dataset_id'] for d in inventory['datasets']}:
        raise ValueError('Requested dataset absent from discovered Landing inventory')
    base=['docker','compose','exec','-T','spark-master','/opt/spark/bin/spark-submit','--master','local[1]', '--driver-memory','1g','--conf','spark.sql.shuffle.partitions=4']
    native_result=None
    def submit(label, job, arguments, memory='1g'):
        stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')
        log=state_path.parent/(label.replace('/','_')+'-'+stamp+'.log')
        begin=time.monotonic()
        command=list(base)
        command[command.index('--driver-memory')+1]=memory
        command+=['--py-files',CONTAINER+'jobs/silver/common.py,'+CONTAINER+'jobs/silver/cams_physics.py',CONTAINER+'jobs/'+job]+arguments
        try:
            with log.open('w') as output:
                process=subprocess.run(command,stdout=output,stderr=subprocess.STDOUT)
            code=process.returncode
        except OSError as exc:
            log.write_text(str(exc));code=127
        return dict(exit_code=code,status='passed' if code==0 else 'failed',seconds=round(time.monotonic()-begin,3),log=str(log))
    for dataset in inventory['datasets']:
        name=dataset['dataset_id']
        if selected and name not in selected:continue
        if not dataset['file_count']:
            results.append(dict(dataset=name,status='blocked_missing_source'));continue
        if any(f['validation']['status']=='failed' for f in dataset['files']):
            results.append(dict(dataset=name,status='failed',phase='landing_validation'));continue
        if name.startswith('.'):
            results.append(dict(dataset=name,status='ancillary_not_dataset'));continue
        if name=='CAMS/EAC4' and cams_pilot:
            record=dict(dataset=name,pilot=submit(name+'-pilot','silver/tests/integration_cams.py',[]))
            record['status']=record['pilot']['status']
            if record['pilot']['exit_code']==0 and gold:
                markers=[line for line in Path(record['pilot']['log']).read_text().splitlines() if line.startswith('CAMS_INTEGRATION_RESULT=')]
                if not markers:raise ValueError('Pilot succeeded without validated dataset identity')
                pilot=json.loads(markers[-1].split('=',1)[1])
                record['pilot_evidence']=pilot
                record['gold']=submit(name+'-gold','gold/run.py',['--schema',gold['schema'],'--dataset-id',pilot['dataset_id'],'--allow-validation','--start-date',gold['start_date'],'--end-date',gold['end_date']], '2g')
                record['status']=record['gold']['status']
            elif not gold:record['gold']=dict(status='skipped',reason='Gold execution not selected')
            results.append(record);continue
        if name=='CAMS/EAC4' and not include_cams:
            results.append(dict(dataset=name,status='requires_measured_backfill_scope',reason='Use bounded integration before full-archive processing'));continue
        fingerprint=hashlib.sha256(json.dumps([(f['path'],f['sha256']) for f in dataset['files']],sort_keys=True).encode()).hexdigest()
        key=name+':'+fingerprint
        checkpoint=state.setdefault(key,dict(batch_id='content-'+fingerprint[:32],ingestion_date=datetime.now(timezone.utc).date().isoformat(),dataset=name,source_version=dataset['source_version']))
        record=dict(dataset=name,**{k:v for k,v in checkpoint.items() if k!='dataset'})
        args=['--dataset',name,'--batch-id',checkpoint['batch_id'],'--ingestion-date',checkpoint['ingestion_date']]
        phases=[('bronze','bronze/landing_to_bronze.py',args)]
        if dataset['silver_adapter']:
            bronze='s3a://lakehouse/bronze/'+name.lower()+'/ingestion_date='+checkpoint['ingestion_date']+'/batch_id='+checkpoint['batch_id']
            silver_args=['--bronze-path',bronze]
            if name=='CAMS/EAC4':silver_args+=['--source-version',dataset['source_version']]
            phases.append(('silver','silver/'+dataset['silver_adapter'],silver_args))
        for phase,job,args in phases:
            record[phase]=submit(name+'-'+phase,job,args)
            checkpoint[phase]=record[phase]
            # Record partial/failed state without advancing any Gold pointer.
            state_path.write_text(json.dumps(state,indent=2)+'\n')
            if record[phase]["exit_code"]:break
        record['status']='failed' if any(record.get(p,{}).get('exit_code',0) for p in ('bronze','silver')) else 'normalized' if dataset['silver_adapter'] else 'raw_only_adapter_missing'
        if record['status']=='normalized' and gold:
            if dataset['gold_adapter']=='native_sources':
                record['gold']=dict(status='pending_native_dependencies')
            elif dataset['gold_adapter']=='dimensions':
                record['gold']=dict(status='not_applicable',reason='Consumed by bounded CAMS Gold geography dimensions')
            else:
                identity=['silver-dataset-v1','cams','eac4',dataset['source_version']]
                dataset_id=hashlib.sha256(json.dumps(identity,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
                record['gold']=submit(name+'-gold','gold/run.py',['--schema',gold['schema'],'--dataset-id',dataset_id,'--start-date',gold['start_date'],'--end-date',gold['end_date']], '2g')
            if record['gold']['status']=='failed':record['status']='failed'
        elif 'gold' not in record:
            record['gold']=dict(status='skipped',reason='Gold execution not selected or upstream failed')
        results.append(record)
    pending=[r for r in results if r.get('gold',{}).get('status')=='pending_native_dependencies']
    if pending:
        native_names={d['dataset_id'] for d in inventory['datasets'] if d.get('gold_adapter')=='native_sources'}
        failed_native=[r for r in results if r['dataset'] in native_names and r['status']!='normalized']
        native_result=(dict(status='blocked',reason='Selected native Silver dependency unavailable or failed') if failed_native else submit('native-gold','gold/native_sources.py',['--schema',gold['schema']]))
        for record in pending:
            record['gold']=native_result
            if native_result['status']=='failed':record['status']='failed'
    (state_path.parent/'orchestration-results.json').write_text(json.dumps(results,indent=2)+'\n')
    return results

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--execute',action='store_true')
    p.add_argument('--dataset',action='append')
    p.add_argument('--include-full-cams',action='store_true',help='Only after bounded pilot/resource review; expensive complete archive')
    p.add_argument('--cams-pilot',action='store_true',help='Three exact real GRIB messages per variable, isolated validation identity')
    p.add_argument('--gold',action='store_true',help='Run compatible Gold branches after successful Silver')
    p.add_argument('--gold-schema',default='gold_test_medallion_runner')
    p.add_argument('--start-date',default='2003-01-01')
    p.add_argument('--end-date',default='2003-01-02')
    p.add_argument('--output' ,type=Path,default=ROOT/'reports/medallion_migration')
    args=p.parse_args()
    if args.cams_pilot and not args.gold_schema.startswith('gold_test'):
        p.error('CAMS pilot requires an isolated gold_test* namespace')
    from datetime import date
    if args.gold and not 0<(date.fromisoformat(args.end_date)-date.fromisoformat(args.start_date)).days<=31:
        p.error('Gold requires a bounded 1..31 day scope')
    with open('/tmp/tlcn-medallion-writer.lock','w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        inventory=run(ROOT/'data/landing',args.output)
        if args.execute:
            results=execute(inventory,args.output/'dataset-checkpoints.json',args.dataset,args.include_full_cams,dict(schema=args.gold_schema,start_date=args.start_date,end_date=args.end_date) if args.gold else None,args.cams_pilot)
            print(json.dumps(results,indent=2))
            if any(r['status'] in ('failed','raw_only_adapter_missing') for r in results):raise SystemExit(1)
