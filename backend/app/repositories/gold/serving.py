"""Each request resolves one manifest, then time-travels every table by snapshot."""
from datetime import datetime,timezone,timedelta,date,time
import json
import re
from app.repositories.base import DataSourceUnavailable

TABLES={'dim_location','dim_air_quality_series','mart_air_quality_hourly','mart_air_quality_daily',
        'mart_air_quality_monthly','mart_source_quality_daily','fact_air_quality_hourly',
        'fact_waqi_station_daily_native','fact_emission_aggregate_native','fact_emission_source_native',
        'mart_emission_country_period_native'}


def ident(value):
    if not re.fullmatch('[a-z][a-z0-9_]*',value):
        raise ValueError('Invalid Gold SQL identifier')
    return value


def literal(value):
    return "'"+str(value).replace("'","''")+"'"


def instant(value):
    if isinstance(value,datetime):
        dt=value
    else:
        dt=datetime.fromisoformat(str(value).replace(' UTC','+00:00').replace('Z','+00:00'))
    if dt.tzinfo is None:
        raise ValueError('UTC offset required')
    return dt.astimezone(timezone.utc)


def timestamp(value):
    return 'TIMESTAMP '+literal(instant(value).strftime('%Y-%m-%d %H:%M:%S.%f')+' UTC')


class GoldServingRepository:
    def __init__(self,client,schema='gold',channel='air_quality'):
        self.client=client
        self.prefix='iceberg.'+ident(schema)+'.'
        self.channel=channel

    def resolve(self,release_id=None):
        if release_id:
            rows=self.client.query('SELECT release_id,output_snapshots_json,scope_start_utc,scope_end_utc FROM '+
                    self.prefix+'gold_release WHERE release_id='+literal(release_id)+' AND channel='+literal(self.channel))
        else:
            rows=self.client.query('SELECT * FROM '+self.prefix+'gold_current_release WHERE channel='+literal(self.channel))
        if len(rows)!=1:
            raise DataSourceUnavailable('No unique published Gold release for this channel')
        result=rows[0]
        try:
            result['snapshots']=json.loads(result['output_snapshots_json'])
            if not all(isinstance(v,int) and v>0 for v in result['snapshots'].values()):
                raise ValueError('Invalid snapshot mapping')
        except (TypeError,ValueError,KeyError) as exc:
            raise DataSourceUnavailable('Invalid Gold publication manifest') from exc
        return result

    def table(self,name,release):
        if name not in TABLES or name not in release['snapshots']:
            raise DataSourceUnavailable('Table absent from published Gold manifest')
        return self.prefix+ident(name)+' FOR VERSION AS OF '+str(release['snapshots'][name])

    def release_filter(self,release,alias=''):
        return (alias+'.' if alias else '')+'release_id='+literal(release['release_id'])

    def air_quality(self,resolution='hourly',start=None,end=None,pollutant='pm25',admin_code=None,release_id=None,limit=10000):
        release=self.resolve(release_id)
        table={'hourly':'mart_air_quality_hourly','daily':'mart_air_quality_daily','monthly':'mart_air_quality_monthly'}[resolution]
        timecol={'hourly':'hour_start_utc','daily':'aqi_date_local','monthly':'month_local'}[resolution]
        lower=instant(start) if start else instant(release['scope_start_utc'])
        upper=instant(end) if end else instant(release['scope_end_utc'])
        if lower>=upper or lower<instant(release['scope_start_utc']) or upper>instant(release['scope_end_utc']):
            raise ValueError('Query must fit one published release scope; end is exclusive')
        if resolution=='monthly' and (lower!=instant(release['scope_start_utc']) or upper!=instant(release['scope_end_utc'])):
            raise ValueError('Monthly mart must be read over its declared release scope; rebuild a new scope for a different period')
        filters=[self.release_filter(release),'pollutant='+literal(pollutant)]
        if resolution=='hourly':
            filters += [timecol+'>='+timestamp(lower),timecol+'<'+timestamp(upper)]
        else:
            zone=timezone(timedelta(hours=7))
            lo,hi=lower.astimezone(zone),upper.astimezone(zone)
            if (lo.time()!=time() or hi.time()!=time()):
                raise ValueError('Daily/monthly bounds must align to local VN midnight')
            if resolution=='monthly':
                # Partial month remains explicitly scoped by release metadata.
                lo=lo.replace(day=1)
            filters += [timecol+'>=DATE '+literal(lo.date()),timecol+'<DATE '+literal(hi.date())]
        if admin_code:
            filters.append('admin_code='+literal(admin_code))
        rows=self.client.query('SELECT * FROM '+self.table(table,release)+' WHERE '+' AND '.join(filters)+
                ' ORDER BY '+timecol+',admin_code,series_id LIMIT '+str(int(limit)+1))
        if len(rows)>limit:
            raise ValueError('Result exceeds limit; narrow the date/location scope')
        for row in rows:
            row['published_release_id']=release['release_id']
            row['resolution']=resolution
            row['calendar_timezone']='Asia/Ho_Chi_Minh'
            if resolution!='hourly':
                row['observation_time']=None
        return dict(published_release_id=release['release_id'],scope_start_utc=release['scope_start_utc'],
                    scope_end_utc=release['scope_end_utc'],resolution=resolution,rows=rows)

    def province_map(self,pollutant='pm25',at=None,release_id=None,source=None,series_id=None,method_version=None,applicability_profile=None,compatibility_id=None):
        timeline_id=None
        if release_id:
            release=self.resolve(release_id)
        else:
            from app.repositories.gold.history import GoldHistoryRepository
            history=GoldHistoryRepository(self)
            context=history.resolve()
            selected,_,_,_=history.select(context,start=at,end=(instant(at)+timedelta(hours=1)) if at else None,source=source,series_id=series_id,method_version=method_version,applicability_profile=applicability_profile,compatibility_id=compatibility_id)
            active=[s for s in selected if not s.get('withdrawn')]
            if not active:raise ValueError('No compatible published map scope for these filters')
            release=dict(max(active,key=lambda s:s['end']))
            release['scope_start_utc']=release['start'];release['scope_end_utc']=release['end']
            timeline_id=context['timeline_id']
        hourly=self.table('mart_air_quality_hourly',release)
        selections={k:v for k,v in [('source',source),('series_id',series_id),('aqi_method_version',method_version),('applicability_profile',applicability_profile)] if v}
        def selected_filters(alias=''):
            return ''.join(' AND '+(alias+'.' if alias else '')+k+'='+literal(v) for k,v in selections.items())
        if at is None:
            bounds=self.client.query('SELECT max(hour_start_utc) t FROM '+hourly+' WHERE '+self.release_filter(release)+
                    ' AND observation_time IS NOT NULL AND pollutant='+literal(pollutant)+
                    ' AND hour_start_utc>='+timestamp(release['scope_start_utc'])+' AND hour_start_utc<'+timestamp(release['scope_end_utc'])+selected_filters())
            at=bounds[0]['t'] if bounds else None
        if at is None:
            raise DataSourceUnavailable('No observations in selected published scope')
        hour=instant(at)
        if hour.minute or hour.second or hour.microsecond:
            raise ValueError('Map time must be an aligned UTC hour')
        if not instant(release['scope_start_utc'])<=hour<instant(release['scope_end_utc']):
            raise ValueError('Map hour outside published scope')
        # Province dimension drives map cardinality. All rows use same hour/source contract.
        sql='SELECT l.location_id,l.admin_code,l.name province_name,h.series_id,h.source,h.observation_time,h.value,h.unit,'+\
            'h.aqi,h.aqi_category,h.aqi_color,h.dominant_pollutants,h.aqi_method_version,h.aqi_origin,'+\
            'h.applicability_profile,coalesce(h.quality_status,\'missing\') quality_status,'+\
            'coalesce(h.missing_reason,CASE WHEN h.series_id IS NULL THEN \'no_series_in_scope\' END) missing_reason,'+\
            'h.aqi_status,h.aqi_missing_reason,h.coverage,h.source_resolution_minutes,h.temporal_support,'+\
            'h.spatial_representation,h.provider_aqi FROM '+self.table('dim_location',release)+' l LEFT JOIN '+hourly+\
            ' h ON h.location_id=l.location_id AND '+self.release_filter(release,'h')+\
            ' AND h.hour_start_utc='+timestamp(hour)+' AND h.pollutant='+literal(pollutant)+selected_filters('h')+\
            ' WHERE '+self.release_filter(release,'l')+" AND l.location_kind='province' ORDER BY l.admin_code"
        rows=self.client.query(sql)
        if len(rows)!=34 or len({r['admin_code'] for r in rows})!=34:
            raise DataSourceUnavailable('Published map is not one compatible series per 34 provinces')
        semantics={(r['source'],r['source_resolution_minutes'],r['temporal_support'],r['spatial_representation'],r['applicability_profile'],r['aqi_method_version']) for r in rows if r['series_id'] is not None}
        if len(semantics)>1:
            raise DataSourceUnavailable('Map requires a single compatible source/method/time contract')
        for r in rows:
            r.update(published_release_id=release['release_id'],resolution='hourly',hour_start_utc=hour.isoformat(),pollutant=pollutant)
        return dict(published_release_id=release['release_id'],published_timeline_id=timeline_id,compatibility_id=release.get('compatibility_id'),hour_start_utc=hour.isoformat(),resolution='hourly',rows=rows)

    def quality(self,release_id=None):
        release=self.resolve(release_id)
        rows=self.client.query('SELECT * FROM '+self.table('mart_source_quality_daily',release)+' WHERE '+self.release_filter(release)+
                               ' ORDER BY date_local,source,series_id,pollutant')
        return dict(published_release_id=release['release_id'],rows=rows)

    def admin_summary(self,release_id=None):
        release=self.resolve(release_id)
        # AQI distributions count series-days, never average AQI or sum concentrations.
        table=self.table('mart_air_quality_daily',release)
        rows=self.client.query('SELECT source,pollutant,unit,sum(concentration_sum)/nullif(sum(valid_hours),0) sample_mean,'+
            'sum(valid_hours) valid_hour_samples,sum(expected_hours) expected_hour_samples,'+
            'count_if(aqi IS NOT NULL) aqi_valid_series_days,'+
            'count_if(aqi_category=\'unhealthy\' OR aqi_category=\'very_unhealthy\' OR aqi_category=\'hazardous\') unhealthy_series_days '+
            'FROM '+table+' WHERE '+self.release_filter(release)+' GROUP BY source,pollutant,unit ORDER BY source,pollutant')
        return dict(published_release_id=release['release_id'],calendar_timezone='Asia/Ho_Chi_Minh',
                    aggregation_policy='valid-sample weighted; no population/area weighting across provinces',rows=rows)

    def native_emissions(self,pollutant='co2',period_type='year',aggregation_level='totals',year=None,source_type=None,limit=1000):
        release=self.resolve()
        table='fact_emission_source_native' if source_type else 'fact_emission_aggregate_native'
        filters=[self.release_filter(release),'pollutant='+literal(pollutant)]
        if source_type:
            filters.append('source_type='+literal(source_type))
            if year is not None:filters.append('year_label='+str(int(year)))
        else:
            filters += ['period_type='+literal(period_type),'aggregation_level='+literal(aggregation_level)]
            if year is not None:filters.append('year(period_start)='+str(int(year)))
        rows=self.client.query('SELECT * FROM '+self.table(table,release)+' WHERE '+' AND '.join(filters)+
                               ' ORDER BY period_start,pollutant LIMIT '+str(int(limit)+1))
        if len(rows)>limit:raise ValueError('Narrow native emission scope')
        return dict(published_release_id=release['release_id'],quantity_kind='native_emission_quantity',
                    note='Unit NULL means unverified; quantities are not labelled tonnes. GADM remains unallocated. No hierarchy/source-type sums.',rows=rows)
