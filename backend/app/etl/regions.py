"""Split reporting regions using the supplied special-region boundaries."""
import json
from pathlib import Path

from shapely import make_valid
from shapely.geometry import MultiPolygon, mapping, shape

ISLAND_REGIONS = {"48": "20333_hoang_sa", "56": "22736_truong_sa"}
ARCHIPELAGO_NAMES = {
    "20333": ("Quần đảo Hoàng Sa", "Đà Nẵng"),
    "22736": ("Quần đảo Trường Sa", "Khánh Hoà"),
}


def region_features(path: Path):
    files = sorted(path.glob("*/*.geojson")) if path.is_dir() else [path]
    if not files:
        raise ValueError(f"No province GeoJSON files in {path}")
    for file in files:
        for feature in json.loads(file.read_text(encoding="utf-8"))["features"]:
            props = feature["properties"]
            code = str(props["code"]).zfill(2)
            # A single file is an explicit, already prepared boundary collection.
            if not path.is_dir() or code not in ISLAND_REGIONS:
                yield feature
                continue
            ward = file.parent / "wards" / f"{ISLAND_REGIONS[code]}.geojson"
            island = json.loads(ward.read_text(encoding="utf-8"))["features"][0]
            whole = make_valid(shape(feature["geometry"]))
            offshore = make_valid(shape(island["geometry"]))
            if offshore.difference(whole).area > 1e-10:
                raise ValueError(f"Island boundary is outside province {code}")
            mainland = whole.difference(offshore)
            for source, geometry, region_code, kind in (
                (feature, mainland, code, "mainland"),
                (island, offshore, str(island["properties"]["code"]), "archipelago"),
            ):
                if geometry.is_empty:
                    raise ValueError(f"Empty reporting region {region_code}")
                if geometry.geom_type == "Polygon":
                    geometry = MultiPolygon([geometry])
                properties = dict(source["properties"], code=region_code,
                                  parentProvinceCode=code, regionKind=kind)
                if kind == "mainland":
                    properties.update(name=props["name"], fullName=props["fullName"])
                else:
                    name, parent = ARCHIPELAGO_NAMES[region_code]
                    properties.update(name=name, fullName=f"{name} ({parent}, Việt Nam)",
                                      parentProvinceName=parent)
                yield dict(type="Feature", id=region_code, properties=properties,
                           geometry=mapping(geometry))
