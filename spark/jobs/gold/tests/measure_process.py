"""Bounded real build: Linux child RSS plus Spark event/task metrics. No archive benchmark."""
import json
from pathlib import Path
import resource
import os
import threading
import subprocess
import sys
import tempfile
import time

if __name__=='__main__':
    begin=time.monotonic()
    peaks={'driver_jvm_rss_kib':0,'driver_python_rss_kib':0,'python_workers_rss_kib':0,'process_tree_rss_kib':0}
    def sample_tree(pid,stop):
        while not stop.wait(0.2):
            processes={}
            for path in Path('/proc').iterdir():
                if not path.name.isdigit():continue
                try:
                    status=dict(line.split(':',1) for line in (path/'status').read_text().splitlines() if ':' in line)
                    command=(path/'cmdline').read_bytes().replace(b'\0',b' ').decode(errors='replace')
                    processes[int(path.name)]=(int(status['PPid']),int(status.get('VmRSS','0 kB').split()[0]),status['Name'].strip(),command)
                except (OSError,KeyError,ValueError):continue
            descendants={pid}
            for _ in range(6):
                descendants.update(p for p,v in processes.items() if v[0] in descendants)
            values={k:0 for k in peaks}
            for child in descendants:
                if child not in processes:continue
                _,rss,name,command=processes[child];values['process_tree_rss_kib']+=rss
                if name=='java':values['driver_jvm_rss_kib']+=rss
                elif 'python' in name and 'run.py' in command:values['driver_python_rss_kib']+=rss
                elif 'python' in name:values['python_workers_rss_kib']+=rss
            for key,value in values.items():peaks[key]=max(peaks[key],value)
    args=sys.argv[1:] or ['--schema','gold_pilot','--dataset-id','cbb7d021543ec806863f7da49793290e7ea2b1c71c169a717f6a01d64418ed61',
                         '--allow-validation','--start-date','2003-01-01','--end-date','2003-01-02']
    with tempfile.TemporaryDirectory(prefix='gold-events-') as eventdir:
        cmd=['/opt/spark/bin/spark-submit','--master','local[1]','--driver-memory','2g',
             '--conf','spark.eventLog.enabled=true','--conf','spark.eventLog.dir=file://'+eventdir,
             '/opt/spark/work-dir/jobs/gold/run.py']+args
        process=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,universal_newlines=True)
        stop=threading.Event();sampler=threading.Thread(target=sample_tree,args=(process.pid,stop),daemon=True);sampler.start()
        output,_=process.communicate();stop.set();sampler.join(timeout=1)
        from types import SimpleNamespace
        result=SimpleNamespace(stdout=output,returncode=process.returncode)
        logdir=Path(os.environ.get('GOLD_BENCH_OUTPUT','/tmp/gold-last-benchmark'));logdir.mkdir(parents=True,exist_ok=True)
        (logdir/'spark.log').write_text(output)
        for line in result.stdout.splitlines():
            if line.startswith('GOLD_'):print(line,flush=True)
        tasks=[];stages=set();jobs=0;per_stage={};shuffle_read=shuffle_write=peak_execution=0
        for path in Path(eventdir).rglob('*'):
            if not path.is_file() or path.name.startswith('.'):continue
            for line in path.read_text().splitlines():
                event=json.loads(line)
                if event.get('Event')=='SparkListenerJobStart':jobs+=1
                if event.get('Event')!='SparkListenerTaskEnd':continue
                stage=event['Stage ID'];stages.add(stage)
                per_stage.setdefault(stage,[]).append(event.get('Task Metrics',{}).get('Executor Run Time',0))
                metric=event.get('Task Metrics',{})
                tasks.append(metric.get('Executor Run Time',0))
                reads=metric.get('Shuffle Read Metrics',{})
                shuffle_read+=reads.get('Remote Bytes Read',0)+reads.get('Local Bytes Read',0)
                shuffle_write+=metric.get('Shuffle Write Metrics',{}).get('Shuffle Bytes Written',0)
                peak_execution=max(peak_execution,metric.get('Peak Execution Memory',0))
        usage=resource.getrusage(resource.RUSAGE_CHILDREN)
        measured=dict(seconds=round(time.monotonic()-begin,3),
            maximum_child_rss_kib=usage.ru_maxrss,child_user_cpu_seconds=usage.ru_utime,
            child_system_cpu_seconds=usage.ru_stime,exit_code=result.returncode,task_count=len(tasks),
            maximum_task_runtime_ms=max(tasks) if tasks else None,median_task_runtime_ms=sorted(tasks)[len(tasks)//2] if tasks else None,
            shuffle_read_bytes=shuffle_read,shuffle_write_bytes=shuffle_write,
            maximum_task_execution_memory_bytes=peak_execution,job_count=jobs,stage_count=len(stages),sampled_rss=peaks,
            memory_scope='local[1]: driver/executor share JVM; sampled RSS sums may double-count shared pages; not Docker peak',
            per_stage_runtime_ms={str(k):dict(tasks=len(v),maximum=max(v),median=sorted(v)[len(v)//2]) for k,v in per_stage.items()})
        (logdir/'metrics.json').write_text(json.dumps(measured,indent=2))
        print('GOLD_PROCESS_METRICS '+json.dumps(measured),flush=True)
        if result.returncode:print(result.stdout[-6000:],flush=True)
    raise SystemExit(result.returncode)
