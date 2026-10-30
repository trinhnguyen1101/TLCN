"""Run with python -m app.etl.eac4; publish complete, immutable Parquet generations."""
import argparse
import calendar
from datetime import datetime, timezone
import hashlib
import json
import logging
from pathlib import Path
import uuid
import os
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from app.core.config import DEFAULT_PARQUET_PATH
from app.etl.metrics import resolve_metric, GAS_PARAM_IDS, SUPPORT_PARAMETERS, convert_direct, DISPLAY_NAMES
from app.etl.atmosphere import HybridCoordinate, METHOD_VERSION, MMR_BASIS, MMR_REFERENCE, reason_text
# Load PROJ before ecCodes: their bundled native libraries otherwise conflict at shutdown.
from app.etl.spatial import AREA_CRS, aggregate, build_weights, load_provinces
import eccodes as ec
from app.etl.grib_fields import DensityInputs

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_INPUT = ROOT / "data/landing/CAMS/EAC4_hourly"
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
    is_gas = param_id in GAS_PARAM_IDS
    if (ec.codes_get(handle, "typeOfLevel") != ("hybrid" if is_gas else "surface")
            or ec.codes_get(handle, "level") != (60 if is_gas else 0)
            or ec.codes_get(handle, "stepType") != "instant"
            or ec.codes_get(handle, "dataType") != "an"):
        raise ValueError("Expected instantaneous EAC4 surface fields or gas at hybrid level 60")
    if is_gas:
        HybridCoordinate(ec.codes_get_array(handle, "pv"), ec.codes_get(handle, "level"))
    return param_id, metric


def process_file(path, output, provinces, grids, minimum_coverage, boundary_hash, seen_metrics, cadence_hours=1, temporal_origin="interpolated", support_paths=None):
    times, values, monthly = [], [], {}
    cell_flags = []
    density_inputs = None
    reason_counts = {}
    writer = None
    writer_year = None
    previous = None
    first = None
    message_count = 0
    duplicate_count = 0
    fingerprints = {}
    row_count = 0
    valid_rows = 0
    source_hash = sha256(path)
    metadata = None

    def flush():
        nonlocal writer, writer_year, row_count, valid_rows
        if not times:
            return
        means, coverage, counts = aggregate(np.asarray(values), weights, minimum_coverage)
        # Every grid value is already in its display unit, including density conversion.
        province_flags = np.zeros(means.shape, dtype=np.uint16)
        if cell_flags:
            flags_array = np.asarray(cell_flags)
            for pi in range(len(provinces)):
                province_flags[:, pi] = np.bitwise_or.reduce(flags_array[:, weights[pi] > 0], axis=1, initial=0)
            for flag in np.unique(province_flags):
                if flag:
                    text = reason_text(flag)
                    reason_counts[text] = reason_counts.get(text, 0) + int((province_flags == flag).sum())
        valid_rows += int(np.isfinite(means).sum())
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
                "quality_reason": [reason_text(flag) or ("insufficient_spatial_coverage" if not np.isfinite(value) else "") for flag,value in zip(province_flags[indices].ravel(),flat)],
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
        cell_flags.clear()

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
                        if param_id in GAS_PARAM_IDS:
                            coordinate = HybridCoordinate(ec.codes_get_array(handle, "pv"), ec.codes_get(handle, "level"))
                            density_inputs = DensityInputs(support_paths or {}, grid_id, coordinate, (ec.codes_get_array(handle,"latitudes"),ec.codes_get_array(handle,"longitudes")))
                        metadata = dict(source="CAMS EAC4", source_file=path.name, source_sha256=source_hash,
                                        param_id=param_id, short_name=ec.codes_get(handle, "shortName"),
                                        boundary_sha256=boundary_hash, grid_id=grid_id,
                                        area_crs=AREA_CRS, minimum_coverage=minimum_coverage,
                                        temporal_resolution=f"{cadence_hours} hours", cadence_hours=cadence_hours,
                                        temporal_origin=temporal_origin,
                                        interpolation_method=("linear" if metric.name in {"t2m", "d2m", "sp", "mslp", "u10", "v10"} else "pchip") if temporal_origin == "interpolated" else None,
                                        original_cadence_hours=3 if temporal_origin == "interpolated" else cadence_hours, timestamp_timezone="UTC",
                                        coordinate_meaning="province_representative_point", **metric.metadata())
                        metadata.update(source_param_id=param_id, source_level=ec.codes_get(handle,"level"),
                            source_level_type=ec.codes_get(handle,"typeOfLevel"), metric_id=metric.name,
                            quantity_type=metric.quantity, display_unit=metric.unit, quality_status="validated",
                            source_resolution="3_hourly_analysis" if temporal_origin=="interpolated" else f"{cadence_hours}_hourly",
                            display_resolution=f"{cadence_hours}_hourly",
                            conversion_method=(METHOD_VERSION if density_inputs else "linear_scale_offset"),
                            mmr_mass_basis=MMR_BASIS if density_inputs else None,
                            mmr_definition_reference=MMR_REFERENCE if density_inputs else None,
                            density_assumption="ideal dry air + water vapour; condensed water neglected" if density_inputs else None)
                        if density_inputs:
                            metadata.update(hybrid_pv=coordinate.pv.tolist(), model_level_pressure="0.5*(A[k-1]+B[k-1]*sp+A[k]+B[k]*sp)",
                                conversion_dependencies={key:dict(file=str(value.name),sha256=sha256(value)) for key,value in (support_paths or {}).items()})
                        LOG.info("Processing %s (%s)", path.name, metric.name)
                    if current_grid != grid_id or current_metric != metric:
                        raise ValueError(f"Grid or parameter changed within {path.name}")
                    date = ec.codes_get(handle, "validityDate")
                    time = ec.codes_get(handle, "validityTime")
                    timestamp = datetime.strptime(f"{date:08d}{time:04d}", "%Y%m%d%H%M").replace(tzinfo=timezone.utc)
                    if timestamp.minute or timestamp.hour % cadence_hours:
                        raise ValueError("Timestamp does not match declared UTC cadence")
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
                    if density_inputs:
                        array, flags = density_inputs.convert(timestamp, array, metric.unit, ec.codes_get_array(handle,"pv"))
                    else:
                        array = convert_direct(metric, array)
                        flags = np.zeros(array.shape, np.uint16)
                    times.append(timestamp)
                    values.append(array)
                    cell_flags.append(flags)
                    message_count += 1
                    if len(times) >= 512:
                        flush()
                finally:
                    ec.codes_release(handle)
        flush()
    finally:
        if writer:
            writer.close()
        if density_inputs:
            density_inputs.close()
    if metadata is None:
        raise ValueError(f"Empty GRIB file: {path}")
    records = []
    for (year, month), (sums, counts, coverages, samples) in sorted(monthly.items()):
        expected = calendar.monthrange(year, month)[1] * (24 // cadence_hours)
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
    metadata["quality_status"] = "unavailable" if valid_rows == 0 else "validated_with_missing_inputs" if reason_counts else "validated"
    return dict(**metadata, valid_rows=valid_rows, messages=message_count, duplicate_messages_skipped=duplicate_count, rows=row_count,
                start=first.isoformat(), end=previous.isoformat(), quality_reason_counts=reason_counts)


def build(input_dir=DEFAULT_INPUT, boundaries=DEFAULT_BOUNDARIES, output=DEFAULT_OUTPUT, minimum_coverage=0.95, cadence_hours=1, temporal_origin="interpolated", reuse_generation=None, workers=1):
    if cadence_hours not in (1, 3):
        raise ValueError("cadence_hours must be 1 or 3")
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
    sources, excluded, support_paths, pending = [], [], {}, []
    identities = []
    for p in files:
        with p.open("rb") as stream:
            handle = ec.codes_grib_new_from_file(stream)
            try:
                param_id = ec.codes_get(handle, "paramId")
                if param_id in SUPPORT_PARAMETERS:
                    name,unit = SUPPORT_PARAMETERS[param_id]
                    if ec.codes_get(handle,"units")!=unit or ec.codes_get(handle,"typeOfLevel")!="hybrid" or ec.codes_get(handle,"level")!=60:
                        raise ValueError("Invalid model-level support field")
                    HybridCoordinate(ec.codes_get_array(handle,"pv"),60)
                    if name in support_paths:
                        raise ValueError("Duplicate support parameter")
                    support_paths[name] = p
                else:
                    _,metric = inspect(handle)
                    if metric.name in seen_metrics:
                        raise ValueError("Duplicate source metric")
                    seen_metrics.add(metric.name)
                    if param_id==134:
                        support_paths['sp']=p
                    identities.append((p,param_id,metric))
            finally:
                ec.codes_release(handle)
    reuse = None
    if reuse_generation:
        if not __import__('re').fullmatch(r'[a-f0-9]{32}',reuse_generation):
            raise ValueError("Invalid reuse generation")
        reuse_folder = output / 'runs' / reuse_generation
        reuse = json.loads((reuse_folder/'manifest.json').read_text())
        if reuse['boundary_sha256']!=boundary_hash or reuse['minimum_coverage']!=minimum_coverage or reuse.get('cadence_hours')!=cadence_hours or reuse.get('temporal_origin')!=temporal_origin:
            raise ValueError("Reused spatial/temporal contract differs")
        shutil.copytree(reuse_folder/'weights',staging/'weights',copy_function=os.link)
    seen_metrics.clear()
    for p,param_id,metric in identities:
        previous = next((source for source in (reuse or {}).get('sources',[]) if source['name']==metric.name),None)
        if previous and param_id not in GAS_PARAM_IDS and previous['source_sha256']==sha256(p) and previous['unit']==metric.unit:
            shutil.copytree(reuse_folder/'observations'/metric.name,staging/'observations'/metric.name,copy_function=os.link)
            (staging/'monthly').mkdir(exist_ok=True)
            os.link(reuse_folder/'monthly'/f'{metric.name}.parquet',staging/'monthly'/f'{metric.name}.parquet')
            sources.append(dict(previous, reused_from_generation=reuse_generation, source_param_id=param_id,
                source_level=0, source_level_type='surface', metric_id=metric.name, quantity_type=metric.quantity,
                display_unit=metric.unit, display_name=DISPLAY_NAMES.get(metric.name,metric.name), quality_status='validated', conversion_method='linear_scale_offset',
                source_resolution='3_hourly_analysis', display_resolution='1_hourly'))
        else:
            pending.append(p)
    # Build shared weights once before independent subprocesses write partitions.
    for p in pending:
        with p.open('rb') as stream:
            h=ec.codes_grib_new_from_file(stream)
            try:
                key=grid_identity(h)
                if key not in grids:
                    weights,table=build_weights(provinces,ec.codes_get_array(h,'latitudes'),ec.codes_get_array(h,'longitudes'),
                        ec.codes_get(h,'iDirectionIncrementInDegrees'),ec.codes_get(h,'jDirectionIncrementInDegrees'))
                    grids[key]=weights
                    folder=staging/'weights';folder.mkdir(exist_ok=True)
                    if not (folder/f'{key}.parquet').exists():
                        pq.write_table(table.replace_schema_metadata({b'area_crs':AREA_CRS.encode(),b'boundary_sha256':boundary_hash.encode(),b'grid_id':key.encode()}),folder/f'{key}.parquet')
            finally:
                ec.codes_release(h)
    if workers > 1:
        def worker(p):
            command=[sys.executable,'-m','app.etl.eac4','--worker-file',str(p.resolve()),'--output-dir',str(staging.resolve()),
                '--input-dir',str(Path(input_dir).resolve()),'--boundaries',str(Path(boundaries).resolve()),
                '--minimum-coverage',str(minimum_coverage),'--cadence-hours',str(cadence_hours),'--temporal-origin',temporal_origin]
            subprocess.run(command,check=True)
            return json.loads((staging/f'{p.stem}.source.json').read_text())
        with ThreadPoolExecutor(max_workers=workers) as pool:
            sources.extend(pool.map(worker,pending))
        for p in pending:
            (staging/f'{p.stem}.source.json').unlink()
    else:
        for p in pending:
            sources.append(process_file(p,staging,provinces,grids,minimum_coverage,boundary_hash,seen_metrics,cadence_hours,temporal_origin,support_paths))
    if not sources:
        raise ValueError("No supported dashboard metrics")
    manifest = dict(schema_version=1, generation=generation, source="CAMS EAC4",
                    created_at=datetime.now(timezone.utc).isoformat(),
                    boundary_source=str(Path(boundaries).resolve()), boundary_sha256=boundary_hash,
                    boundary_policy="Administrative provinces include their archipelagos; current supplied boundaries applied to all historical timestamps",
                    administrative_hierarchy={"20333": "48", "22736": "56"},
                    province_count=len(provinces), minimum_coverage=minimum_coverage,
                    area_crs=AREA_CRS, sources=sources, excluded_sources=excluded,
                    cadence_hours=cadence_hours, temporal_origin=temporal_origin,
                    input_directory=str(Path(input_dir).resolve()), processing_version=METHOD_VERSION,
                    support_sources=[dict(name=key, file=value.name, sha256=sha256(value), source_param_id=130 if key=='t_model' else 133, source_unit='K' if key=='t_model' else 'kg kg**-1', source_level=60, source_level_type='hybrid', role='density_support', quality_status='validated') for key,value in support_paths.items() if key!='sp'],
                    sampling_note="Hourly slots include temporal interpolation; sample counts do not represent independent physical observations",
                    previous_generation=reuse_generation,
                    provinces=[dict(code=p.code, name=p.name, lat=p.lat, lon=p.lon, area_m2=p.area_m2)
                               for p in provinces],
                    grid_coverage={**((reuse or {}).get("grid_coverage", {})), **{key: dict(zip([p.code for p in provinces], weights.sum(axis=1).tolist()))
                                   for key, weights in grids.items()}})
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
    parser.add_argument("--cadence-hours", type=int, choices=[1, 3], default=1)
    parser.add_argument("--temporal-origin", choices=["native", "interpolated", "unknown"], default="interpolated")
    parser.add_argument("--reuse-generation")
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--worker-file", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--minimum-coverage", type=float, default=0.95)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    if args.worker_file:
        provinces,boundary_hash=load_provinces(args.boundaries)
        grids={}
        with args.worker_file.open('rb') as stream:
            h=ec.codes_grib_new_from_file(stream)
            try:
                grid_size=len(ec.codes_get_values(h))
            finally:
                ec.codes_release(h)
        for file in (args.output_dir/'weights').glob('*.parquet'):
            rows=pq.read_table(file).to_pylist()
            weights=np.zeros((len(provinces),grid_size))
            codes={p.code:i for i,p in enumerate(provinces)}
            for row in rows:
                weights[codes[row['province_code']],row['cell_index']]=row['province_fraction']
            grids[file.stem]=weights
        support={}
        for p in args.input_dir.glob('*.grib'):
            with p.open('rb') as stream:
                h=ec.codes_grib_new_from_file(stream)
                try:
                    param=ec.codes_get(h,'paramId')
                    if param in SUPPORT_PARAMETERS:
                        support[SUPPORT_PARAMETERS[param][0]]=p
                    if param==134:
                        support['sp']=p
                finally:
                    ec.codes_release(h)
        result=process_file(args.worker_file,args.output_dir,provinces,grids,args.minimum_coverage,boundary_hash,set(),args.cadence_hours,args.temporal_origin,support)
        (args.output_dir/f'{args.worker_file.stem}.source.json').write_text(json.dumps(result))
        return
    build(args.input_dir, args.boundaries, args.output_dir, args.minimum_coverage, args.cadence_hours, args.temporal_origin, args.reuse_generation, args.workers)


if __name__ == "__main__":
    main()
