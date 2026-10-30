"""Publish 34 administrative provinces from the former 36 reporting regions.

This migration only accepts complete valid spatial coverage for the two split
provinces. Otherwise rebuild from GRIB: suppressed regional means cannot recover
partially valid grid-cell numerators. Old generations remain recoverable.
"""
import calendar
from datetime import datetime, timezone
import json
from pathlib import Path
import uuid

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from app.etl.spatial import load_provinces

PARENTS = {'20333': '48', '22736': '56'}


def merge_complete_regions(values, coverage, grid_coverage, areas):
    """Combine disjoint region means using valid area, refusing lost samples."""
    if (not np.isfinite(values).all() or not np.isfinite(coverage).all() or
            not np.isfinite(areas).all() or np.any(areas <= 0) or
            np.any(coverage <= 0) or
            not np.allclose(coverage, grid_coverage, rtol=0, atol=1e-8)):
        raise ValueError('Incomplete regional inputs: rebuild province values from GRIB')
    valid_areas = coverage * areas
    return (values * valid_areas).sum(axis=-1) / valid_areas.sum(axis=-1)


def migrate(root: Path, boundaries: Path):
    previous = (root / 'CURRENT').read_text().strip()
    old = root / 'runs' / previous
    manifest = json.loads((old / 'manifest.json').read_text())
    old_provinces = manifest['provinces']
    codes = [p['code'] for p in old_provinces]
    if not set(PARENTS).issubset(codes):
        raise ValueError('Expected a generation with separate archipelago regions')
    provinces, boundary_hash = load_provinces(boundaries)
    new_codes = [p.code for p in provinces]
    if len(new_codes) != 34 or set(new_codes) != set(codes) - set(PARENTS):
        raise ValueError('Expected exactly 34 administrative provinces')
    generation = uuid.uuid4().hex
    staging = root / f'.staging-{generation}'
    staging.mkdir()
    # Recompute weights directly from unchanged province geometries and the
    # original grid geometry, validating equivalence to the disjoint old regions.
    (staging / 'weights').mkdir()
    grids = {}
    for file in (old / 'weights').glob('*.parquet'):
        rows = pq.read_table(file).to_pylist()
        # The original weight table only contains cells intersecting Vietnam.
        # Preserve these identities; no regridding or new field values are used.
        grouped = {}
        province_lookup = {p.code: p for p in provinces}
        for row in rows:
            code = PARENTS.get(row['province_code'], row['province_code'])
            key = (code, row['cell_index'])
            if key not in grouped:
                p = province_lookup[code]
                grouped[key] = dict(row, province_code=code, province_name=p.name,
                                    province_area_m2=p.area_m2, intersection_area_m2=0.)
            grouped[key]['intersection_area_m2'] += row['intersection_area_m2']
        totals = {}
        for (code, _), row in grouped.items():
            totals[code] = totals.get(code, 0.) + row['intersection_area_m2']
        for (code, _), row in grouped.items():
            row.update(province_fraction=row['intersection_area_m2']/row['province_area_m2'],
                       province_percent=100*row['intersection_area_m2']/row['province_area_m2'],
                       weight=row['intersection_area_m2']/totals[code],
                       grid_coverage_fraction=totals[code]/row['province_area_m2'])
        pq.write_table(pa.Table.from_pylist(list(grouped.values())), staging/'weights'/file.name, compression='zstd')
        grids[file.stem] = {code: totals[code]/province_lookup[code].area_m2 for code in new_codes}
    parents = {parent: [codes.index(parent), codes.index(child)] for child, parent in PARENTS.items()}
    keep = [codes.index(code) for code in new_codes]
    for source in manifest['sources']:
        metric = source['name']
        monthly = {}
        total_rows = valid_rows = 0
        for file in sorted((old/'observations'/metric).glob('*/*.parquet')):
            table = pq.read_table(file)
            n = table.num_rows // len(codes)
            identities = np.asarray(table['province_code']).reshape(n, len(codes))
            if not np.all(identities == np.asarray(codes)):
                raise ValueError('Unexpected region order or incomplete timestamps')
            arrays = {name: np.asarray(table[name]).reshape(n, len(codes)) for name in table.column_names}
            if not np.all(arrays['timestamp'] == arrays['timestamp'][:, :1]):
                raise ValueError('Mismatched regional timestamps')
            result = {name: values[:, keep].copy() for name, values in arrays.items()}
            times = table['timestamp'].to_pylist()[::len(codes)]
            for parent, indices in parents.items():
                if not np.all(arrays['quality_flag'][:, indices] == 'ok'):
                    raise ValueError('Invalid regional quality flags: rebuild from GRIB')
                pi = new_codes.index(parent)
                areas = np.array([old_provinces[i]['area_m2'] for i in indices])
                result['value'][:, pi] = merge_complete_regions(
                    arrays['value'][:, indices], arrays['valid_area_fraction'][:, indices],
                    arrays['grid_coverage_fraction'][:, indices], areas)
                result['valid_area_fraction'][:, pi] = (
                    arrays['valid_area_fraction'][:, indices]*areas).sum(axis=1)/provinces[pi].area_m2
                result['grid_coverage_fraction'][:, pi] = grids[source['grid_id']][parent]
                result['valid_cell_count'][:, pi] = sum(
                    r['province_code'] == parent for r in pq.read_table(staging/'weights'/f"{source['grid_id']}.parquet").to_pylist())
            for name, vals in [('province_name', [p.name for p in provinces]),
                               ('lat', [p.lat for p in provinces]), ('lon', [p.lon for p in provinces])]:
                result[name] = np.tile(vals, (n, 1))
            metadata = dict(table.schema.metadata or {})
            provenance = json.loads(metadata.get(b'provenance', b'{}'))
            provenance.update(boundary_sha256=boundary_hash, province_count=34,
                              administrative_hierarchy='Hoang Sa:48; Truong Sa:56',
                              spatial_migration_from=previous)
            metadata[b'provenance'] = json.dumps(provenance, ensure_ascii=False).encode()
            updated = pa.Table.from_arrays([
                pa.array(result[f.name].ravel(), type=f.type, from_pandas=True)
                for f in table.schema], schema=table.schema.with_metadata(metadata))
            target = staging/file.relative_to(old)
            target.parent.mkdir(parents=True, exist_ok=True)
            pq.write_table(updated, target, compression='zstd', row_group_size=36*168)
            total_rows += updated.num_rows
            valid_rows += int(np.isfinite(result['value']).sum())
            for month in sorted({t.month for t in times}):
                indices = [i for i,t in enumerate(times) if t.month == month]
                vals = result['value'][indices]
                key = (times[indices[0]].year, month)
                state = monthly.setdefault(key, [np.zeros(34), np.zeros(34, dtype=int), np.ones(34), 0])
                state[0] += np.nansum(vals, axis=0)
                state[1] += np.isfinite(vals).sum(axis=0)
                state[2] = np.minimum(state[2], result['valid_area_fraction'][indices].min(axis=0))
                state[3] += len(indices)
        records = []
        for (year, month), (sums, counts, coverage, samples) in sorted(monthly.items()):
            expected = calendar.monthrange(year,month)[1]*24//manifest['cadence_hours']
            for i,p in enumerate(provinces):
                records.append(dict(province_code=p.code, province_name=p.name, lat=p.lat, lon=p.lon,
                    timestamp=datetime(year,month,1,tzinfo=timezone.utc), metric=metric, unit=source['unit'],
                    value=float(sums[i]/counts[i]) if counts[i] else None, sample_count=int(counts[i]),
                    source_sample_count=samples, expected_sample_count=expected,
                    temporal_coverage_fraction=float(counts[i]/expected), minimum_valid_area_fraction=float(coverage[i])))
        (staging/'monthly').mkdir(exist_ok=True)
        pq.write_table(pa.Table.from_pylist(records).replace_schema_metadata(metadata),staging/'monthly'/f'{metric}.parquet',compression='zstd')
        source.update(rows=total_rows, valid_rows=valid_rows,
                      original_region_boundary_sha256=source['boundary_sha256'],
                      boundary_sha256=boundary_hash)
        source.pop('reused_from_generation', None)
        print(f'{metric}: {total_rows} rows, 34 provinces', flush=True)
    manifest.update(generation=generation, previous_generation=previous,
        created_at=datetime.now(timezone.utc).isoformat(), province_count=34,
        boundary_sha256=boundary_hash, grid_coverage=grids,
        provinces=[dict(code=p.code,name=p.name,lat=p.lat,lon=p.lon,area_m2=p.area_m2) for p in provinces],
        administrative_hierarchy=PARENTS,
        boundary_policy='34 administrative provinces; Hoang Sa belongs to Da Nang (48), Truong Sa to Khanh Hoa (56)',
        spatial_migration='Disjoint complete region means combined by valid area before temporal aggregation')
    (staging/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
    # Verify every published partition and monthly file before atomic activation.
    assert all(len(pq.read_table(f,columns=['province_code'])['province_code'].unique()) == 34
               for f in staging.rglob('*.parquet') if f.parent.name != 'weights')
    staging.rename(root/'runs'/generation)
    pointer = root/f'.CURRENT-{generation}'
    pointer.write_text(generation+'\n')
    pointer.replace(root/'CURRENT')
    return manifest


if __name__ == '__main__':
    from app.etl.eac4 import DEFAULT_OUTPUT, DEFAULT_BOUNDARIES
    print(json.dumps({'generation': migrate(DEFAULT_OUTPUT, DEFAULT_BOUNDARIES)['generation']}))
