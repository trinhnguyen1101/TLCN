"""Read-only, complete ecCodes audit of the standalone hourly GRIB archive."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import eccodes as ec
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / 'data/landing/CAMS/EAC4_hourly'
OUTPUT = ROOT / 'reports/dashboard/science'
KEYS = ('paramId shortName name units typeOfLevel level gridType Ni Nj '
        'latitudeOfFirstGridPointInDegrees latitudeOfLastGridPointInDegrees '
        'longitudeOfFirstGridPointInDegrees longitudeOfLastGridPointInDegrees '
        'iDirectionIncrementInDegrees jDirectionIncrementInDegrees '
        'dataDate dataTime validityDate validityTime stepType dataType edition NV '
        'centre class expver stream generatingProcessIdentifier').split()
IDENTITY = 'paramId typeOfLevel level md5GridSection stepType dataType edition NV'.split()


def get(handle, key):
    try:
        return ec.codes_get(handle, key)
    except ec.CodesInternalError:
        return None


def inspect_file(path):
    path = Path(path)
    first = None
    last = None
    identity = None
    stamps = hashlib.sha256()
    seen = {}
    variants = {}
    allowed = json.loads((ROOT/'backend/app/etl/fixtures/eac4_l60.json').read_text())['pv_variants']
    messages = duplicate = gaps = missing = negative = invalid = 0
    minimum, maximum = float('inf'), float('-inf')
    mismatched_reference_times = 0
    with path.open('rb') as stream:
        while (h := ec.codes_grib_new_from_file(stream)) is not None:
            try:
                signature = [get(h, key) for key in IDENTITY]
                pv = ec.codes_get_array(h, 'pv').tolist() if signature[-1] else None
                if identity is None:
                    identity = signature
                    metadata = {key: get(h, key) for key in KEYS}
                    metadata['pv'] = pv
                    metadata['pv_sha256'] = hashlib.sha256(np.asarray(pv, dtype='<f8').tobytes()).hexdigest() if pv else None
                    metadata['grid_id'] = signature[3]
                    coords = np.column_stack([ec.codes_get_array(h,'latitudes'),ec.codes_get_array(h,'longitudes')])
                    metadata['coordinate_sha256'] = hashlib.sha256(coords.astype('<f8').tobytes()).hexdigest()
                if signature != identity:
                    raise ValueError(f'Changed parameter/grid/vertical coordinate: {path.name}')
                if pv is not None and pv not in allowed:
                    raise ValueError(f'Unknown hybrid coefficients: {path.name}')
                date, time = ec.codes_get(h,'validityDate'), ec.codes_get(h,'validityTime')
                if (date,time) != (ec.codes_get(h,'dataDate'),ec.codes_get(h,'dataTime')):
                    mismatched_reference_times += 1
                instant = datetime.strptime(f'{date:08d}{time:04d}','%Y%m%d%H%M').replace(tzinfo=timezone.utc)
                if instant.minute:
                    raise ValueError('Unaligned timestamp')
                if pv is not None:
                    key=hashlib.sha256(np.asarray(pv,dtype='<f8').tobytes()).hexdigest()
                    variant=variants.setdefault(key,dict(pv=pv,first=instant.isoformat(),last=instant.isoformat(),messages=0))
                    variant['last']=instant.isoformat();variant['messages']+=1
                values = ec.codes_get_values(h)
                if ec.codes_get(h,'bitmapPresent'):
                    values[np.asarray(ec.codes_get_array(h,'bitmap')) == 0] = np.nan
                fingerprint = hashlib.sha256(values.tobytes()).digest()
                messages += 1
                if instant in seen:
                    if seen[instant] != fingerprint:
                        raise ValueError('Conflicting duplicate')
                    duplicate += 1
                    continue
                seen[instant] = fingerprint
                if last is not None:
                    delta = (instant-last).total_seconds()/3600
                    if delta <= 0 or delta != int(delta):
                        raise ValueError('Unordered/non-hourly timestamp')
                    gaps += int(delta)-1
                if first is None:
                    first = instant
                last = instant
                stamps.update(int(instant.timestamp()).to_bytes(8,'little',signed=True))
                finite = np.isfinite(values)
                missing += int((~finite).sum())
                invalid += int(np.isinf(values).sum())
                negative += int((values[finite] < 0).sum())
                if finite.any():
                    minimum = min(minimum,float(values[finite].min()))
                    maximum = max(maximum,float(values[finite].max()))
                if messages % 50000 == 0:
                    print(f'{path.name}: {messages} messages',file=sys.stderr,flush=True)
            finally:
                ec.codes_release(h)
    with path.open('rb') as stream:
        source_hash = hashlib.file_digest(stream,'sha256').hexdigest()
    result = dict(file=path.name, **metadata, source_sha256=source_hash,
        messages=messages, unique_timestamps=len(seen), duplicate_messages=duplicate,
        start=first.isoformat(),end=last.isoformat(),timestamp_sha256=stamps.hexdigest(),
        missing_hourly_slots=gaps,missing_cell_values=missing,infinite_cell_values=invalid,
        negative_cell_values=negative,minimum=minimum,maximum=maximum,
        reference_time_differs_from_validity=mismatched_reference_times, pv_variants=variants)
    return result


def run_file(path):
    cached=OUTPUT/(path.stem+'.json')
    if cached.exists():
        result=json.loads(cached.read_text())
        with path.open('rb') as stream:
            digest=hashlib.file_digest(stream,'sha256').hexdigest()
        if result['source_sha256']==digest:
            print('Reusing complete audit: '+path.name,flush=True)
            return result
    subprocess.run([sys.executable,__file__,'--file',str(path)],check=True)
    return json.loads((OUTPUT/(path.stem+'.json')).read_text())


if __name__ == '__main__':
    OUTPUT.mkdir(parents=True,exist_ok=True)
    if len(sys.argv)>1 and sys.argv[1]=='--file':
        p=Path(sys.argv[2]); result=inspect_file(p)
        (OUTPUT/(p.stem+'.json')).write_text(json.dumps(result,indent=2))
        print('Completed '+p.name,flush=True)
    else:
        files=sorted(INPUT.glob('*.grib'))
        if len(files)!=20:
            raise ValueError(f'Expected 20 verified source files, found {len(files)}')
        with ThreadPoolExecutor(max_workers=4) as pool:
            results=list(pool.map(run_file,files))
        for field in ['timestamp_sha256','coordinate_sha256']:
            if len({r[field] for r in results})!=1:
                raise ValueError('Incompatible source '+field)
        models=[r for r in results if r['typeOfLevel']=='hybrid']
        if len({(r['level'],json.dumps(r.get('pv_variants'),sort_keys=True)) for r in models})!=1:
            raise ValueError('Incompatible vertical coordinates')
        (OUTPUT/'grib-inventory.json').write_text(json.dumps(results,indent=2))
        print('All 20 sources aligned; complete inventory published.',flush=True)
