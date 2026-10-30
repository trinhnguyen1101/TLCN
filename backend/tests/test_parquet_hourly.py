"""Standalone hourly serving contract, independent of Lakehouse services."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from app.repositories.parquet.dashboard import ParquetDashboardRepository
from app.repositories.base import DataSourceUnavailable
from app.services.temporal import DashboardQuery
from app.main import create_app
from app.core.config import Settings
from httpx import AsyncClient, ASGITransport


@pytest.fixture
def hourly(tmp_path):
    generation = 'a' * 32
    folder = tmp_path / 'runs' / generation
    observations = folder / 'observations/pm25/2025'
    observations.mkdir(parents=True)
    (folder / 'monthly').mkdir()
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    times = [start + timedelta(hours=i) for i in range(24)]
    table = pa.table({'timestamp': times, 'province_code': ['01'] * 24,
                      'metric': ['pm25'] * 24, 'unit': ['µg/m³'] * 24,
                      'value': [float(i) for i in range(24)],
                      'valid_area_fraction': [1.] * 24, 'quality_flag': ['ok'] * 24})
    pq.write_table(table, observations / 'part-00000.parquet')
    pq.write_table(pa.Table.from_pylist([dict(timestamp=start, province_code='01', metric='pm25',
        unit='µg/m³', value=11.5, sample_count=24, temporal_coverage_fraction=24/744)]), folder / 'monthly/pm25.parquet')
    manifest = dict(schema_version=1, generation=generation, province_count=1, minimum_coverage=.95,
        cadence_hours=1, temporal_origin='interpolated', provinces=[dict(code='01', name='Hà Nội')],
        sources=[dict(name='pm25', unit='µg/m³', quantity='surface_mass_concentration',
                      start=times[0].isoformat(), end=times[-1].isoformat(), cadence_hours=1)])
    (folder / 'manifest.json').write_text(json.dumps(manifest))
    (tmp_path / 'CURRENT').write_text(generation)
    return ParquetDashboardRepository(tmp_path), observations / 'part-00000.parquet'


def test_hourly_intermediate_slots_cache_and_null_aqi(hourly):
    repo, _ = hourly
    query = DashboardQuery('hourly')
    data = repo.get_dashboard(query)
    assert [r.date.hour for r in data.dashboard_trend_records] == list(range(24))
    assert data.metadata.temporal_origin == 'interpolated'
    assert data.metadata.cadence_hours == 1
    assert data.province_snapshots[0].aqi is None
    assert len(repo._queries) == 1
    data.dashboard_trend_records[0].pm25 = -1
    assert repo.get_dashboard(query).dashboard_trend_records[0].pm25 == 0


def test_daily_coverage_and_weight(hourly):
    repo, path = hourly
    assert repo.get_dashboard(DashboardQuery('daily')).dashboard_trend_records[0].pm25 == 11.5
    table = pq.read_table(path)
    table = table.set_column(table.schema.get_field_index('value'), 'value', pa.array([None] * 7 + list(range(17)), type=pa.float64()))
    pq.write_table(table, path)
    daily = repo.get_dashboard(DashboardQuery('daily')).dashboard_trend_records[0]
    assert daily.pm25 is None  # 17/24 is below 75%, unlike the old six-sample rule.
    assert daily.metric_sample_counts['pm25'] == 17
    assert repo.get_dashboard(DashboardQuery('monthly')).dashboard_trend_records[0].pm25 is None


def test_duplicates_and_utc(hourly):
    repo, path = hourly
    table = pq.read_table(path)
    pq.write_table(pa.concat_tables([table, table.slice(0, 1)]), path)
    with pytest.raises(DataSourceUnavailable):
        repo.get_dashboard(DashboardQuery('hourly'))


@pytest.mark.anyio
async def test_hourly_api_and_admin(hourly):
    repo, _ = hourly
    client = AsyncClient(transport=ASGITransport(app=create_app(Settings(), repo)), base_url="http://test")
    for endpoint in ['/api/dashboard', '/api/admin/dashboard']:
        response = await client.get(endpoint, params={'resolution': 'hourly', 'start': '2025-01-01T01:00:00Z', 'end': '2025-01-01T05:00:00Z'})
        assert response.status_code == 200, response.text
        rows = response.json()['dashboardTrendRecords']
        assert len(rows) == 5
        assert rows[0]['date'] == '2025-01-01T01:00:00Z'
        assert rows[-1]['pm25'] == 5

    await client.aclose()


def test_real_grib_conversion_and_immutable_publication(tmp_path):
    """Use source messages, including intermediate hours and an identical duplicate."""
    from app.etl.eac4 import build, DEFAULT_INPUT, DEFAULT_BOUNDARIES
    import eccodes as ec
    source = DEFAULT_INPUT / 'pm2p5_2003_2025_vietnam.grib'
    if not source.exists():
        pytest.skip('Local hourly GRIB is not installed')
    inputs = tmp_path / 'inputs'
    inputs.mkdir()
    with source.open('rb') as stream, (inputs / source.name).open('wb') as output:
        last = None
        for _ in range(24):
            handle = ec.codes_grib_new_from_file(stream)
            try:
                last = ec.codes_get_message(handle)
                output.write(last)
            finally:
                ec.codes_release(handle)
        output.write(last)
    output = tmp_path / 'serving'
    first = build(inputs, DEFAULT_BOUNDARIES, output)
    second = build(inputs, DEFAULT_BOUNDARIES, output)
    assert (output / 'runs' / first['generation'] / 'manifest.json').exists()
    assert (output / 'CURRENT').read_text().strip() == second['generation']
    assert second['sources'][0]['messages'] == 24
    assert second['sources'][0]['duplicate_messages_skipped'] == 1
    assert second['sources'][0]['unit'] == 'µg/m³'
    assert second['sources'][0]['interpolation_method'] == 'pchip'
    data = ParquetDashboardRepository(output).get_dashboard(DashboardQuery('hourly'))
    assert {r.date.hour for r in data.dashboard_trend_records} == set(range(24))
    assert all(r.date.tzinfo is not None for r in data.dashboard_trend_records)
    # A failed rebuild must leave the published pointer and generations intact.
    with source.open('rb') as stream:
        handle = ec.codes_grib_new_from_file(stream)
        try:
            ec.codes_set_values(handle, ec.codes_get_values(handle) + 1)
            conflicting = ec.codes_get_message(handle)
        finally:
            ec.codes_release(handle)
    with (inputs / source.name).open('ab') as stream:
        stream.write(conflicting)
    with pytest.raises(ValueError, match='Conflicting duplicate'):
        build(inputs, DEFAULT_BOUNDARIES, output)
    assert (output / 'CURRENT').read_text().strip() == second['generation']


@pytest.mark.anyio
async def test_hourly_analytics_bounds(hourly):
    repo, _ = hourly
    async with AsyncClient(transport=ASGITransport(app=create_app(Settings(), repo)), base_url='http://test') as client:
        response = await client.get('/api/dashboard/analytics', params=dict(resolution='hourly', start='2025-01-01T01:00:00Z', end='2025-01-01T05:00:00Z'))
        assert response.status_code == 200, response.text
        body = response.json()
        assert body['summary']['validCount'] == 5
        assert body['summary']['mean'] == 3
        assert len(body['timeline']) == 5
        response = await client.get('/api/dashboard?resolution=hourly&start=2025-01-01&end=2025-03-01')
        assert response.status_code == 422


def test_unit_and_cadence_validation():
    from app.etl.metrics import resolve_metric
    assert resolve_metric(210073, 'kg m**-3').scale == 1e9
    with pytest.raises(ValueError):
        resolve_metric(210073, 'kg kg**-1')
    from app.etl.metrics import convert_direct
    with pytest.raises(ValueError):
        convert_direct(resolve_metric(210121, 'kg kg**-1'), __import__('numpy').array([1e-7]))
    codes = pa.array(['01'])
    instant = datetime(2025, 1, 1, 1, tzinfo=timezone.utc)
    table = pa.table(dict(timestamp=[instant], province_code=['01'], metric=['pm25'], unit=['µg/m³'], value=pa.array([None], type=pa.float64()), valid_area_fraction=[0.], quality_flag=['insufficient_coverage']))
    ParquetDashboardRepository._validate_observations(table, 'pm25', 'µg/m³', codes, 1)
    with pytest.raises(ValueError):
        ParquetDashboardRepository._validate_observations(table, 'pm25', 'µg/m³', codes, 3)
    naive = table.set_column(0, 'timestamp', pa.array([instant.replace(tzinfo=None)]))
    with pytest.raises(ValueError):
        ParquetDashboardRepository._validate_observations(naive, 'pm25', 'µg/m³', codes, 1)


@pytest.mark.anyio
async def test_default_resolution_offset_bounds_and_legacy_decimation(hourly):
    repo, _ = hourly
    async with AsyncClient(transport=ASGITransport(app=create_app(Settings(), repo)), base_url='http://test') as client:
        response = await client.get('/api/dashboard')
        assert response.status_code == 200
        assert response.json()['metadata']['temporalAggregation'] == 'hourly'
        response = await client.get('/api/dashboard', params=dict(resolution='hourly', start='2025-01-01T08:00:00+07:00', end='2025-01-01T12:00:00+07:00'))
        assert [row['pm25'] for row in response.json()['dashboardTrendRecords']] == list(range(1, 6))
        response = await client.get('/api/dashboard', params=dict(resolution='3h'))
        assert [row['pm25'] for row in response.json()['dashboardTrendRecords']] == list(range(0, 24, 3))


def test_admin_annual_projection_weights_valid_source_samples(hourly):
    from app.schemas.dashboard import DashboardTrendRecord
    from app.services.admin_projection import project_admin_dashboard
    repo, _ = hourly
    data = repo.get_dashboard(DashboardQuery('hourly'))
    data.metadata.temporal_aggregation = 'monthly_mean'
    data.dashboard_trend_records = [DashboardTrendRecord(province_code='01', date=datetime(2025,month,1,tzinfo=timezone.utc).date(),
        pm25=100 if month == 1 else 0, pm10=None, o3=None, no2=None, so2=None, co=None,
        metric_sample_counts={'pm25': 744 if month == 1 else 672}) for month in range(1,13)]
    annual = project_admin_dashboard(data).annual_province_summaries
    assert len(annual) == 1
    assert annual[0].pm25_average == pytest.approx(100 * 744 / (744 + 11 * 672))


def test_aggregated_cache_copies_isolate_quality_and_counts(hourly):
    repo,_=hourly
    response=repo.get_dashboard(DashboardQuery('daily'))
    response.dashboard_trend_records[0].metric_sample_counts['pm25']=999
    assert repo.get_dashboard(DashboardQuery('daily')).dashboard_trend_records[0].metric_sample_counts['pm25']==24


def test_quality_reason_dictionary_is_not_a_numeric_analytics_metric():
    from app.services.analytics import AnalyticsQuery
    with pytest.raises(ValueError):AnalyticsQuery(metric='metricQualityReasons')
