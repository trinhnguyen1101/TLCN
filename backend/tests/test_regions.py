import json

import numpy as np
import pytest
from shapely.geometry import shape

from app.etl.eac4 import DEFAULT_BOUNDARIES, ROOT
from app.etl.regions import ISLAND_REGIONS, region_features
from app.etl.spatial import aggregate, build_weights, load_provinces


def test_regions_partition_original_boundaries_and_match_map():
    features = {f["properties"]["code"]: f for f in region_features(DEFAULT_BOUNDARIES)}
    map_features = {f["id"]: f for f in json.loads(
        (ROOT / "frontend/public/data/vietnam-provinces.geojson").read_text(encoding="utf-8")
    )["features"]}
    assert len(features) == len(map_features) == 36
    assert features["48"]["properties"]["name"] == "Đà Nẵng"
    assert features["56"]["properties"]["name"] == "Khánh Hoà"
    assert features["20333"]["properties"]["fullName"] == "Quần đảo Hoàng Sa (Đà Nẵng, Việt Nam)"
    assert features["22736"]["properties"]["fullName"] == "Quần đảo Trường Sa (Khánh Hoà, Việt Nam)"
    for code, ward in ISLAND_REGIONS.items():
        original_file = next(DEFAULT_BOUNDARIES.glob(f"{code}*/*.geojson"))
        original = shape(json.loads(original_file.read_text(encoding="utf-8"))["features"][0]["geometry"])
        mainland = shape(features[code]["geometry"])
        island_code = ward.split("_")[0]
        island = shape(features[island_code]["geometry"])
        assert mainland.intersection(island).area == 0
        assert mainland.union(island).symmetric_difference(original).area < 1e-10
        for region_code in (code, island_code):
            assert shape(map_features[region_code]["geometry"]).equals(shape(features[region_code]["geometry"]))
            assert map_features[region_code]["properties"]["fullName"] == features[region_code]["properties"]["fullName"]


def test_mainland_and_archipelagos_aggregate_independently():
    provinces, _ = load_provinces(DEFAULT_BOUNDARIES)
    selected = [p for p in provinces if p.code in ("48", "56", "20333", "22736")]
    lat, lon = np.meshgrid(np.arange(6., 19.), np.arange(106., 120.), indexing="ij")
    weights, _ = build_weights(selected, lat.ravel(), lon.ravel(), 1, 1)
    # Distinct cell values let this catch accidental parent-weight reuse.
    means, coverage, _ = aggregate((lat * 100 + lon).reshape(1, -1), weights)
    assert coverage[0] == pytest.approx(np.ones(4), abs=1e-5)
    assert np.isfinite(means).all()
    values = dict(zip([p.code for p in selected], means[0]))
    assert values["48"] != pytest.approx(values["20333"])
    assert values["56"] != pytest.approx(values["22736"])
