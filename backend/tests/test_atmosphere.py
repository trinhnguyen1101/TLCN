"""Independent numerical reference cases; no fixed density in production."""
from decimal import Decimal
import numpy as np
import pytest
from app.etl.atmosphere import (HybridCoordinate,L60_REFERENCE,moist_air_density,gas_concentration,
    reason_text,R_D,R_V,MMR_BASIS)
from app.etl.metrics import resolve_metric,convert_direct
from app.etl.spatial import aggregate


def test_density_and_virtual_temperature_equivalence():
    p,t,q=95000.,300.,.01
    rho,flags=moist_air_density(p,t,q)
    reference=float(Decimal(95000)/((Decimal('.99')*Decimal('287.05')+Decimal('.01')*Decimal('461.5'))*Decimal(300)))
    assert float(rho)==pytest.approx(reference,rel=1e-14)
    assert float(rho)==pytest.approx(1.0965121103991477)
    assert int(flags)==0
    virtual=t*(1+(R_V/R_D-1)*q)
    assert float(rho)==pytest.approx(p/(R_D*virtual),rel=1e-14)


def test_gases_moist_and_dry_basis_units():
    rho,_=moist_air_density([95000],[300],[.01])
    ug,_=gas_concentration([1e-7],rho,[.01],basis='moist_air',target_unit='µg/m³')
    co,_=gas_concentration([1e-7],rho,[.01],basis='moist_air',target_unit='mg/m³')
    dry,_=gas_concentration([1e-7],rho,[.01],basis='dry_air',target_unit='µg/m³')
    assert ug[0]==pytest.approx(109.65121103991477)
    assert co[0]==pytest.approx(.10965121103991477)
    assert dry[0]==pytest.approx(108.55469892951563)
    assert MMR_BASIS=='moist_air'


def test_pm_and_columns_never_use_density():
    assert convert_direct(resolve_metric(210073,'kg m**-3'),np.array([2.5e-8]))[0]==25
    assert convert_direct(resolve_metric(210125,'kg m**-2'),np.array([2.5e-6]))[0]==2.5
    with pytest.raises(ValueError,match='density'):
        convert_direct(resolve_metric(210121,'kg kg**-1'),np.array([1e-7]))


def test_l60_pressure_indexing_embedded_pv_and_encoding_transition():
    for pv in L60_REFERENCE['pv_variants']:
        coordinate=HybridCoordinate(pv,60)
        pressure,above,below=coordinate.pressure(np.array([101325.,95000.]))
        # Independent documented L60 B59/B60; no surface-pressure substitution.
        np.testing.assert_allclose(above,np.array([101325,95000])*.9976301193237305,rtol=0,atol=1e-10)
        np.testing.assert_allclose(below,[101325,95000],rtol=0,atol=1e-10)
        np.testing.assert_allclose(pressure,[101204.9359202385,94887.4306678772],atol=1e-7,rtol=0)
        assert np.all(pressure<below)
    with pytest.raises(ValueError):HybridCoordinate(np.zeros(276),60) # not ERA5 L137
    with pytest.raises(ValueError):HybridCoordinate([],60)


def test_missing_and_invalid_inputs_preserve_reasons():
    for p,t,q,reason in [(95000,np.nan,.01,'missing_model_temperature'),(95000,300,np.nan,'missing_model_specific_humidity'),(np.nan,300,.01,'missing_model_pressure'),(95000,0,.01,'invalid_model_temperature'),(95000,300,-.1,'invalid_model_specific_humidity')]:
        rho,flags=moist_air_density([p],[t],[q])
        concentration,flags=gas_concentration([1e-7],rho,[q],basis='moist_air',target_unit='µg/m³',flags=flags)
        assert np.isnan(concentration[0])
        assert reason in reason_text(flags[0])
    concentration,flags=gas_concentration([-1e-7],[1.1],[.01],basis='moist_air',target_unit='µg/m³')
    assert np.isnan(concentration[0]) and 'negative_gas' in reason_text(flags[0])


def test_grid_conversion_precedes_area_aggregation():
    mmr=np.array([1e-7,3e-7]);rho=np.array([1.,2.]);weights=np.array([[.25,.75]])
    converted,_=gas_concentration(mmr,rho,[0.,0.],basis='moist_air',target_unit='µg/m³')
    means,_,_=aggregate(converted[None,:],weights)
    assert means[0,0]==pytest.approx(475.)
    assert means[0,0]!=pytest.approx(np.average(mmr,weights=weights[0])*np.average(rho,weights=weights[0])*1e9)


def test_dimensional_integrity_and_no_co2():
    for param,unit in [(210073,'kg m**-2'),(210123,'kg m**-3'),(134,'hPa'),(130,'°C')]:
        with pytest.raises(ValueError):resolve_metric(param,unit)
    with pytest.raises(ValueError):HybridCoordinate(L60_REFERENCE['pv'],60).pressure([1000],unit='hPa')
    with pytest.raises(ValueError):HybridCoordinate(L60_REFERENCE['pv'],60).pressure([100000],param_id=151)
    with pytest.raises(ValueError):moist_air_density([95000],[27],[.01],temperature_unit='°C')
    with pytest.raises(ValueError):gas_concentration([1e-7],[1.1],[.01],basis='unknown',target_unit='µg/m³')
    assert resolve_metric(210123,'kg kg**-1').name=='co'
    with pytest.raises(ValueError):resolve_metric(210061,'kg kg**-1')
