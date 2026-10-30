"""Export map boundaries with the same region identities used by EAC4 ETL."""
import json
from app.etl.eac4 import DEFAULT_BOUNDARIES, ROOT
from app.etl.regions import region_features
from app.etl.spatial import equal_area
from shapely.geometry import shape


def export():
    # Separate paths improve island tooltips; their parent is the administrative
    # province used by the ETL, API, selectors and province counts.
    features = list(region_features(DEFAULT_BOUNDARIES, split_archipelagos=True))
    for feature in features:
        feature["id"] = str(feature["properties"]["code"]).zfill(2)
        feature["properties"]["areaKm2"] = equal_area(shape(feature["geometry"])).area / 1e6
    target = ROOT / "frontend/public/data/vietnam-provinces.geojson"
    target.write_text(json.dumps(dict(type="FeatureCollection", features=features),
                                 ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


if __name__ == "__main__":
    export()
