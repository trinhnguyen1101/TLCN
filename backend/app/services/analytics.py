"""Monthly analytics. Nulls remain missing; rankings compare province means."""
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from statistics import mean, median
from math import ceil

from app.schemas.dashboard import ApiModel, DashboardData, DashboardTrendRecord, ProvinceSnapshot
from pydantic import Field, model_validator

METRICS = {field.alias or name: name for name, field in DashboardTrendRecord.model_fields.items()
           if name not in {'province_code', 'date', 'aqi', 'metric_sample_counts', 'metric_quality_reasons'}}
POLLUTION_METRICS = {'pm1', 'pm25', 'pm10', 'o3', 'no2', 'so2', 'co', 'aod550',
                     'o3Column', 'no2Column', 'so2Column', 'coColumn'}


class AnalyticsQuery(ApiModel):
    province_code: str = 'all'
    metric: str = 'pm25'
    year: int | None = Field(default=None, ge=1900, le=2200)
    month: int | None = Field(default=None, ge=1, le=12)
    start_date: date | None = None
    end_date: date | None = None

    @model_validator(mode='after')
    def validate_filters(self):
        if self.metric not in METRICS:
            raise ValueError('Unknown metric')
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValueError('startDate must precede endDate')
        return self


class Statistics(ApiModel):
    mean: float | None = None
    median: float | None = None
    minimum: float | None = None
    maximum: float | None = None
    valid_count: int = 0
    expected_count: int = 0


class ProvinceRank(Statistics):
    province_code: str
    province_name: str
    rank: int


class MetricRanking(ApiModel):
    metric: str
    unit: str
    rows: list[ProvinceRank]


class MonthValues(ApiModel):
    date: str
    values: dict[str, float | None]


class DashboardAnalytics(ApiModel):
    aggregation_policy: str = "monthly observations; counts/median/range use province-month grain"
    scope: AnalyticsQuery
    summary: Statistics
    province_count: int
    months: list[str]
    rankings: list[MetricRanking]
    timeline: list[MonthValues]
    province_snapshots: list[ProvinceSnapshot]
    generation: str | None


def statistics(values, expected):
    return Statistics(mean=mean(values) if values else None,
                      median=median(values) if values else None,
                      minimum=min(values) if values else None,
                      maximum=max(values) if values else None,
                      valid_count=len(values), expected_count=expected)


def build_analytics(data: DashboardData, query: AnalyticsQuery, resolution="monthly") -> DashboardAnalytics:
    names = {p.province_code: p.province_name for p in data.province_snapshots}
    if query.province_code != 'all' and query.province_code not in names:
        raise ValueError('Unknown province')
    # Month overlap, not comparison with the first day: a mid-month range still
    # selects that monthly observation. No daily precision is implied.
    def matches(month):
        return ((query.year is None or int(month[:4]) == query.year)
                and (query.month is None or int(month[5:7]) == query.month)
                and (query.start_date is None or month >= query.start_date.isoformat()[:7])
                and (query.end_date is None or month <= query.end_date.isoformat()[:7]))

    # Build a continuous source calendar so missing entire months count as gaps.
    dates = [r.date for r in data.dashboard_trend_records]
    calendar = []
    if dates:
        first, last = min(dates), max(dates)
        for ordinal in range(first.year * 12 + first.month - 1, last.year * 12 + last.month):
            year, month = divmod(ordinal, 12)
            key = f'{year:04d}-{month + 1:02d}'
            if matches(key):
                calendar.append(key)
    def period_key(value):
        if resolution == "monthly":
            return value.isoformat()[:7]
        if resolution == "daily":
            return value.isoformat()[:10]
        return value.isoformat()

    if resolution != "monthly":
        calendar = []
        first = data.metadata.query_start if data.metadata else None
        last = data.metadata.query_end if data.metadata else None
        if first and last:
            step = timedelta(days=1) if resolution == "daily" else timedelta(hours=3 if resolution == "3h" else 1)
            current = first.replace(hour=0, minute=0, second=0, microsecond=0) if resolution == "daily" else datetime.fromtimestamp(ceil(first.timestamp() / step.total_seconds()) * step.total_seconds(), tz=timezone.utc)
            while current <= last:
                key = period_key(current)
                if matches(key[:7]) and (query.start_date is None or current.date() >= query.start_date) and (query.end_date is None or current.date() <= query.end_date):
                    calendar.append(key)
                current += step
    months = set(calendar)
    # Normalize to one value per province/month/metric before aggregating.
    grouped = defaultdict(lambda: defaultdict(list))
    weighted=any(r.metric_sample_counts is not None for r in data.dashboard_trend_records)
    available = list(data.metadata.metrics) if data.metadata else list(METRICS)
    for record in data.dashboard_trend_records:
        month = period_key(record.date)
        if month not in months:
            continue
        for alias in available:
            value = getattr(record, METRICS[alias], None) if alias in METRICS else None
            if value is not None:
                grouped[(record.province_code, alias)][month].append((value,(record.metric_sample_counts or {}).get(alias,1)))
    weights={key:{month:sum(w for _,w in samples) for month,samples in by_month.items()} for key,by_month in grouped.items()}
    values={key:{month:sum(v*w for v,w in samples)/weights[key][month] for month,samples in by_month.items() if weights[key][month]>0}
            for key,by_month in grouped.items()}
    def scoped_statistics(codes,metric,expected):
        samples=[v for code in codes for v in values.get((code,metric),{}).values()]
        result=statistics(samples,expected)
        pairs=[(v,weights[(code,metric)][month]) for code in codes for month,v in values.get((code,metric),{}).items()]
        if pairs and weighted:result.mean=sum(v*w for v,w in pairs)/sum(w for _,w in pairs)
        return result
    ranking_metrics = [m for m in available if m in POLLUTION_METRICS or m == query.metric]
    rankings = []
    for metric in ranking_metrics:
        rows = []
        for code, name in names.items():
            samples = list(values.get((code, metric), {}).values())
            if samples:
                rows.append(dict(province_code=code, province_name=name,
                                 **scoped_statistics([code],metric,len(calendar)).model_dump()))
        rows.sort(key=lambda row: (-row['mean'], row['province_code']))
        previous, rank = None, 0
        ranked = []
        for index, row in enumerate(rows):
            if row['mean'] != previous:
                rank = index + 1
            previous = row['mean']
            ranked.append(ProvinceRank(rank=rank, **row))
        unit = data.metadata.metrics[metric].unit if data.metadata and metric in data.metadata.metrics else ('mg/m³' if metric == 'co' else 'µg/m³')
        rankings.append(MetricRanking(metric=metric, unit=unit, rows=ranked))
    scope_codes = list(names) if query.province_code == 'all' else [query.province_code]
    samples = [v for code in scope_codes for v in values.get((code, query.metric), {}).values()]
    timeline = [MonthValues(date=month, values={code: values.get((code, query.metric), {}).get(month)
                                              for code in names}) for month in calendar]
    snapshots = []
    for province in data.province_snapshots:
        snapshot = province.model_dump(by_alias=True)
        snapshot.update(aqi=None, status=None)
        for metric in ('pm1', 'pm25', 'pm10'):
            samples_for_province = list(values.get((province.province_code, metric), {}).values())
            snapshot[metric] = scoped_statistics([province.province_code],metric,len(calendar)).mean
        snapshots.append(ProvinceSnapshot(**snapshot))
    return DashboardAnalytics(scope=query, summary=scoped_statistics(scope_codes,query.metric,len(calendar)*len(scope_codes)),
                              aggregation_policy=(f'{resolution} observations; mean weighted by valid source samples; count/range at province-period grain' if resolution != 'monthly' else 'mean weighted by valid hourly samples; median/range/count at province-month grain' if weighted else 'monthly observations; counts/median/range use province-month grain'),
                              province_count=sum(bool(values.get((code, query.metric))) for code in scope_codes),
                              months=calendar, rankings=rankings, timeline=timeline,
                              province_snapshots=snapshots,
                              generation=data.metadata.generation if data.metadata else None)
