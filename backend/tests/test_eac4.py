import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import numpy as np
import pyarrow.parquet as pq
import pytest
from shapely.geometry import Polygon, box, mapping

from app.core.config import Settings
from app.etl.eac4 import build
import eccodes as ec
from app.etl.metrics import resolve_metric
from app.etl.spatial import Province, aggregate, build_weights, equal_area, load_provinces
from app.main import create_app
from app.repositories.base import DataSourceUnavailable
from app.repositories.parquet.dashboard import ParquetDashboardRepository


def province(geometry):
    return Province("01", "Test", geometry, 0, 0, equal_area(geometry).area)


def test_fractional_overlap_and_missing_cells():
    # Same latitude range: 75% of the province in the left cell, 25% in right.
    weights, table = build_weights([province(box(-0.25, -0.5, 0.75, 0.5))], [0, 0], [0, 1], 1, 1)
    assert weights[0] == pytest.approx([0.75, 0.25])
    assert sum(table['province_percent'].to_pylist()) == pytest.approx(100)
    values, coverage, counts = aggregate(np.array([[10., 30.], [10., np.nan], [np.nan, np.nan]]), weights)
    assert values[0, 0] == pytest.approx(15)
    assert np.isnan(values[1:, 0]).all()
    assert coverage[:, 0] == pytest.approx([1, .75, 0])
    assert counts[:, 0].tolist() == [2, 1, 0]
    relaxed, _, _ = aggregate(np.array([[10., np.nan]]), weights, .7)
    assert relaxed[0, 0] == pytest.approx(10)  # Renormalize valid area, never fill missing with zero.


def test_holes_and_partial_grid_coverage():
    outer = box(-.5, -.5, 1.5, .5)
    hole = box(.1, -.1, .3, .1)
    geometry = Polygon(outer.exterior.coords, [hole.exterior.coords])
    weights, _ = build_weights([province(geometry)], [0, 0], [0, 1], 1, 1)
    assert weights.sum() == pytest.approx(1)
    assert weights[0, 0] < weights[0, 1]
    partial, _ = build_weights([province(box(-.5, -.5, 2.5, .5))], [0, 0], [0, 1], 1, 1)
    assert partial.sum() == pytest.approx(2 / 3)
    assert np.isnan(aggregate(np.ones((1, 2)), partial)[0]).all()


def test_area_is_not_square_degrees_and_preserves_cell_order():
    geometry = box(-.5, 59.5, .5, 61.5)
    weights, _ = build_weights([province(geometry)], [61, 60], [0, 0], 1, 1)
    assert weights[0, 0] < weights[0, 1]  # Northern cell has less area.
    assert weights.sum() == pytest.approx(1)


@pytest.mark.parametrize(('param', 'unit', 'raw', 'expected'), [
    (210073, 'kg m**-3', 2e-8, 20), (167, 'K', 300, 26.85),
    (134, 'Pa', 101325, 1013.25), (210125, 'kg m**-2', .0001, 100),
    (210206, 'kg m**-2', .005, 5000), (210207, '~', .3, .3),
    (165, 'm s**-1', -4, -4),
])
def test_unit_conversions(param, unit, raw, expected):
    metric = resolve_metric(param, unit)
    assert raw * metric.scale + metric.offset == pytest.approx(expected)
    if 'column' in metric.name:
        assert metric.unit == 'mg/m²'
        assert metric.quantity == 'total_column_mass'


def test_unknown_parameters_or_incompatible_units_fail():
    with pytest.raises(ValueError, match='Unexpected unit'):
        resolve_metric(210073, 'kg m**-2')
    with pytest.raises(ValueError, match='Unsupported'):
        resolve_metric(999999, 'K')


def write_grib(path, param_id, values, *, count=248, duplicate=False, conflict=False):
    with path.open('wb') as stream:
        for i in range(count):
            handle = ec.codes_grib_new_from_samples('regular_ll_sfc_grib1')
            try:
                for key, value in dict(Ni=2, Nj=2, latitudeOfFirstGridPointInDegrees=1,
                                       latitudeOfLastGridPointInDegrees=0,
                                       longitudeOfFirstGridPointInDegrees=0,
                                       longitudeOfLastGridPointInDegrees=1,
                                       iDirectionIncrementInDegrees=1, jDirectionIncrementInDegrees=1,
                                       paramId=param_id).items():
                    ec.codes_set(handle, key, value)
                time = datetime(2024, 1, 1) + timedelta(hours=3 * (0 if duplicate else i))
                ec.codes_set(handle, 'dataDate', int(time.strftime('%Y%m%d')))
                ec.codes_set(handle, 'dataTime', time.hour * 100)
                ec.codes_set_values(handle, np.asarray(values) * (2 if conflict and i else 1))
                ec.codes_write(handle, stream)
            finally:
                ec.codes_release(handle)


@pytest.fixture
def dataset(tmp_path):
    inputs = tmp_path / 'input'
    inputs.mkdir()
    boundaries = tmp_path / 'provinces.geojson'
    boundaries.write_text(json.dumps(dict(type='FeatureCollection', features=[
        dict(type='Feature', properties=dict(code='01', name='Test'),
             geometry=mapping(box(-.25, -.5, .75, 1.5))),
    ])))
    # Deliberately use filenames that do not name the parameter.
    write_grib(inputs / 'a.grib', 210073, [1e-8, 3e-8, 1e-8, 3e-8])
    write_grib(inputs / 'b.grib', 210074, [2e-8, 6e-8, 2e-8, 6e-8])
    write_grib(inputs / 'c.grib', 210125, [1e-4, 3e-4, 1e-4, 3e-4])
    write_grib(inputs / 'd.grib', 210072, [5e-9, 15e-9, 5e-9, 15e-9])
    output = tmp_path / 'output'
    manifest = build(inputs, boundaries, output)
    return inputs, boundaries, output, manifest


def test_real_grib_to_parquet_to_repository(dataset):
    _, _, output, manifest = dataset
    run = output / 'runs' / manifest['generation']
    raw_file = next((run / 'observations/pm25').rglob('*.parquet'))
    table = pq.ParquetFile(raw_file).read()
    assert table.num_rows == 248
    assert table.schema.field('timestamp').type.tz == 'UTC'
    assert table['value'][0].as_py() == pytest.approx(15, rel=1e-5)
    assert table['timestamp'][-1].as_py() == datetime(2024, 1, 31, 21, tzinfo=timezone.utc)
    assert table['province_code'][0].as_py() == '01'
    metadata = json.loads(table.schema.metadata[b'provenance'])
    assert metadata['param_id'] == 210073
    assert metadata['source_unit'] == 'kg m**-3'
    repository = ParquetDashboardRepository(output)
    data = repository.get_dashboard()
    assert data.province_snapshots[0].pm25 == pytest.approx(15, rel=1e-5)
    assert data.province_snapshots[0].pm10 == pytest.approx(30, rel=1e-5)
    assert data.province_snapshots[0].pm1 == pytest.approx(7.5, rel=1e-5)
    assert data.metadata.metrics['pm1'].map_scale.breakpoints == [25, 50, 100]
    assert data.metadata.metrics['pm1'].map_scale.sample_count == 1
    assert data.province_snapshots[0].aqi is None
    assert data.emission_records == []
    assert data.dashboard_trend_records[0].no2 is None
    assert data.dashboard_trend_records[0].no2_column == pytest.approx(150, rel=1e-5)
    assert data.metadata.metrics['no2Column'].unit == 'mg/m²'
    data.province_snapshots.clear()
    assert len(repository.get_dashboard().province_snapshots) == 1


@pytest.mark.anyio
async def test_parquet_api_and_missing_source(dataset, tmp_path):
    _, _, output, _ = dataset
    app = create_app(Settings(dashboard_parquet_path=output))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
        response = await client.get('/api/dashboard')
        assert response.status_code == 200
        assert response.json()['provinceSnapshots'][0]['pm1'] == pytest.approx(7.5, rel=1e-5)
        assert response.json()['metadata']['metrics']['pm1']['mapScale']['breakpoints'] == [25, 50, 100]
        assert response.json()['dashboardTrendRecords'][0]['no2Column'] == pytest.approx(150, rel=1e-5)
        assert response.json()['metadata']['metrics']['no2Column']['unit'] == 'mg/m²'
    app = create_app(Settings(dashboard_parquet_path=tmp_path / 'missing'))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
        assert (await client.get('/api/dashboard')).status_code == 503


def test_failed_rebuild_does_not_replace_published_data(dataset):
    inputs, boundaries, output, manifest = dataset
    write_grib(inputs / 'a.grib', 210073, [1e-8] * 4, count=2, duplicate=True, conflict=True)
    with pytest.raises(ValueError, match='Conflicting duplicate'):
        build(inputs, boundaries, output)
    assert (output / 'CURRENT').read_text().strip() == manifest['generation']
    assert ParquetDashboardRepository(output).get_dashboard().province_snapshots


def test_repository_refreshes_on_new_generation(dataset):
    inputs, boundaries, output, _ = dataset
    repository = ParquetDashboardRepository(output)
    assert repository.get_dashboard().province_snapshots[0].pm25 == pytest.approx(15, rel=1e-5)
    write_grib(inputs / 'a.grib', 210073, [4e-8] * 4)
    build(inputs, boundaries, output)
    assert repository.get_dashboard().province_snapshots[0].pm25 == pytest.approx(40, rel=1e-5)
    (output / 'CURRENT').write_text('../invalid')
    with pytest.raises(DataSourceUnavailable):
        repository.get_dashboard()


def test_reject_duplicate_boundary_codes(tmp_path):
    feature = dict(type='Feature', properties=dict(code='01', name='Test'), geometry=mapping(box(0, 0, 1, 1)))
    path = tmp_path / 'boundaries.json'
    path.write_text(json.dumps(dict(type='FeatureCollection', features=[feature, feature])))
    with pytest.raises(ValueError, match='Duplicate province'):
        load_provinces(path)


def test_identical_duplicates_are_deduplicated_and_audited(dataset):
    inputs, boundaries, output, _ = dataset
    write_grib(inputs / 'a.grib', 210073, [1e-8] * 4, count=2, duplicate=True)
    manifest = build(inputs, boundaries, output)
    source = next(s for s in manifest['sources'] if s['name'] == 'pm25')
    assert source['messages'] == 1
    assert source['duplicate_messages_skipped'] == 1
    data = ParquetDashboardRepository(output).get_dashboard()
    assert data.dashboard_trend_records[0].pm25 is None  # Incomplete month is not a full-month estimate.


def test_meteorological_identifiers_keep_their_grib_spelling_in_json():
    from app.schemas.dashboard import DashboardTrendRecord
    record = DashboardTrendRecord(province_code='01', date='2024-01-01',
                                  pm25=None, pm10=None, o3=None, no2=None, so2=None, co=None,
                                  t2m=26.85, d2m=20)
    body = record.model_dump(by_alias=True, exclude_unset=True)
    assert body['t2m'] == 26.85
    assert body['d2m'] == 20
    assert 't2M' not in body and 'd2M' not in body


@pytest.mark.anyio
@pytest.mark.parametrize(("column", "value"), [
    ("value", float("nan")),
    ("value", float("inf")),
    ("temporal_coverage_fraction", float("nan")),
    ("temporal_coverage_fraction", 1.5),
    ("province_code", "unknown"),
    ("timestamp", "2024-01-01"),
])
async def test_invalid_monthly_data_returns_503(dataset, column, value):
    import pyarrow as pa

    _, _, output, manifest = dataset
    path = output / "runs" / manifest["generation"] / "monthly/pm25.parquet"
    rows = pq.read_table(path).to_pylist()
    rows[0][column] = value
    pq.write_table(pa.Table.from_pylist(rows), path)
    application = create_app(Settings(dashboard_parquet_path=output))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=application), base_url="http://test") as client:
        response = await client.get("/api/dashboard")
    assert response.status_code == 503
    assert response.json() == {"detail": "Dashboard data source is temporarily unavailable."}


def test_reject_empty_boundary_collection(tmp_path):
    path = tmp_path / "boundaries.json"
    path.write_text(json.dumps({"type": "FeatureCollection", "features": []}))
    with pytest.raises(ValueError, match="No province features"):
        load_provinces(path)
