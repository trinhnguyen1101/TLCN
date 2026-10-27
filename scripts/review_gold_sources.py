"""Bounded read-only source inventory for the Gold implementation plan."""
import csv
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
report = {'checked_at_utc': datetime.now(timezone.utc).isoformat(), 'scope': 'Local files and bounded Supabase GET requests; no live Iceberg read'}
landing = ROOT / 'data/landing'
report['landing'] = {}
for name in ['CAMS/EAC4', 'waqi/historical', 'climate_trace/climate_trace_vietnam', 'reference/vietnam_administrative_divisions', 'reference/vietnamese-provinces-database', 'ERA5/single_levels']:
    files = sorted(p for p in (landing / name).rglob('*') if p.is_file())
    report['landing'][name] = {'files': len(files), 'bytes': sum(p.stat().st_size for p in files), 'extensions': dict(Counter(p.suffix for p in files))}
    if name.startswith(('waqi/', 'climate_trace/')):
        profiles = []
        for path in files:
            if path.suffix != '.csv':
                continue
            with path.open(encoding='utf-8-sig', newline='') as handle:
                reader = csv.DictReader(handle)
                rows = list(reader)
                keys = reader.fieldnames
            distinct_rows = {tuple(sorted(r.items())) for r in rows}
            profile = {'file': path.relative_to(landing).as_posix(), 'rows': len(rows), 'columns': keys,
                       'exact_duplicate_rows': len(rows) - len(distinct_rows)}
            if rows and 'source_type' in rows[0]:
                profile['source_type_row_counts'] = dict(Counter(r['source_type'] for r in rows))
                profile['source_type_distinct_row_counts'] = dict(Counter(dict(r)['source_type'] for r in distinct_rows))
            for column in ['date', 'year', 'data_month', 'gas', 'aggregation', 'source_type']:
                values = sorted({r.get(column, '').strip() for r in rows} - {''})
                if values:
                    profile[column] = {'distinct': len(values), 'sample': values[:12]}
                    if column == 'date':
                        dates = [datetime.strptime(v, '%Y/%m/%d').date().isoformat() for v in values]
                        profile['date'].update(min=min(dates), max=max(dates))
                    else:
                        profile[column].update(min=values[0], max=values[-1])
            profiles.append(profile)
        report['landing'][name]['csv_profiles'] = profiles
report['admin_json'] = {}
for path in [landing/'reference/vietnam_administrative_divisions/all-province.json', landing/'reference/vietnamese-provinces-database/json/full_json_generated_data_vn_units.json']:
    if path.exists():
        value = json.loads(path.read_text())
        report['admin_json'][path.relative_to(ROOT).as_posix()] = {'type': type(value).__name__, 'count': len(value)}
report['dashboard_samples'] = []
for path in (ROOT/'backend/data/samples').rglob('manifest.json'):
    manifest = json.loads(path.read_text())
    report['dashboard_samples'].append({'file': path.relative_to(ROOT).as_posix(), **{
        k: manifest.get(k) for k in ['generation', 'province_count', 'boundary_policy', 'observation_start', 'observation_end', 'minimum_coverage']}})
report['supabase'] = {'verification_limits': 'REST GET only; Cron schedules, deployed Edge Function code, RLS policies and raw object hashes not audited.'}
target = ROOT / 'docs/gold-source-review.json'
if '--reuse-cloud' in sys.argv:
    previous = json.loads(target.read_text())
    report['supabase'] = previous['supabase']
    report['supabase']['checked_at_utc'] = previous['supabase'].get('checked_at_utc', previous['checked_at_utc'])
    report['supabase']['verification_limits'] = 'REST GET only; Cron schedules, deployed Edge Function code, RLS policies and raw object hashes not audited.'
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    print('Saved local inventory; reused cloud evidence from', report['supabase']['checked_at_utc'])
    raise SystemExit(0)
env = {}
for line in (ROOT/'.env').read_text().splitlines():
    if line.strip() and not line.lstrip().startswith('#') and '=' in line:
        k, v = line.split('=', 1)
        env[k.strip()] = v.strip().strip('\"\'')
uri = urlsplit(env['AWS_CONNECTION_STRING'][5:])
user = parse_qs(uri.query)['user'][0]
base = 'https://' + user.removeprefix('postgres.') + '.supabase.co'
key = env['AWS_SECRET_KEY']

def get(path, params=None, count=False):
    url = base + path + ('?' + urlencode(params) if params else '')
    headers = {'apikey': key, 'Authorization': 'Bearer ' + key}
    if count:
        headers['Prefer'] = 'count=exact'
    try:
        with urlopen(Request(url, headers=headers), timeout=20) as response:
            body = json.load(response)
            return {'status': response.status, 'content_range': response.headers.get('Content-Range'), 'data': body}
    except HTTPError as exc:
        return {'error': 'HTTP ' + str(exc.code)}
    except Exception as exc:
        return {'error_type': type(exc).__name__}

for table, select in [('waqi_stations', 'source_uid,is_active,latitude,longitude'), ('api_ninjas_locations', 'location_key,province_code,province_name,is_active,latitude,longitude')]:
    report['supabase'][table] = get('/rest/v1/' + table, {'select': select, 'limit': '100'}, True)
for source in ['waqi', 'api_ninjas']:
    result = get('/rest/v1/collection_runs', {'select': 'source,scheduled_hour_utc,attempt_number,status,expected_records,successful_records,failed_records,manifest_object_path,manifest_sha256', 'source': 'eq.'+source, 'order': 'scheduled_hour_utc.desc,attempt_number.desc', 'limit': '72'}, True)
    if 'data' in result:
        rows = result.pop('data')
        result['sample_size'] = len(rows)
        result['status_counts_in_sample'] = dict(Counter(r['status'] for r in rows))
        result['min_scheduled_hour_in_sample'] = min((r['scheduled_hour_utc'] for r in rows), default=None)
        result['max_scheduled_hour_in_sample'] = max((r['scheduled_hour_utc'] for r in rows), default=None)
        result['completed_without_manifest_in_sample'] = sum(r['status'] in ['succeeded','partial'] and not (r['manifest_object_path'] and r['manifest_sha256']) for r in rows)
        result['latest_runs'] = [{k:v for k,v in r.items() if k not in ['manifest_object_path','manifest_sha256']} for r in rows[:6]]
    report['supabase']['collection_runs_'+source] = result
for table, cols, order in [('waqi_snapshots','snapshot_hour_utc,waqi_time,collected_at_utc,validation_status','snapshot_hour_utc.desc'), ('api_ninjas_snapshots','snapshot_hour_utc,collected_at_utc,validation_status','snapshot_hour_utc.desc')]:
    report['supabase'][table] = get('/rest/v1/' + table, {'select': cols, 'order': order, 'limit': '3'}, True)
bucket = get('/storage/v1/bucket/raw-api')
if 'data' in bucket:
    bucket['data'] = {k:v for k,v in bucket['data'].items() if k in ['id','name','public','created_at','file_size_limit','allowed_mime_types']}
report['supabase']['raw_bucket'] = bucket
report['supabase']['checked_at_utc'] = report['checked_at_utc']
target.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
print('Saved read-only source inventory:', target)
for name, result in report['supabase'].items():
    if isinstance(result, dict):
        print(name, result.get('content_range'), result.get('status_counts_in_sample', result.get('error', result.get('error_type', result.get('status')))))
