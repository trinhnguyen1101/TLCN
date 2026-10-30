"""Administrative identities and lossless split-region migration."""
from pathlib import Path

import numpy as np
import pytest
from shapely.geometry import shape
from shapely.ops import unary_union

from app.etl.province_hierarchy import merge_complete_regions, PARENTS
from app.etl.regions import region_features

BOUNDARIES = Path(__file__).resolve().parents[2] / 'data/landing/reference/vietnamese-provinces-database/json/geojson'


@pytest.mark.skipif(not BOUNDARIES.exists(), reason='Local administrative boundaries not installed')
def test_34_provinces_preserve_archipelago_territories():
    administrative = {str(f['properties']['code']).zfill(2): f for f in region_features(BOUNDARIES)}
    display = list(region_features(BOUNDARIES, split_archipelagos=True))
    assert len(administrative) == 34
    assert len(display) == 36
    assert not set(PARENTS) & administrative.keys()
    assert {f['properties'].get('parentProvinceCode', str(f['properties']['code']).zfill(2)) for f in display} == administrative.keys()
    for child, parent in PARENTS.items():
        parts = [shape(f['geometry']) for f in display if f['properties'].get('parentProvinceCode') == parent]
        assert len(parts) == 2
        assert unary_union(parts).symmetric_difference(shape(administrative[parent]['geometry'])).area < 1e-10
        island = next(f for f in display if str(f['properties']['code']) == child)
        assert island['properties']['parentProvinceCode'] == parent


def test_merge_is_valid_area_weighted_before_temporal_aggregation():
    # Unequal areas must not become an unweighted mean of two regional means.
    values = np.array([[10., 100.], [20., 200.]])
    coverage = np.ones_like(values)
    np.testing.assert_allclose(merge_complete_regions(values, coverage, coverage, np.array([9., 1.])), [19., 38.])


def test_merge_refuses_suppressed_or_incomplete_regional_values():
    with pytest.raises(ValueError, match='rebuild'):
        merge_complete_regions(np.array([[10., np.nan]]), np.ones((1,2)), np.ones((1,2)), np.ones(2))
    with pytest.raises(ValueError, match='rebuild'):
        merge_complete_regions(np.array([[10., 20.]]), np.array([[1., .96]]), np.ones((1,2)), np.ones(2))
