"""Immutable, disjoint published intervals. No database or Spark dependencies."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json


def utc(value):
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)  # Spark session timestamps are UTC
    return value.astimezone(timezone.utc).isoformat()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def overlay(manifest, entry):
    """Replace the entire scope, including absent/deleted keys, in one compatible lane."""
    result = deepcopy(unpack_manifest(manifest))
    entry = deepcopy(entry)
    entry['start'], entry['end'] = utc(entry['start']), utc(entry['end'])
    if entry['start'] >= entry['end']:
        raise ValueError('Empty publication scope')
    segments = []
    for old in result.get('segments', []):
        if old['compatibility_id'] != entry['compatibility_id'] or old['end'] <= entry['start'] or old['start'] >= entry['end']:
            segments.append(old)
            continue
        if old['start'] < entry['start']:
            left = deepcopy(old)
            left['end'] = entry['start']
            segments.append(left)
        if old['end'] > entry['end']:
            right = deepcopy(old)
            right['start'] = entry['end']
            segments.append(right)
    segments.append(entry)
    result['segments'] = sorted(segments, key=lambda r: (r['compatibility_id'], r['start']))
    result['version'] = 1
    return result


def gaps(segments, start, end):
    start, end = utc(start), utc(end)
    cursor, missing = start, []
    for segment in sorted(segments, key=lambda r: r['start']):
        lo, hi = max(start, segment['start']), min(end, segment['end'])
        if lo >= hi:
            continue
        if lo > cursor:
            missing.append({'start': cursor, 'end': lo, 'reason': 'unpublished_scope'})
        if segment.get('withdrawn'):
            missing.append({'start': lo, 'end': hi, 'reason': 'withdrawn_scope'})
        cursor = max(cursor, hi)
    if cursor < end:
        missing.append({'start': cursor, 'end': end, 'reason': 'unpublished_scope'})
    return missing


def unpack_manifest(manifest):
    """Expand v2 dictionary references in memory; v1 remains readable unchanged."""
    if not manifest:return manifest
    version=manifest.get('version')
    if version==1:return manifest
    if version!=2:raise ValueError('Unsupported timeline version')
    catalog=manifest.get('series_catalog',{})
    result={k:v for k,v in manifest.items() if k!='series_catalog'}
    result['version']=1
    result['segments']=[]
    for segment in manifest['segments']:
        item=dict(segment)
        reference=item.pop('series_ref',None)
        if reference is not None:
            if reference not in catalog:raise ValueError('Missing series catalog reference')
            item['series']=catalog[reference]
        result['segments'].append(item)
    return result


def pack_manifest(manifest):
    """v2 wire format deduplicates immutable series metadata, never snapshot IDs."""
    expanded=unpack_manifest(manifest)
    result={k:v for k,v in expanded.items() if k not in ('segments','series_catalog')}
    result['version']=2;result['segments']=[];result['series_catalog']={}
    for segment in expanded['segments']:
        item=dict(segment)
        if 'series' in item:
            # Series is an unordered metadata set, identified by its stable ID.
            series=sorted(item.pop('series'),key=lambda r:r['series_id'])
            reference=digest(series)
            result['series_catalog'][reference]=series
            item['series_ref']=reference
        result['segments'].append(item)
    return result
