"""Snapshot-pinned historical reads over an immutable, disjoint publication manifest."""
import base64
import calendar
from datetime import datetime,timedelta,time,timezone
import hashlib
import json
from app.repositories.base import DataSourceUnavailable
from app.repositories.gold.manifest import decode
from app.repositories.gold.history_pages import window,batches,DATA_SCANS
from app.repositories.gold.serving import instant,literal,timestamp

VN=timezone(timedelta(hours=7))


def daily_bounds(lower,upper):
    if lower.astimezone(VN).time()!=time() or upper.astimezone(VN).time()!=time():
        raise ValueError('Daily/monthly bounds must align to VN midnight')


class GoldHistoryRepository:
    def __init__(self,serving):
        self.serving=serving
        self.client=serving.client
        self.prefix=serving.prefix

    def resolve(self,timeline_id=None):
        table='gold_timeline' if timeline_id else 'gold_timeline_current'
        filters='channel='+literal(self.serving.channel)
        if timeline_id:filters+=' AND timeline_id='+literal(timeline_id)
        rows=self.client.query('SELECT timeline_id,manifest_json FROM '+self.prefix+table+' WHERE '+filters)
        if len(rows)!=1:raise DataSourceUnavailable('No unique published historical timeline; run the additive migration')
        result=rows[0].copy()
        try:
            manifest=decode(json.loads(result['manifest_json']))
            if manifest['version']!=1:raise ValueError('Unsupported timeline version')
            result['segments']=manifest['segments']
            for segment in result['segments']:
                if instant(segment['start'])>=instant(segment['end']):raise ValueError('Empty interval')
                if not segment.get('withdrawn'):
                    if not segment['snapshots'] or not all(type(v) is int and v>0 for v in segment['snapshots'].values()):raise ValueError('Invalid snapshots')
                    if not segment['release_id'] or not segment['method_version'] or not isinstance(segment['series'],list):raise ValueError('Missing semantic identity')
                    if any(not all(v.get(k) for k in ('series_id','source_system','applicability_profile')) for v in segment['series']):raise ValueError('Invalid series identity')
            lanes={s['compatibility_id'] for s in result['segments']}
            for lane in lanes:
                ordered=sorted((s for s in result['segments'] if s['compatibility_id']==lane),key=lambda s:s['start'])
                if any(instant(a['end'])>instant(b['start']) for a,b in zip(ordered,ordered[1:])):raise ValueError('Overlapping published segments')
        except (KeyError,TypeError,ValueError) as exc:raise DataSourceUnavailable('Invalid historical manifest') from exc
        return result

    def select(self,context,start=None,end=None,source=None,series_id=None,method_version=None,applicability_profile=None,compatibility_id=None):
        candidates=context['segments']
        if not candidates:raise DataSourceUnavailable('Empty historical timeline')
        matching=[s for s in candidates if (not s.get('withdrawn') or s.get('series'))
                  and (not compatibility_id or s['compatibility_id']==compatibility_id)
                  and (not method_version or s.get('method_version')==method_version)
                  and (not source or any(v['source_system']==source for v in s['series']))
                  and (not series_id or any(v['series_id']==series_id for v in s['series']))
                  and (not applicability_profile or any(v['applicability_profile']==applicability_profile for v in s['series']))]
        matching_lanes={s['compatibility_id'] for s in matching}
        scoped=matching+[s for s in candidates if s.get('withdrawn') and
                         (s['compatibility_id']==compatibility_id if compatibility_id else s['compatibility_id'] in matching_lanes)]
        bounds=scoped or candidates
        lower=instant(start) if start else min(instant(s['start']) for s in bounds)
        upper=instant(end) if end else max(instant(s['end']) for s in bounds)
        if lower>=upper:raise ValueError('End must follow start')
        selected=[]
        for s in candidates:
            if instant(s['start'])>=upper or instant(s['end'])<=lower:continue
            if compatibility_id and s['compatibility_id']!=compatibility_id:continue
            if not s.get('withdrawn') or s.get('series'):
                if method_version and s['method_version']!=method_version:continue
                if source and not any(v['source_system']==source for v in s['series']):continue
                if series_id and not any(v['series_id']==series_id for v in s['series']):continue
                if applicability_profile and not any(v['applicability_profile']==applicability_profile for v in s['series']):continue
            selected.append(s)
        lanes={s['compatibility_id'] for s in selected if not s.get('withdrawn')}
        if len(lanes)>1:raise ValueError('Incompatible historical policies; select source/series/method/profile/compatibility_id explicitly')
        if compatibility_id:lanes={compatibility_id}
        if lanes:selected=[s for s in selected if s['compatibility_id'] in lanes]
        missing=[];cursor=lower
        for s in sorted(selected,key=lambda s:s['start']):
            lo,hi=max(lower,instant(s['start'])),min(upper,instant(s['end']))
            if lo>cursor:missing.append(dict(start=cursor.isoformat(),end=lo.isoformat(),reason='unpublished_scope'))
            if s.get('withdrawn'):missing.append(dict(start=lo.isoformat(),end=hi.isoformat(),reason='withdrawn_scope'))
            cursor=max(cursor,hi)
        if cursor<upper:missing.append(dict(start=cursor.isoformat(),end=upper.isoformat(),reason='unpublished_scope'))
        return selected,lower,upper,missing

    def sql(self,segments,resolution,lower,upper,pollutant,admin_code,source,series_id,method_version=None,applicability_profile=None):
        table='mart_air_quality_hourly' if resolution=='hourly' else 'mart_air_quality_daily'
        timecol='hour_start_utc' if resolution=='hourly' else 'aqi_date_local'
        pieces=[]
        for s in segments:
            if s.get('withdrawn'):continue
            lo,hi=max(lower,instant(s['start'])),min(upper,instant(s['end']))
            if resolution!='hourly' and (lo.astimezone(VN).time()!=time() or hi.astimezone(VN).time()!=time()):raise ValueError('Daily/monthly scope must align to local VN midnight')
            filters=['release_id='+literal(s['release_id'])]
            if resolution=='hourly':filters += [timecol+'>='+timestamp(lo),timecol+'<'+timestamp(hi)]
            else:filters += [timecol+'>=DATE '+literal(lo.astimezone(VN).date()),timecol+'<DATE '+literal(hi.astimezone(VN).date())]
            for name,value in [('pollutant',pollutant),('admin_code',admin_code),('source',source),('series_id',series_id),('aqi_method_version',method_version),('applicability_profile',applicability_profile)]:
                if value:filters.append(name+'='+literal(value))
            pieces.append('SELECT * FROM '+self.serving.table(table,s)+' WHERE '+' AND '.join(filters))
        return ' UNION ALL '.join(pieces)

    def air_quality(self,resolution='hourly',start=None,end=None,pollutant='pm25',admin_code=None,source=None,
                    series_id=None,method_version=None,applicability_profile=None,compatibility_id=None,
                    timeline_id=None,limit=10000,cursor=None,context=None):
        if resolution not in ('hourly','daily','monthly'):raise ValueError('Unknown resolution')
        limit=int(limit)
        if not 1<=limit<=25000:raise ValueError('Limit outside 1..25000')
        signature=hashlib.sha256(json.dumps([resolution,str(start),str(end),pollutant,admin_code,source,series_id,
            method_version,applicability_profile,compatibility_id],sort_keys=True).encode()).hexdigest()
        offset=0;page=0;legacy=False
        if cursor:
            try:
                token=json.loads(base64.urlsafe_b64decode(cursor.encode()).decode())
                if token['signature']!=signature or token['offset']<0:raise ValueError()
                if timeline_id and timeline_id!=token['timeline_id']:raise ValueError()
                timeline_id=token['timeline_id'];offset=int(token['offset'])
                legacy='version' not in token
                if not legacy and token['version']!=2:raise ValueError()
                page=int(token.get('page',0))
                if page<0:raise ValueError()
            except Exception as exc:raise ValueError('Invalid cursor or changed filters') from exc
        if context and timeline_id and context['timeline_id']!=timeline_id:raise ValueError('Cursor and pinned context differ')
        context=context or self.resolve(timeline_id)
        segments,lower,upper,missing=self.select(context,start,end,source,series_id,method_version,applicability_profile,compatibility_id)
        if resolution!='hourly':daily_bounds(lower,upper)
        if legacy:
            if len([s for s in segments if not s.get('withdrawn')])>DATA_SCANS:raise ValueError('Restart pagination: legacy cursor exceeds bounded query scope')
            page_segments,page_lower,page_upper,next_page=segments,lower,upper,None
        else:
            page_segments,page_lower,page_upper,next_page=window(segments,resolution,lower,upper,page)
        sql=self.sql(page_segments,resolution,page_lower,page_upper,pollutant,admin_code,source,series_id,method_version,applicability_profile)
        timecol='hour_start_utc' if resolution=='hourly' else 'aqi_date_local'
        if resolution=='monthly':
            timecol='month_local'
            # Daily sufficient statistics are canonical after scope overlay. No mean of means, no AVG(AQI).
            sql=('SELECT series_id,location_id,admin_code,source,pollutant,unit,aqi_method_version,applicability_profile,'
                 "CAST(date_trunc('month',aqi_date_local) AS date) month_local,"
                 'sum(concentration_sum)/nullif(sum(valid_hours),0) value,sum(concentration_sum) concentration_sum,'
                 'sum(valid_hours) valid_hours,sum(expected_hours) published_expected_hours,'
                 'count_if(valid_hours=expected_hours) valid_days,count_if(valid_hours>0) observed_days,count_if(aqi IS NOT NULL) aqi_valid_days,'
                 'min(minimum) minimum,max(maximum) maximum,'
                 "histogram(aqi_category) FILTER (WHERE aqi_category IS NOT NULL) aqi_category_counts "
                 'FROM ('+sql+') d GROUP BY series_id,location_id,admin_code,source,pollutant,unit,aqi_method_version,applicability_profile,date_trunc(\'month\',aqi_date_local)') if sql else ''
        rows=self.client.query('SELECT * FROM ('+sql+') h ORDER BY '+timecol+',series_id,pollutant OFFSET '+str(offset)+' LIMIT '+str(limit+1)) if sql else []
        more=len(rows)>limit;rows=rows[:limit]
        for row in rows:
            row['published_release_id']=row.get('release_id')
            row['published_timeline_id']=context['timeline_id']
            row['resolution']=resolution
            row['calendar_timezone']='Asia/Ho_Chi_Minh'
            if resolution=='monthly':
                month=datetime.fromisoformat(str(row['month_local']))
                row['calendar_expected_hours']=calendar.monthrange(month.year,month.month)[1]*24
                row['expected_hours']=row['calendar_expected_hours']
                row['completeness_ratio']=row['valid_hours']/row['calendar_expected_hours']
                row['aqi']=None;row['aqi_origin']='not_defined_for_month'
                row['aggregation_policy']='sum(concentration_sum)/sum(valid_hours); daily categories per series-date-method; no monthly AQI'
            elif resolution=='daily':row['observation_time']=None
        token=dict(timeline_id=context['timeline_id'],signature=signature,offset=offset+limit if more else 0)
        if not legacy:token.update(version=2,page=page if more else next_page)
        next_cursor=base64.urlsafe_b64encode(json.dumps(token).encode()).decode() if more or next_page is not None else None
        return dict(published_timeline_id=context['timeline_id'],scope_start_utc=lower.isoformat(),scope_end_utc=upper.isoformat(),
                    compatibility_ids=sorted({s['compatibility_id'] for s in segments}),
                    published_release_ids=sorted({s['release_id'] for s in segments if not s.get('withdrawn')}),
                    missing_scopes=missing,resolution=resolution,next_cursor=next_cursor,rows=rows)

    def aqi_distribution(self,start=None,end=None,admin_code=None,source=None,series_id=None,
                         method_version=None,applicability_profile=None,compatibility_id=None,timeline_id=None,limit=25000):
        context=self.resolve(timeline_id)
        segments,lower,upper,missing=self.select(context,start,end,source,series_id,method_version,applicability_profile,compatibility_id)
        daily_bounds(lower,upper)
        counts={}
        for batch in batches(segments):
            sql=self.sql(batch,'daily',lower,upper,'pm25',admin_code,source,series_id,method_version,applicability_profile)
            rows=self.client.query("SELECT coalesce(aqi_category,'unavailable') category,count(*) n FROM ("+sql+") d GROUP BY aqi_category")
            for row in rows:counts[row['category']]=counts.get(row['category'],0)+row['n']
        return dict(published_timeline_id=context['timeline_id'],counts=counts,series_days=sum(counts.values()),missing_scopes=missing)

    def quality(self,start=None,end=None,source=None,compatibility_id=None,timeline_id=None):
        context=self.resolve(timeline_id)
        segments,lower,upper,missing=self.select(context,start,end,source=source,compatibility_id=compatibility_id)
        daily_bounds(lower,upper)
        grouped={}
        summed=('valid_measurements','expected_hours','observed_slots','missing_hours','invalid_measurements','collection_attempts','failed_ingestions')
        for batch in batches(segments):
            pieces=[]
            for s in batch:
                lo,hi=max(lower,instant(s['start'])),min(upper,instant(s['end']))
                daily_bounds(lo,hi)
                filters=['release_id='+literal(s['release_id']),'date_local>=DATE '+literal(lo.astimezone(VN).date()),'date_local<DATE '+literal(hi.astimezone(VN).date())]
                if source:filters.append('source='+literal(source))
                pieces.append('SELECT * FROM '+self.serving.table('mart_source_quality_daily',s)+' WHERE '+' AND '.join(filters))
            sql=' UNION ALL '.join(pieces)
            rows=self.client.query('SELECT source,pollutant,'+','.join('sum('+name+') '+name for name in summed)+
                ',max(latest_observation_time) latest_observation_time FROM ('+sql+') q GROUP BY source,pollutant')
            for row in rows:
                key=(row['source'],row['pollutant'])
                if key not in grouped:grouped[key]=row.copy();continue
                current=grouped[key]
                for name in summed:
                    values=[v for v in (current[name],row[name]) if v is not None]
                    current[name]=sum(values) if values else None
                values=[v for v in (current['latest_observation_time'],row['latest_observation_time']) if v is not None]
                current['latest_observation_time']=max(values) if values else None
        rows=[grouped[k] for k in sorted(grouped)]
        for row in rows:
            row['absent_slots']=row['expected_hours']-row['observed_slots']
            row['missing_value_slots']=row['observed_slots']-row['valid_measurements']-row['invalid_measurements']
        return dict(published_timeline_id=context['timeline_id'],rows=rows,missing_scopes=missing,
                    note='Coverage in published series-days. missing_hours includes all unusable slots; absent_slots, missing_value_slots and invalid_measurements are separate. Collection telemetry remains NULL when unknown.')
