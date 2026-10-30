"""Real GRIB fields: independent density/area reference and missing-input behavior."""
from pathlib import Path
import json
import numpy as np
import pyarrow.parquet as pq
import pytest
from app.etl.eac4 import build, DEFAULT_INPUT, DEFAULT_BOUNDARIES
from app.repositories.parquet.dashboard import ParquetDashboardRepository
from app.services.temporal import DashboardQuery
import eccodes as ec


def subset(source, output, count=24):
    values=[]
    with source.open('rb') as stream, output.open('wb') as dest:
        for _ in range(count):
            h=ec.codes_grib_new_from_file(stream)
            try:
                dest.write(ec.codes_get_message(h))
                values.append(ec.codes_get_values(h))
            finally:
                ec.codes_release(h)
    return np.asarray(values)


def test_real_gas_density_before_province_aggregation(tmp_path):
    if not DEFAULT_INPUT.exists():pytest.skip('Local hourly GRIB not installed')
    inputs=tmp_path/'inputs';inputs.mkdir()
    raw={}
    for name in ['co','no2','so2','o3','t_model','q_model','sp','pm2p5']:
        p=DEFAULT_INPUT/f'{name}_2003_2025_vietnam.grib'
        raw[name]=subset(p,inputs/p.name)
    output=tmp_path/'parquet'
    result=build(inputs,DEFAULT_BOUNDARIES,output)
    folder=output/'runs'/result['generation']
    weight_files=list((folder/'weights').glob('*.parquet'))
    rows=pq.read_table(weight_files[0]).to_pylist()
    weights=np.zeros(575)
    for row in rows:
        if row['province_code']=='01':weights[row['cell_index']]=row['province_fraction']
    # Reference arithmetic is intentionally independent of the conversion helper.
    pressure=raw['sp']*(1+.9976301193237305)/2
    density=pressure/(raw['t_model']*((1-raw['q_model'])*287.05+raw['q_model']*461.5))
    data=ParquetDashboardRepository(output).get_dashboard(DashboardQuery('hourly'))
    selected=[r for r in data.dashboard_trend_records if r.province_code=='01']
    assert len(selected)==24
    for name,scale in [('co',1e6),('no2',1e9),('so2',1e9),('o3',1e9)]:
        expected=(raw[name]*density*scale@weights)/weights.sum()
        np.testing.assert_allclose([getattr(row,name) for row in selected],expected,rtol=1e-12,atol=1e-10)
        source=next(s for s in result['sources'] if s['name']==name)
        assert source['mmr_mass_basis']=='moist_air'
        assert source['source_level']==60
        assert source['conversion_dependencies']['sp']['sha256']
    assert data.metadata.metrics['co'].unit=='mg/m³'
    assert data.metadata.metrics['no2'].unit=='µg/m³'
    assert data.metadata.metrics['co'].conversion_method=='eac4-l60-moist-density-v1'
    assert all(r.aqi is None for r in data.province_snapshots)


def test_missing_q_file_produces_nulls_and_explicit_reason(tmp_path):
    if not DEFAULT_INPUT.exists():pytest.skip('Local hourly GRIB not installed')
    inputs=tmp_path/'inputs';inputs.mkdir()
    for name in ['co','t_model','sp']:
        p=DEFAULT_INPUT/f'{name}_2003_2025_vietnam.grib';subset(p,inputs/p.name,3)
    output=tmp_path/'parquet'
    manifest=build(inputs,DEFAULT_BOUNDARIES,output)
    source=next(s for s in manifest['sources'] if s['name']=='co')
    assert source['quality_status']=='unavailable'
    folder=output/'runs'/manifest['generation']
    table=pq.read_table(folder/'observations/co/2003/part-00000.parquet')
    assert table['value'].null_count==table.num_rows
    assert all('missing_model_specific_humidity' in value for value in table['quality_reason'].to_pylist())
