"""Monthly analytics. Nulls remain missing; rankings compare province means."""
from collections import defaultdict
from datetime import date
from statistics import mean, median

from app.schemas.dashboard import ApiModel, DashboardData, DashboardTrendRecord, ProvinceSnapshot
from pydantic import Field, model_validator

METRICS = {field.alias or name: name for name, field in DashboardTrendRecord.model_fields.items()
           if name not in {'province_code', 'date'}}
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


def build_analytics(data: DashboardData, query: AnalyticsQuery) -> DashboardAnalytics:
    names = {p.province_code: p.province_name for p in data.province_snapshots}
    if query.province_code != 'all' and query.province_code not in names:
        raise ValueError('Unknown province')
    # Month overlap, not comparison with the first day: a mid-month range still
    # selects that monthly observation. No daily precision is implied.
    def matches(month):
        return ((query.year is None or int(month[:4]) == query.year)
                and (query.month is None or int(month[5:]) == query.month)
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
    months = set(calendar)
    # Normalize to one value per province/month/metric before aggregating.
    grouped = defaultdict(lambda: defaultdict(list))
    available = list(data.metadata.metrics) if data.metadata else list(METRICS)
    for record in data.dashboard_trend_records:
        month = record.date.isoformat()[:7]
        if month not in months:
            continue
        for alias in available:
            value = getattr(record, METRICS[alias], None) if alias in METRICS else None
            if value is not None:
                grouped[(record.province_code, alias)][month].append(value)
    values = {key: {month: mean(samples) for month, samples in by_month.items()}
              for key, by_month in grouped.items()}
    ranking_metrics = [m for m in available if m in POLLUTION_METRICS or m == query.metric]
    rankings = []
    for metric in ranking_metrics:
        rows = []
        for code, name in names.items():
            samples = list(values.get((code, metric), {}).values())
            if samples:
                rows.append(dict(province_code=code, province_name=name,
                                 **statistics(samples, len(calendar)).model_dump()))
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
            snapshot[metric] = mean(samples_for_province) if samples_for_province else None
        snapshots.append(ProvinceSnapshot(**snapshot))
    return DashboardAnalytics(scope=query, summary=statistics(samples, len(calendar) * len(scope_codes)),
                              province_count=sum(bool(values.get((code, query.metric))) for code in scope_codes),
                              months=calendar, rankings=rankings, timeline=timeline,
                              province_snapshots=snapshots,
                              generation=data.metadata.generation if data.metadata else None)
