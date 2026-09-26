"""Fractional province/cell overlap in an equal-area CRS, retaining GRIB order."""
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pyarrow as pa
from pyproj import Transformer
from shapely import make_valid, segmentize
from shapely.geometry import box, shape
from shapely.ops import transform

AREA_CRS = "EPSG:6933"
PROJECT = Transformer.from_crs("EPSG:4326", AREA_CRS, always_xy=True).transform


@dataclass
class Province:
    code: str
    name: str
    geometry: object
    lat: float
    lon: float
    area_m2: float


def equal_area(geometry):
    # Densify before projection so curved projected edges are represented well.
    return transform(PROJECT, segmentize(geometry, 0.025))


def load_provinces(path: Path) -> tuple[list[Province], str]:
    files = sorted(path.glob("*/*.geojson")) if path.is_dir() else [path]
    if not files:
        raise ValueError(f"No province GeoJSON files in {path}")
    provinces, digest = [], hashlib.sha256()
    for file in files:
        content = file.read_bytes()
        digest.update(content)
        for feature in json.loads(content)["features"]:
            props = feature["properties"]
            geometry = make_valid(shape(feature["geometry"]))
            if geometry.is_empty or geometry.geom_type not in ("Polygon", "MultiPolygon"):
                raise ValueError(f"Invalid polygon for province {props['code']}")
            point = geometry.representative_point()
            provinces.append(Province(str(props["code"]).zfill(2), props["name"], geometry,
                                      point.y, point.x, equal_area(geometry).area))
    if not provinces:
        raise ValueError("No province features in boundary data")
    provinces.sort(key=lambda p: p.code)
    if len({p.code for p in provinces}) != len(provinces):
        raise ValueError("Duplicate province codes")
    return provinces, digest.hexdigest()


def build_weights(provinces, latitudes, longitudes, di, dj):
    latitudes, longitudes = np.asarray(latitudes), np.asarray(longitudes)
    if di <= 0 or dj <= 0 or len(latitudes) != len(longitudes):
        raise ValueError("Invalid regular latitude/longitude grid")
    if len(set(zip(latitudes, longitudes))) != len(latitudes):
        raise ValueError("Duplicate grid centres")
    for coordinates, spacing in ((latitudes, dj), (longitudes, di)):
        diffs = np.diff(np.unique(coordinates))
        if len(diffs) and not np.allclose(diffs, spacing):
            raise ValueError("Grid is not regularly spaced")
    if len(np.unique(latitudes)) * len(np.unique(longitudes)) != len(latitudes):
        raise ValueError("Incomplete rectangular grid")
    weights = np.zeros((len(provinces), len(latitudes)), dtype=np.float64)
    rows = []
    for index, (lat, lon) in enumerate(zip(latitudes, longitudes)):
        cell = box(lon - di / 2, max(-90, lat - dj / 2), lon + di / 2, min(90, lat + dj / 2))
        for pindex, province in enumerate(provinces):
            if not province.geometry.intersects(cell):
                continue
            intersection = province.geometry.intersection(cell)
            area = equal_area(intersection).area
            if area <= 0:
                continue
            fraction = area / province.area_m2
            weights[pindex, index] = fraction
            rows.append(dict(province_code=province.code, province_name=province.name,
                             cell_index=index, lat=float(lat), lon=float(lon),
                             lat_min=cell.bounds[1], lat_max=cell.bounds[3],
                             lon_min=cell.bounds[0], lon_max=cell.bounds[2],
                             intersection_area_m2=area, province_area_m2=province.area_m2,
                             province_fraction=fraction, province_percent=100 * fraction))
    coverage = weights.sum(axis=1)
    for row in rows:
        pi = next(i for i, p in enumerate(provinces) if p.code == row["province_code"])
        row["weight"] = row["province_fraction"] / coverage[pi]
        row["grid_coverage_fraction"] = float(coverage[pi])
    if np.any(coverage > 1.0001):
        raise ValueError("Overlapping grid cells exceed province area")
    return weights, pa.Table.from_pylist(rows)


def aggregate(values, weights, minimum_coverage=0.95):
    """values: [time, cell]; return means, valid province fractions, cell counts."""
    valid = np.isfinite(values)
    coverage = valid.astype(float) @ weights.T
    numerator = np.where(valid, values, 0.0) @ weights.T
    means = np.divide(numerator, coverage, out=np.full_like(numerator, np.nan), where=coverage > 0)
    means[coverage < minimum_coverage] = np.nan
    counts = valid.astype(np.int32) @ (weights > 0).T.astype(np.int32)
    return means, coverage, counts
