"""Reference-aware dry run. This module deliberately contains no deletion API."""
from datetime import datetime,timedelta,timezone
import json


def timestamp(value):
    if isinstance(value,str):value=datetime.fromisoformat(value.replace('Z','+00:00'))
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def references(prefix,releases,timelines,pointers=()):
    kept={};source_tables=set();registered=set();issues=[]
    def keep(table,snapshot,reason):
        if type(snapshot) is not int or snapshot<=0:raise ValueError('Invalid referenced snapshot')
        kept.setdefault(table,{}).setdefault(snapshot,set()).add(reason)
    for release in releases:
        registered.add(release['release_id'])
        for table,snapshot in json.loads(release['input_snapshots_json']).items():
            source_tables.add(table);keep(table,snapshot,'input:'+release['release_id'])
        for table,snapshot in json.loads(release['output_snapshots_json']).items():keep(prefix+table,snapshot,'release:'+release['release_id'])
    for record in timelines:
        # Both v1/v2 retain snapshot mappings inline; no series expansion needed.
        manifest=json.loads(record['manifest_json'])
        if manifest.get('version') not in (1,2):raise ValueError('Unsupported timeline version')
        for segment in manifest['segments']:
            if segment.get('withdrawn'):continue
            release=segment['release_id']
            if release not in registered:issues.append('Timeline references unknown release '+release)
            for table,snapshot in segment['snapshots'].items():keep(prefix+table,snapshot,'timeline:'+record['timeline_id'])
    for pointer in pointers:
        if pointer['release_id'] not in registered:issues.append('Legacy pointer references unknown release '+pointer['release_id'])
        for table,snapshot in json.loads(pointer['output_snapshots_json']).items():keep(prefix+table,snapshot,'current_release')
    return dict(kept=kept,source_tables=source_tables,registered=registered,issues=issues)


def dry_run(refs,inventory,now=None,minimum_age_days=90,inventory_complete=True):
    now=timestamp(now or datetime.now(timezone.utc));present={};protected=[];review=[];recent=[]
    for item in inventory:
        row=dict(item);table=row['table'];sid=row['snapshot_id'];present.setdefault(table,set()).add(sid)
        reasons=set(refs['kept'].get(table,{}).get(sid,()))
        if table in refs['source_tables']:reasons.add('source_table_read_only')
        if row.get('is_head'):reasons.add('current_table_head')
        if row.get('named_refs'):reasons.add('named_snapshot_reference')
        if reasons:protected.append(dict(row,reasons=sorted(reasons)))
        elif now-timestamp(row['committed_at'])<timedelta(days=minimum_age_days):recent.append(row)
        else:review.append(row)
    missing=[dict(table=t,snapshot_id=s) for t,ids in refs['kept'].items() for s in ids if s not in present.get(t,set())]
    complete=inventory_complete and not missing and not refs['issues']
    # A review candidate is not permission to expire a snapshot or remove a file.
    # Keep sources, all rollback/registry references, current heads and named refs.
    return dict(dry_run=True,cleanup_enabled=False,delete_candidates=[],inventory_complete=complete,
        missing_references=missing,issues=refs['issues'],protected_snapshots=protected,recent_unreferenced=recent,
        unreferenced_snapshot_review_candidates=review if complete else [],
        minimum_age_days=minimum_age_days,
        note='All released/rollback/input references protected. Review candidates may be intermediate or staged; no orphan-file or object deletion classification is made.')
