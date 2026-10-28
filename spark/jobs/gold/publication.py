"""Historical publication. Caller must hold the existing Gold single-writer lock."""
from datetime import datetime, timezone
import json
from timeline import overlay, digest, utc, pack_manifest, unpack_manifest


def current(spark, prefix, channel):
    rows = spark.table(prefix+'gold_timeline_current').where("channel='"+channel.replace("'", "''")+"'").collect()
    if len(rows) > 1:
        raise ValueError('Duplicate historical pointer')
    return rows[0].asDict() if rows else None


def entry_for(spark, prefix, release):
    snapshots = json.loads(release['output_snapshots_json'])
    def rows(name, fields):
        return [r.asDict() for r in spark.read.option('snapshot-id', str(snapshots[name])).table(prefix+name)
                .where("release_id='"+release['release_id']+"'").select(*fields).collect()]
    series = rows('dim_air_quality_series', ['series_id','dataset_id','source_system','source_contract_version',
                  'source_resolution_minutes','temporal_support','applicability_profile','spatial_policy_version'])
    semantics = [{k:v for k,v in s.items() if k!='series_id'} for s in series]
    semantics = sorted({json.dumps(s, sort_keys=True) for s in semantics})
    metrics = rows('dim_metric', ['metric_id','measurement_kind','unit','vertical_support','unit_policy_version'])
    geography = rows('dim_admin_unit', ['admin_code','boundary_hash','snapshot_date'])
    # Source snapshots/code may change during corrections; semantics must not.
    policy = dict(contract=release['contract_sha256'], method=release['method_version'], series=semantics,
                  metrics=sorted(metrics,key=lambda r:r['metric_id']),
                  geography=sorted([{k:str(v) for k,v in r.items()} for r in geography],key=lambda r:r['admin_code']))
    return dict(start=utc(release['scope_start_utc']), end=utc(release['scope_end_utc']),
                compatibility_id=digest(policy), release_id=release['release_id'], snapshots=snapshots,
                method_version=release['method_version'], contract_sha256=release['contract_sha256'],
                series=series, withdrawn=False)


def point(spark, prefix, record):
    row = {k:record[k] for k in spark.table(prefix+'gold_timeline_current').columns}
    spark.createDataFrame([row], spark.table(prefix+'gold_timeline_current').schema).createOrReplaceTempView('_timeline_pointer')
    spark.sql('MERGE INTO '+prefix+'gold_timeline_current t USING _timeline_pointer s ON t.channel=s.channel '
              'WHEN MATCHED THEN UPDATE SET * WHEN NOT MATCHED THEN INSERT *')


def publish(spark, prefix, release):
    old = current(spark,prefix,release['channel'])
    manifest = unpack_manifest(json.loads(old['manifest_json'])) if old else {'version':1,'segments':[], 'activated_releases':[]}
    # Replay never undoes an explicit rollback or resurrects withdrawn intervals.
    if release['release_id'] in manifest.get('activated_releases',[]):
        return old
    # Across rollback, a previously activated release remains an explicit operation.
    prior = spark.table(prefix+'gold_timeline').where("trigger_release_id='"+release['release_id']+"'").limit(1).collect()
    if prior:
        staged = prior[0].asDict()
        if staged['parent_timeline_id'] == (old['timeline_id'] if old else None):
            point(spark,prefix,staged)
            return staged
        return old
    manifest = overlay(manifest,entry_for(spark,prefix,release))
    manifest['activated_releases'] = sorted(set(manifest.get('activated_releases',[])+[release['release_id']]))
    return commit(spark,prefix,release['channel'],manifest,old,'publish',release['release_id'])


def commit(spark,prefix,channel,manifest,parent,operation,release_id=None):
    manifest=pack_manifest(manifest)
    record = dict(channel=channel,parent_timeline_id=parent['timeline_id'] if parent else None,
                  operation=operation,trigger_release_id=release_id,
                  manifest_json=json.dumps(manifest,sort_keys=True),published_at=datetime.now(timezone.utc))
    record['timeline_id'] = digest([channel,record['parent_timeline_id'],operation,release_id,manifest])
    spark.createDataFrame([record],spark.table(prefix+'gold_timeline').schema).createOrReplaceTempView('_timeline')
    spark.sql('MERGE INTO '+prefix+'gold_timeline t USING _timeline s ON t.timeline_id=s.timeline_id WHEN NOT MATCHED THEN INSERT *')
    point(spark,prefix,record)
    return record


def restore(spark,prefix,timeline_id):
    rows=spark.table(prefix+'gold_timeline').where("timeline_id='"+timeline_id+"'").collect()
    if len(rows)!=1:raise ValueError('Unknown immutable historical timeline')
    record=rows[0].asDict()
    for segment in json.loads(record['manifest_json'])['segments']:
        for name,snapshot_id in segment.get('snapshots',{}).items():
            from runtime import identifier
            identifier(name)
            spark.read.option('snapshot-id',str(int(snapshot_id))).table(prefix+name).limit(1).collect()
    return commit(spark,prefix,record['channel'],json.loads(record['manifest_json']),
                  current(spark,prefix,record['channel']),'rollback')
