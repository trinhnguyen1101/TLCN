"""Run with python -m app.etl.eac4; publish complete, immutable Parquet generations."""
import argparse
import calendar
from datetime import datetime, timezone
import hashlib
import json
import logging
from pathlib import Path
import uuid

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from app.core.config import DEFAULT_PARQUET_PATH
from app.etl.metrics import resolve_metric
# Load PROJ before ecCodes: their bundled native libraries otherwise conflict at shutdown.
from app.etl.spatial import AREA_CRS, aggregate, build_weights, load_provinces
import eccodes as ec

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_INPUT = ROOT / "data/landing/CAMS/EAC4"
DEFAULT_BOUNDARIES = ROOT / "data/landing/reference/vietnamese-provinces-database/json/geojson"
DEFAULT_OUTPUT = DEFAULT_PARQUET_PATH
LOG = logging.getLogger(__name__)


def sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def grid_identity(handle):
    if ec.codes_get(handle, "gridType") != "regular_ll":
        raise ValueError("Only regular latitude/longitude GRIB grids are supported")
    return ec.codes_get(handle, "md5GridSection")


def inspect(handle):
    param_id = ec.codes_get(handle, "paramId")
    metric = resolve_metric(param_id, ec.codes_get(handle, "units"))
    if (ec.codes_get(handle, "typeOfLevel") != "surface"
            or ec.codes_get(handle, "level") != 0
            or ec.codes_get(handle, "stepType") != "instant"
            or ec.codes_get(handle, "dataType") != "an"):
        raise ValueError("Expected instantaneous surface/column analysis fields")
    return param_id, metric


def process_file(path, output, provinces, grids, minimum_coverage, boundary_hash, seen_metrics):
    times, values, monthly = [], [], {}
    writer = None
    writer_year = None
    previous = None
    first = None
    message_count = 0
    duplicate_count = 0
    fingerprints = {}
    row_count = 0
    source_hash = sha256(path)
    metadata = None

    def flush():
        nonlocal writer, writer_year, row_count
        if not times:
            return
        means, coverage, counts = aggregate(np.asarray(values), weights, minimum_coverage)
        means = means * metric.scale + metric.offset
        nprovince = len(provinces)
        for month in sorted({(t.year, t.month) for t in times}):
            indices = [i for i, t in enumerate(times) if (t.year, t.month) == month]
            vals = means[indices]
            state = monthly.setdefault(month, [np.zeros(nprovince), np.zeros(nprovince, dtype=int),
                                               np.ones(nprovince), 0])
            state[0] += np.nansum(vals, axis=0)
            state[1] += np.isfinite(vals).sum(axis=0)
            state[2] = np.minimum(state[2], coverage[indices].min(axis=0))
            state[3] += len(indices)
        for year in sorted({t.year for t in times}):
            indices = [i for i, t in enumerate(times) if t.year == year]
            n = len(indices)
            flat = means[indices].ravel()
            quality = np.where(np.isfinite(flat), "ok", "insufficient_coverage")
            table = pa.table({
                "timestamp": pa.array([times[i] for i in indices for _ in provinces], type=pa.timestamp("us", tz="UTC")),
                "province_code": [p.code for _ in indices for p in provinces],
                "province_name": [p.name for _ in indices for p in provinces],
                "lat": np.tile([p.lat for p in provinces], n),
                "lon": np.tile([p.lon for p in provinces], n),
                "metric": [metric.name] * (n * nprovince),
                "value": pa.array(flat, mask=~np.isfinite(flat)),
                "unit": [metric.unit] * (n * nprovince),
                "valid_area_fraction": coverage[indices].ravel(),
                "grid_coverage_fraction": np.tile(weights.sum(axis=1), n),
                "valid_cell_count": counts[indices].ravel(),
                "quality_flag": quality,
                "grid_id": [grid_id] * (n * nprovince),
                "source_file": [path.name] * (n * nprovince),
            }).replace_schema_metadata({b"provenance": json.dumps(metadata, ensure_ascii=False).encode()})
            if writer_year != year:
                if writer:
                    writer.close()
                folder = output / "observations" / metric.name / str(year)
                folder.mkdir(parents=True, exist_ok=True)
                writer = pq.ParquetWriter(folder / "part-00000.parquet", table.schema, compression="zstd")
                writer_year = year
            writer.write_table(table)
            row_count += table.num_rows
        times.clear()
        values.clear()

    try:
        with path.open("rb") as stream:
            while (handle := ec.codes_grib_new_from_file(stream)) is not None:
                try:
                    param_id, current_metric = inspect(handle)
                    current_grid = grid_identity(handle)
                    if metadata is None:
                        metric, grid_id = current_metric, current_grid
                        if metric.name in seen_metrics:
                            raise ValueError(f"Multiple files for {metric.name}; merge source files first")
                        seen_metrics.add(metric.name)
                        if grid_id not in grids:
                            latitudes = ec.codes_get_array(handle, "latitudes")
                            longitudes = ec.codes_get_array(handle, "longitudes")
                            di = ec.codes_get(handle, "iDirectionIncrementInDegrees")
                            dj = ec.codes_get(handle, "jDirectionIncrementInDegrees")
                            weights, weight_table = build_weights(provinces, latitudes, longitudes, di, dj)
                            grids[grid_id] = weights
                            folder = output / "weights"
                            folder.mkdir(exist_ok=True)
                            pq.write_table(weight_table.replace_schema_metadata({
                                b"area_crs": AREA_CRS.encode(), b"boundary_sha256": boundary_hash.encode(),
                                b"grid_id": grid_id.encode(),
                            }), folder / f"{grid_id}.parquet", compression="zstd")
                        weights = grids[grid_id]
                        metadata = dict(source="CAMS EAC4", source_file=path.name, source_sha256=source_hash,
                                        param_id=param_id, short_name=ec.codes_get(handle, "shortName"),
                                        boundary_sha256=boundary_hash, grid_id=grid_id,
                                        area_crs=AREA_CRS, minimum_coverage=minimum_coverage,
                                        temporal_resolution="3 hours", timestamp_timezone="UTC",
                                        coordinate_meaning="province_representative_point", **metric.metadata())
                        LOG.info("Processing %s (%s)", path.name, metric.name)
                    if current_grid != grid_id or current_metric != metric:
                        raise ValueError(f"Grid or parameter changed within {path.name}")
                    date = ec.codes_get(handle, "validityDate")
                    time = ec.codes_get(handle, "validityTime")
                    timestamp = datetime.strptime(f"{date:08d}{time:04d}", "%Y%m%d%H%M").replace(tzinfo=timezone.utc)
                    if timestamp.minute or timestamp.hour % 3:
                        raise ValueError("Expected timestamps on a 3-hour UTC grid")
                    array = ec.codes_get_values(handle)
                    if len(array) != weights.shape[1]:
                        raise ValueError("Value count differs from grid")
                    if ec.codes_get(handle, "bitmapPresent"):
                        array[np.asarray(ec.codes_get_array(handle, "bitmap")) == 0] = np.nan
                    array[~np.isfinite(array)] = np.nan
                    fingerprint = hashlib.sha256(array.tobytes()).digest()
                    if timestamp in fingerprints:
                        if fingerprints[timestamp] != fingerprint:
                            raise ValueError(f"Conflicting duplicate timestamp in {path.name}: {timestamp}")
                        duplicate_count += 1
                        continue
                    if previous and timestamp < previous:
                        raise ValueError(f"Unordered unique timestamp in {path.name}: {timestamp}")
                    fingerprints[timestamp] = fingerprint
                    if first is None:
                        first = timestamp
                    previous = timestamp
                    times.append(timestamp)
                    values.append(array)
                    message_count += 1
                    if len(times) >= 512:
                        flush()
                finally:
                    ec.codes_release(handle)
        flush()
    finally:
        if writer:
            writer.close()
    if metadata is None:
        raise ValueError(f"Empty GRIB file: {path}")
    records = []
    for (year, month), (sums, counts, coverages, samples) in sorted(monthly.items()):
        expected = calendar.monthrange(year, month)[1] * 8
        for i, province in enumerate(provinces):
            records.append(dict(province_code=province.code, province_name=province.name,
                                lat=province.lat, lon=province.lon,
                                timestamp=datetime(year, month, 1, tzinfo=timezone.utc),
                                metric=metric.name, unit=metric.unit,
                                value=float(sums[i] / counts[i]) if counts[i] else None,
                                sample_count=int(counts[i]), source_sample_count=samples,
                                expected_sample_count=expected,
                                temporal_coverage_fraction=float(counts[i] / expected),
                                minimum_valid_area_fraction=float(coverages[i])))
    table = pa.Table.from_pylist(records).replace_schema_metadata({b"provenance": json.dumps(metadata).encode()})
    folder = output / "monthly"
    folder.mkdir(exist_ok=True)
    pq.write_table(table, folder / f"{metric.name}.parquet", compression="zstd")
    LOG.info("Completed %s: %s messages, %s province rows", metric.name, message_count, row_count)
    return dict(**metadata, messages=message_count, duplicate_messages_skipped=duplicate_count, rows=row_count,
                start=first.isoformat(), end=previous.isoformat())


def build(input_dir=DEFAULT_INPUT, boundaries=DEFAULT_BOUNDARIES, output=DEFAULT_OUTPUT, minimum_coverage=0.95):
    if not 0 < minimum_coverage <= 1:
        raise ValueError("minimum_coverage must be in (0, 1]")
    files = sorted(Path(input_dir).glob("*.grib"))
    if not files:
        raise ValueError(f"No GRIB inputs in {input_dir}")
    provinces, boundary_hash = load_provinces(Path(boundaries))
    output = Path(output)
    generation = uuid.uuid4().hex
    staging = output / f".staging-{generation}"
    staging.mkdir(parents=True)
    grids, seen_metrics = {}, set()
    sources = [process_file(p, staging, provinces, grids, minimum_coverage, boundary_hash, seen_metrics)
               for p in files]
    manifest = dict(schema_version=1, generation=generation, source="CAMS EAC4",
                    created_at=datetime.now(timezone.utc).isoformat(),
                    boundary_source=str(Path(boundaries).resolve()), boundary_sha256=boundary_hash,
                    boundary_policy="Current supplied boundaries applied to all historical timestamps",
                    province_count=len(provinces), minimum_coverage=minimum_coverage,
                    area_crs=AREA_CRS, sources=sources,
                    provinces=[dict(code=p.code, name=p.name, lat=p.lat, lon=p.lon, area_m2=p.area_m2)
                               for p in provinces],
                    grid_coverage={key: dict(zip([p.code for p in provinces], weights.sum(axis=1).tolist()))
                                   for key, weights in grids.items()})
    (staging / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    (output / "runs").mkdir(exist_ok=True)
    staging.rename(output / "runs" / generation)
    pointer = output / f".CURRENT-{generation}"
    pointer.write_text(generation + "\n", encoding="ascii")
    pointer.replace(output / "CURRENT")
    LOG.info("Published generation %s, %s rows", generation, sum(s['rows'] for s in sources))
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--boundaries", type=Path, default=DEFAULT_BOUNDARIES)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--minimum-coverage", type=float, default=0.95)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    build(args.input_dir, args.boundaries, args.output_dir, args.minimum_coverage)


if __name__ == "__main__":
    main()
