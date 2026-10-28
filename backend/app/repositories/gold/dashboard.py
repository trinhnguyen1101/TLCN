"""Backward-compatible dashboard projection of materialized Gold marts."""
from datetime import datetime,time,timedelta,timezone,date
from app.repositories.base import DataSourceUnavailable
from app.repositories.gold.serving import GoldServingRepository,instant
from app.repositories.gold.history import GoldHistoryRepository
from app.repositories.gold.colors import concentration_metadata
from app.repositories.gold.contracts import source_policy
from app.schemas.dashboard import DashboardData,ProvinceSnapshot,DashboardTrendRecord,DashboardMetadata,MetricMetadata
from app.services.temporal import DashboardQuery,utc_bound

LABELS={'good':'Tốt','moderate':'Trung bình','poor':'Kém','unhealthy':'Xấu','very_unhealthy':'Rất xấu','hazardous':'Nguy hại'}
VN=timezone(timedelta(hours=7))


class GoldDashboardRepository:
    def __init__(self,serving:GoldServingRepository):
        self.serving=serving

    def get_dashboard(self,query:DashboardQuery|None=None):
        query=query or DashboardQuery('hourly')
        resolution='hourly' if query.resolution in ('3h','hourly') else query.resolution
        history=GoldHistoryRepository(self.serving)
        context=history.resolve()
        selection={name:getattr(query,name) for name in ('source','series_id','method_version','applicability_profile','compatibility_id')}
        requested_lower=(utc_bound(query.start) if resolution=='hourly' else datetime.combine(date.fromisoformat(query.start[:10]),time(),VN).astimezone(timezone.utc)) if query.start else None
        requested_upper=((utc_bound(query.end,end=True)+timedelta(microseconds=1)) if resolution=='hourly' else datetime.combine(date.fromisoformat(query.end[:10])+timedelta(days=1),time(),VN).astimezone(timezone.utc)) if query.end else None
        selected,lower,upper,missing=history.select(context,start=requested_lower,end=requested_upper,**selection)
        active=[s for s in selected if not s.get('withdrawn')]
        if not active:
            # A known source with an unpublished requested interval returns empty
            # observations and explicit missing scope, using its pinned geography.
            available,_,_,_=history.select(context,**selection)
            active=[s for s in available if not s.get('withdrawn')]
        if not active:raise DataSourceUnavailable('No active published concentration scope')
        release=max(active,key=lambda s:s['end'])
        selection['compatibility_id']=release['compatibility_id']
        _,available_lower,available_upper,_=history.select(context,**selection)
        if resolution=='hourly' and not query.start:lower=max(lower,upper-timedelta(days=7))
        rows=[]
        for pollutant in ['pm25','pm10','co','no2','so2','o3']:
            cursor=None;received=0
            while True:
                remaining=25000-received
                if remaining<=0:raise ValueError('Dashboard scope exceeds rendering limit; use paginated Gold history API')
                result=history.air_quality(resolution,lower,upper,pollutant,limit=min(10000,remaining),context=context,cursor=cursor,**selection)
                rows.extend(result['rows']);received+=len(result['rows'])
                cursor=result['next_cursor']
                if not cursor:break
        timecol={'hourly':'hour_start_utc','daily':'aqi_date_local','monthly':'month_local'}[resolution]
        points={}
        sources={r['source'] for r in rows}
        if not rows:sources={s['source_system'] for s in release['series']}
        if resolution!='monthly':
            semantics={(r['source_resolution_minutes'],r['temporal_support'],r['spatial_representation'],r['applicability_profile'],r['aqi_method_version']) for r in rows}
            if len(semantics)>1:
                raise DataSourceUnavailable('Dashboard requires one compatible temporal/spatial/method contract')
        series_by_location={}
        for r in rows:series_by_location.setdefault(r['location_id'],set()).add(r['series_id'])
        if any(len(series)>1 for series in series_by_location.values()):
            raise DataSourceUnavailable('Select one Gold series per location before pivoting')
        if len(sources)!=1:
            raise DataSourceUnavailable('Dashboard requires one compatible source')
        for r in rows:
            key=(r['admin_code'],r[timecol])
            point=points.setdefault(key,dict(province_code=r['admin_code'],date=r[timecol],pm25=None,pm10=None,o3=None,no2=None,so2=None,co=None))
            point[r['pollutant']]=r['value']
            point['aqi']=r.get('aqi')
            point.setdefault('metric_sample_counts',{})[r['pollutant']]=int(r.get('valid_hours',r['value'] is not None))
            # All six rows repeat the same precomputed overall; no AQI aggregation.
        trend=[DashboardTrendRecord(**p) for _,p in sorted(points.items())]
        available=[r[timecol] for r in rows if r['value'] is not None]
        latest=max(available) if available else max((r[timecol] for r in rows),default=None)
        grouped={}
        for r in rows:
            if r[timecol]==latest:
                p=grouped.setdefault(r['admin_code'],{})
                p[r['pollutant']]=r['value']
                p.setdefault('metric_quality',{})[r['pollutant']]=dict(quality_status=r.get('quality_status'),missing_reason=r.get('missing_reason'),observation_time=r.get('observation_time'),coverage=r.get('coverage'))
                p.update(aqi=r.get('aqi'),status=LABELS.get(r.get('aqi_category')),source=r['source'],series_id=r['series_id'],
                         location_id=r['location_id'],observation_time=r.get('observation_time'),
                         source_resolution_minutes=r.get('source_resolution_minutes'),temporal_support=r.get('temporal_support'),
                         applicability_profile=r.get('applicability_profile'),quality_status=r.get('quality_status'),
                         aqi_missing_reason=r.get('aqi_missing_reason'),aqi_status=r.get('aqi_status'),coverage=r.get('coverage'),
                         aqi_method_version=r.get('aqi_method_version'),published_release_id=r.get('published_release_id'),
                         aqi_origin=r.get('aqi_origin'),dominant_pollutants=r.get('dominant_pollutants'))
        for values in grouped.values():
            qualities=list(values.get('metric_quality',{}).values())
            statuses=[q['quality_status'] for q in qualities if q['quality_status'] is not None]
            values['quality_status']=(None if not statuses else 'ok' if len(statuses)==6 and all(s in ('ok','complete') for s in statuses)
                                      else 'partial' if any(values.get(p) is not None for p in ('pm25','pm10','co','no2','so2','o3')) else 'missing')
            coverages=[q['coverage'] for q in qualities]
            values['coverage']=coverages[0] if len(coverages)==6 and all(v is not None and v==coverages[0] for v in coverages) else None
        locations=self.serving.client.query('SELECT location_id,admin_code,name FROM '+self.serving.table('dim_location',release)+
                ' WHERE '+self.serving.release_filter(release)+" AND location_kind='province' ORDER BY admin_code")
        snapshots=[]
        for loc in locations:
            values=grouped.get(loc['admin_code'],dict(aqi=None,status=None,pm25=None,pm10=None))
            snapshots.append(ProvinceSnapshot(province_code=loc['admin_code'],province_name=loc['name'],**values))
        policy=source_policy(release.get('contract_sha256'))
        metadata=DashboardMetadata(source=next(iter(sources)),generation=context['timeline_id'],start=(lower.isoformat() if resolution=='hourly' else lower.astimezone(VN).date().isoformat()),end=((upper-timedelta(microseconds=1)).isoformat() if resolution=='hourly' else (upper-timedelta(microseconds=1)).astimezone(VN).date().isoformat()),
            snapshot_date=latest,metrics=concentration_metadata({'hourly':'hourly_native_samples','daily':'daily_available_sample_mean','monthly':'monthly_sample_weighted_mean'}[resolution]),
            temporal_aggregation={'hourly':'hourly_native_samples','daily':'daily_available_sample_mean','monthly':'monthly_sample_weighted_mean'}[resolution],
            timezone='UTC' if resolution=='hourly' else 'Asia/Ho_Chi_Minh',minimum_spatial_coverage=policy.get('minimum_spatial_coverage'),minimum_monthly_coverage=policy.get('minimum_monthly_coverage'),
            note='Gold đã materialize. AQI chỉ có khi đủ eligibility; daily/monthly concentration là thống kê mẫu thật, không nội suy. Lịch sử ghép các scope đã công bố; khoảng chưa công bố giữ missing.',
            query_start=lower if resolution=='hourly' else lower.astimezone(VN),query_end=(upper-timedelta(microseconds=1)) if resolution=='hourly' else (upper-timedelta(microseconds=1)).astimezone(VN),observation_start=available_lower.isoformat(),observation_end=available_upper.isoformat(),
            available_years=list(range(available_lower.astimezone(VN).year,(available_upper-timedelta(microseconds=1)).astimezone(VN).year+1)),
            published_release_id=release['release_id'],published_timeline_id=context['timeline_id'],compatibility_id=release['compatibility_id'],
            published_release_ids=result['published_release_ids'],missing_scopes=result['missing_scopes'])
        return DashboardData(province_snapshots=snapshots,emission_records=[],emission_sectors=[],dashboard_trend_records=trend,metadata=metadata)

    def get_analytics(self,query):
        from app.services.analytics import build_analytics
        return build_analytics(self.get_dashboard(DashboardQuery('monthly')),query)

    def get_admin_dashboard(self,query=None):
        from app.schemas.dashboard import AdminDashboardData,AdminDashboardTrendRecord
        data=self.get_dashboard(query)
        # Explicit empty annual/KPI projections: bounded sample means are not annual
        # estimates. Admin aggregate contract is /api/gold/admin/summary.
        return AdminDashboardData(province_snapshots=data.province_snapshots,emission_records=[],emission_sectors=[],
            dashboard_trend_records=[AdminDashboardTrendRecord(**r.model_dump()) for r in data.dashboard_trend_records],
            priority_areas=[],annual_province_summaries=[],metadata=data.metadata)
