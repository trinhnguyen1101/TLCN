from datetime import date

import pytest
from app.schemas.dashboard import DashboardData, DashboardTrendRecord, ProvinceSnapshot
from app.services.analytics import AnalyticsQuery, build_analytics


def sample():
    provinces = [ProvinceSnapshot(province_code=code, province_name=code, aqi=None, status=None, pm25=None, pm10=None) for code in ['a', 'b', 'c']]
    records = []
    for code, month, value in [('a', 1, 10), ('a', 3, 30), ('b', 1, 20), ('b', 3, None)]:
        records.append(DashboardTrendRecord(province_code=code, date=date(2025, month, 1), pm25=value, pm10=value, o3=None, no2=None, so2=None, co=None))
    return DashboardData(province_snapshots=provinces, dashboard_trend_records=records, emission_records=[], emission_sectors=[])


def test_nulls_gaps_ties_and_summary():
    result = build_analytics(sample(), AnalyticsQuery())
    assert result.summary.mean == 20
    assert result.summary.median == 20
    assert result.summary.minimum == 10
    assert result.summary.maximum == 30
    assert result.summary.valid_count == 3
    assert result.summary.expected_count == 9
    assert result.months == ['2025-01', '2025-02', '2025-03']
    assert result.timeline[1].values == {'a': None, 'b': None, 'c': None}
    ranks = next(r for r in result.rankings if r.metric == 'pm25').rows
    assert [(r.province_code, r.rank) for r in ranks] == [('a', 1), ('b', 1)]
    assert ranks[1].valid_count == 1


def test_province_drilldown_preserves_national_rankings():
    result = build_analytics(sample(), AnalyticsQuery(province_code='b'))
    assert result.summary.valid_count == 1
    assert result.summary.expected_count == 3
    assert result.province_count == 1
    assert len(next(r for r in result.rankings if r.metric == 'pm25').rows) == 2


def test_midmonth_range_and_filtered_map():
    result = build_analytics(sample(), AnalyticsQuery(start_date=date(2025, 3, 15), end_date=date(2025, 3, 20)))
    assert result.months == ['2025-03']
    assert result.summary.mean == 30
    assert result.province_snapshots[0].pm25 == 30
    assert result.province_snapshots[1].pm25 is None
    assert result.province_snapshots[0].aqi is None


def test_missing_metric_and_empty_period():
    result = build_analytics(sample(), AnalyticsQuery(metric='co', year=2024))
    assert result.summary.mean is None
    assert result.summary.valid_count == result.summary.expected_count == 0
    assert result.timeline == []
    assert not next(r for r in result.rankings if r.metric == 'co').rows


@pytest.mark.anyio
async def test_api_aliases_and_validation(client):
    response = await client.get('/api/dashboard/analytics', params={'year': 2025, 'month': 2, 'metric': 'pm10'})
    assert response.status_code == 200, response.text
    data = response.json()
    assert data['scope']['metric'] == 'pm10'
    assert data['months'] == ['2025-02']
    code = data['rankings'][0]['rows'][0]['provinceCode']
    response = await client.get('/api/dashboard/analytics', params={'provinceCode': code, 'startDate': '2025-02-15', 'endDate': '2025-02-20'})
    assert response.status_code == 200, response.text
    assert response.json()['scope']['provinceCode'] == code
    assert response.json()['summary']['expectedCount'] == 1
    for params in [{'month': 13}, {'metric': 'bogus'}, {'provinceCode': 'bogus'}, {'startDate': '2025-02-01', 'endDate': '2025-01-01'}]:
        response = await client.get('/api/dashboard/analytics', params=params)
        assert response.status_code == 422, response.text


def test_cache_reuse_generation_change_and_outage(monkeypatch):
    from app.repositories.base import DataSourceUnavailable
    from app.schemas.dashboard import DashboardMetadata
    from app.services.dashboard import DashboardService
    import app.services.dashboard as service_module

    data = sample()
    data.metadata = DashboardMetadata(
        source='test', generation='one', start='2025-01-01', end='2025-03-31',
        snapshot_date=None, metrics={'pm25': {'unit': 'µg/m³', 'quantity': 'concentration'}},
        temporal_aggregation='monthly_mean', timezone='UTC',
        minimum_spatial_coverage=.95, minimum_monthly_coverage=.75, note='Test fixture',
    )

    class Repository:
        fail = False

        def get_dashboard(self):
            if self.fail:
                raise DataSourceUnavailable('unavailable')
            return data

    repository = Repository()
    service = DashboardService(repository)
    calls = []
    original = service_module.build_analytics

    def tracked(*args):
        calls.append(True)
        return original(*args)

    monkeypatch.setattr(service_module, 'build_analytics', tracked)
    query = AnalyticsQuery()
    service.get_analytics(query)
    service.get_analytics(query)
    assert len(calls) == 1
    data.metadata.generation = 'two'
    data.dashboard_trend_records[0].pm25 = 40
    assert service.get_analytics(query).summary.mean == 30
    assert len(calls) == 2
    repository.fail = True
    with pytest.raises(DataSourceUnavailable):
        service.get_analytics(query)
    repository.fail = False
    for year in range(2000, 2035):
        service.get_analytics(AnalyticsQuery(year=year))
    assert len(service._analytics_cache) == 32


def test_duplicate_month_normalization_and_valid_zero():
    data = sample()
    duplicate = data.dashboard_trend_records[0].model_copy()
    duplicate.pm25 = 0
    data.dashboard_trend_records.append(duplicate)
    result = build_analytics(data, AnalyticsQuery(province_code='a', month=1))
    assert result.summary.mean == 5
    assert result.summary.valid_count == result.summary.expected_count == 1


@pytest.mark.anyio
async def test_response_supports_gzip(client):
    response = await client.get('/api/dashboard/analytics', headers={'Accept-Encoding': 'gzip'})
    assert response.status_code == 200
    assert response.headers['content-encoding'] == 'gzip'
