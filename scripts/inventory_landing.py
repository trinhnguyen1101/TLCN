"""Regenerate recursive Landing inventory, validation and scientific registry.

No source writes. Unknown datasets are inventoried as raw-only, never assigned
concentration semantics. Checksums identify bytes; schema inspection is bounded.
"""
import argparse
import csv
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'spark/jobs/silver'))
from cams_physics import CONTRACTS, GASES

ADAPTERS = {
    'CAMS/EAC4': ('cams_bronze_to_silver.py', 'cams', 'hourly instantaneous model grid', 'EAC4-hourly-v1'),
    'waqi/historical': ('waqi_bronze_to_silver.py', 'native_sources', 'provider daily index/station', 'provider_native'),
    'climate_trace/climate_trace_vietnam': ('climate_trace_bronze_to_silver.py', 'native_sources', 'annual/monthly emissions', 'provider_native'),
    'reference/vietnam_administrative_divisions': ('admin_bronze_to_silver.py', 'dimensions', 'versioned administrative hierarchy', 'source_native'),
    'reference/vietnamese-provinces-database': ('admin_bronze_to_silver.py', 'dimensions', 'versioned boundary components', 'source_native'),
}

def discover(root):
    """Source/dataset is the registration boundary; retain deeper directories."""
    for source in sorted(root.iterdir()):
        if source.is_symlink():
            raise ValueError('Landing symlink forbidden')
        if source.name.startswith('.'):
            continue
        if not source.is_dir():
            yield source.name, [source]
            continue
        for dataset in sorted(source.iterdir()):
            if dataset.is_symlink():
                raise ValueError('Landing symlink forbidden')
            if dataset.is_dir():
                paths = sorted(dataset.rglob('*'))
                if any(p.is_symlink() for p in paths):
                    raise ValueError('Landing symlink forbidden')
                yield dataset.relative_to(root).as_posix(), [p for p in paths if p.is_file()]
            else:
                yield dataset.relative_to(root).as_posix(), [dataset]


def inspect(path):
    ext = path.suffix.lower()
    if ext == '.csv':
        with path.open(encoding='utf-8-sig', newline='') as stream:
            # WAQI exports contain provider comment preambles.
            lines = (line for line in stream if not line.startswith('#'))
            reader = csv.reader(lines)
            header = next(reader)
            count = bad = 0
            dates=[]; gases=set()
            clean=[h.strip().lower() for h in header]
            for row in reader:
                if not row: continue
                count += 1
                for key in (['date'] if 'date' in clean else ['year']):
                    if key in clean and len(row)>clean.index(key):
                        value=row[clean.index(key)].strip()
                        if value: dates.append(value)
                if 'gas' in clean and len(row)>clean.index('gas'):gases.add(row[clean.index('gas')].strip())
                bad += len(row) != len(header)
        return dict(date_range_native=[min(dates),max(dates)] if dates else None, gases=sorted(gases), columns=header, rows=count, inconsistent_width_rows=bad,
                    status='failed' if bad else 'passed_structure')
    if ext in ('.json', '.geojson'):
        data = json.loads(path.read_text(encoding='utf-8-sig'))
        return dict(json_type=type(data).__name__, keys=list(data)[:30] if isinstance(data, dict) else [],
                    status='passed_parse', geometry_validation='deferred_to_silver' if ext == '.geojson' else None)
    if ext in ('.grib', '.grb', '.grib2'):
        import eccodes as ec
        keys = 'paramId shortName name units typeOfLevel level stepType dataType dataDate dataTime validityDate validityTime step Ni Nj md5GridSection numberOfMissing'.split()
        records=[]
        with path.open('rb') as stream:
            for _ in range(3):
                h = ec.codes_grib_new_from_file(stream)
                if h is None: break
                try: records.append({k:ec.codes_get(h,k) for k in keys})
                finally: ec.codes_release(h)
        if not records: raise ValueError('Empty GRIB')
        return dict(status='passed_bounded_decode', sample_messages=records,
                    validation_scope='first_three_messages; full archive separately audited')
    return dict(status='raw_preserved', validation_scope='opaque ancillary bytes')


def run(root, output):
    output.mkdir(parents=True, exist_ok=True)
    datasets=[]
    registry=[]
    for name, paths in discover(root):
        files=[]
        for p in paths:
            digest=hashlib.sha256()
            with p.open('rb') as stream:
                for chunk in iter(lambda:stream.read(1024*1024), b''): digest.update(chunk)
            record=dict(path=p.relative_to(root).as_posix(), bytes=p.stat().st_size, sha256=digest.hexdigest(), format=p.suffix.lower())
            try: record['validation']=inspect(p)
            except Exception as exc: record['validation']=dict(status='failed', reason=str(exc))
            files.append(record)
        adapter=ADAPTERS.get(name)
        datasets.append(dict(dataset_id=name, source_name=name.split('/')[0], source_version=adapter[3] if adapter else 'unreviewed',
            file_count=len(files), total_bytes=sum(f['bytes'] for f in files), formats=dict(Counter(f['format'] for f in files)),
            bronze_adapter='landing_to_bronze.py', silver_adapter=adapter[0] if adapter else None,
            gold_adapter=adapter[1] if adapter else None, native_semantics=adapter[2] if adapter else 'unknown',
            status='available' if paths else 'blocked_missing_source',
            readiness='requires_adapter_review' if paths and not adapter else 'registered' if paths else 'empty',
            files=files))
        print(name, len(files), flush=True)
    for col,(native,quantity,standard,scale,offset) in sorted(CONTRACTS.items()):
        registry.append(dict(dataset_id='CAMS/EAC4',source_variable=col, canonical_metric='pm25' if col=='pm2p5' else col,
            physical_quantity='mass_fraction' if col in GASES else quantity, measurement_kind='model_estimate',
            native_unit=native,standard_unit=standard,conversion_method='mmr_rho_l60_virtual_temperature_v1' if col in GASES else 'native_scale_offset_v1',
            conversion_parameters=dict(scale=scale, offset=offset, density_inputs=['sp','t_model','q_model'] if col in GASES else []),
            conversion_version='cams-physics-v1',temporal_support='instantaneous',vertical_support='model_level_60' if col in GASES or col in ('t_model','q_model') else 'atmospheric_column' if col.endswith('_column') or col=='aod550' else 'height_2m' if col in ('t2m','d2m') else 'height_10m' if col in ('u10','v10') else 'surface_field',
            quality_policy='fail_on_invalid_no_clipping', conversion_verified=True,
            source_reference='https://confluence.ecmwf.int/pages/viewpage.action?pageId=188040388'))
    for d in datasets:
        dates=[f['validation'].get('date_range_native') for f in d['files'] if f['validation'].get('date_range_native')]
        d['available_date_range_native']=[min(v[0] for v in dates),max(v[1] for v in dates)] if dates else None
        d['logical_keys']={'waqi/historical':['station_source_key','date','variable'], 'CAMS/EAC4':['source_version','valid_time','ordered_grid'], 'climate_trace/climate_trace_vietnam':['gas','source_id_or_aggregation','period','sector']}.get(d['dataset_id'],['source_version','administrative_identity'])
        d['ingestion_status']='not_queried_by_landing_inventory; see runtime-state.txt'
        d['spatial_representation']='grid_23x25' if d['dataset_id']=='CAMS/EAC4' else d['native_semantics']
        if d['dataset_id']=='waqi/historical':
            variables=sorted({c.strip() for f in d['files'] for c in f['validation'].get('columns',[]) if c.strip()!='date'})
            for col in variables:
                registry.append(dict(dataset_id=d['dataset_id'],source_variable=col,canonical_metric=col,physical_quantity='index',measurement_kind='provider_daily_aqi',native_unit='AQI',standard_unit='AQI',conversion_method='identity_provider_index',conversion_parameters={},conversion_version='waqi-native-v1',temporal_support='daily',vertical_support='station_provider_unspecified',quality_policy='finite_nonnegative_integer',conversion_verified=True,source_reference='https://aqicn.org/data-platform/register/'))
        if d['dataset_id']=='climate_trace/climate_trace_vietnam':
            for gas in sorted({g for f in d['files'] for g in f['validation'].get('gases',[])}):
                registry.append(dict(dataset_id=d['dataset_id'],source_variable=gas,canonical_metric=gas,physical_quantity='emission_quantity',measurement_kind='emission_quantity',native_unit=None,standard_unit=None,conversion_method='retain_native_unverified_unit',conversion_parameters={},conversion_version='climate-trace-native-v1',temporal_support='source_annual_or_monthly',vertical_support='source_native',quality_policy='finite_source_quantity_preserve_period_and_source_type',conversion_verified=False,source_reference='source CSV lacks explicit units'))
    artifact=dict(generated_at=datetime.now(timezone.utc).isoformat(),root=str(root.resolve()),datasets=datasets)
    (output/'landing-inventory.json').write_text(json.dumps(artifact,indent=2,ensure_ascii=False)+'\n')
    (output/'variable-registry.json').write_text(json.dumps(registry,indent=2)+'\n')
    return artifact

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--landing-root',type=Path,default=ROOT/'data/landing')
    parser.add_argument('--output',type=Path,default=ROOT/'reports/medallion_migration')
    args=parser.parse_args()
    run(args.landing_root,args.output)
