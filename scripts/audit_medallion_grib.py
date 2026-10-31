"""Verify full archive evidence against current source bytes, rescan on mismatch."""
import hashlib
import json
from pathlib import Path
import sys
import inventory_hourly_grib as audit

ROOT=Path(__file__).resolve().parents[1]
audit.INPUT=ROOT/'data/landing/CAMS/EAC4'
audit.OUTPUT=ROOT/'reports/medallion_migration/grib'
audit.OUTPUT.mkdir(parents=True,exist_ok=True)
for path in sorted(audit.INPUT.glob('*.grib')):
    cached=ROOT/'reports/dashboard/science'/(path.stem+'.json')
    digest=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):digest.update(block)
    prior=json.loads(cached.read_text()) if cached.exists() else {}
    if prior.get('source_sha256')==digest.hexdigest():
        result=prior
        print('Revalidated complete ecCodes evidence by current SHA256: '+path.name,flush=True)
    else:
        result=audit.inspect_file(path)
    (audit.OUTPUT/(path.stem+'.json')).write_text(json.dumps(result,indent=2))
results=[json.loads(p.read_text()) for p in sorted(audit.OUTPUT.glob('*.json')) if p.name!='inventory.json']
assert len(results)==20
assert len({r['timestamp_sha256'] for r in results})==1
assert len({r['coordinate_sha256'] for r in results})==1
assert all(r['duplicate_messages']==r['missing_hourly_slots']==0 for r in results)
(audit.OUTPUT/'inventory.json').write_text(json.dumps(results,indent=2))
print('COMPLETE_GRIB_AUDIT_OK',flush=True)
