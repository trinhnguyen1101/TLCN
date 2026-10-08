# Air Quality backend

FastAPI serves the **temporary CAMS EAC4 sample** from
`backend/data/samples/cams/eac4_provinces` by default. This preserves the current
dashboard values; it is not a validated Gold dataset or an official processing
pipeline. Native 3-hour observations for 2024–2025 and the monthly history for
2003–2025 are included in the repository. Python 3.12
is used for local verification.

Quick setup in Vietnamese: [Thiết lập web dashboard](../docs/setup-web-dashboard.md).

## Run

From the repository root:

```sh
python3.12 -m venv backend/.venv
backend/.venv/bin/python -m pip install -r backend/requirements.txt
# Start the API. Paths are resolved from the project, independent of working directory.
backend/.venv/bin/python -m uvicorn app.main:app --app-dir backend --reload --port 8000
```

On Windows, use `py -3.12` and `backend\.venv\Scripts\python.exe`; run the ETL
from `backend` with `python -m app.etl.eac4` instead of setting `PYTHONPATH`.
`OPENBLAS_NUM_THREADS=1` limits overhead for the small aggregation matrices.

- `GET /api/dashboard`: province snapshots, 3-hour trends and source metadata.
- `GET /api/admin/dashboard`: management dashboard trends, province comparisons,
  priority areas, emissions, and annual summaries. The CAMS sample leaves AQI, exceedance days,
  and emissions unavailable because that source does not provide them.
- `GET /api/health`: application liveness (not dataset readiness).
- `/docs`: generated API documentation.
- `DASHBOARD_DATA_SOURCE=parquet` is the default and the only bundled provider.
  Missing/corrupt Parquet returns HTTP 503; it never substitutes generated data
  or a stale generation. The retired `mock` setting is rejected.
- `DASHBOARD_PARQUET_PATH` overrides `backend/data/samples/cams/eac4_provinces`.

Both dashboard endpoints accept `resolution=3h|daily|monthly`, `start` and `end`.
The default is `3h`, covering the last seven source days, not the current date.
Bounds accept ISO dates or date/time strings. Naive times mean UTC; timezone
offsets are normalized to UTC. An end date includes the whole day, while an end
instant is inclusive. Native queries allow at most 31 days; daily queries allow
366 days. Invalid bounds return HTTP 422. Examples:

```text
/api/dashboard?resolution=3h&start=2025-12-01&end=2025-12-07
/api/admin/dashboard?resolution=3h&start=2025-12-31T00:00:00Z&end=2025-12-31T21:00:00Z
/api/dashboard?resolution=daily&start=2025-01-01&end=2025-12-31
/api/dashboard?resolution=monthly
```

Native records retain full UTC timestamps in `date`; daily/monthly aggregates
use calendar dates. One native Parquet row is **region × UTC timestamp × metric**,
with eight timestamps per day. The API pivots metrics into one row per region
and timestamp. Daily averages require at least six valid observations out of
eight. Monthly coverage still requires 75% of expected samples. Neither native
values nor native snapshots are masked by monthly temporal coverage.

Metadata includes `queryStart`, `queryEnd`, `observationStart`, `observationEnd`
and `availableYears`. Snapshots use one latest valid timestamp inside the queried
period across all regions; missing values remain null. Bounded admin windows do
not become annual summaries. Missing/corrupt native files return 503, with no
fallback to monthly averages. Queries outside the bundled native period return
empty records; use monthly resolution for older history or rebuild from GRIB.

The current workspace also retains all 33,872,832 native rows for 2003–2025.
Only the last two native years (2,947,392 rows) are bundled in Git; older native
partitions stay local. Metadata and the frontend detect the native years present
on disk. `python -m app.etl.sample --years 0` preserves full native history;
`--years 2` creates a portable two-year sample. Use `--source-generation <id>`
to package a previous full ETL generation. Update the generation-specific
`.gitignore` exception when replacing the bundled sample.

The frontend continues to use `/api/dashboard` through its existing Vite proxy.
Restart an existing backend process after moving samples or changing configuration.

## Optional sample conversion

Normal setup uses the included sample and does not run ETL. To regenerate it
from local GRIB files, install the optional conversion dependencies first:

```sh
backend/.venv/bin/python -m pip install -r backend/requirements-etl.txt
PYTHONPATH=backend OPENBLAS_NUM_THREADS=1 backend/.venv/bin/python -m app.etl.eac4
```

This writes temporary samples inside `backend/`, never the Gold layer by default.
The following describes that local conversion, not production data certification.

## Inputs and method

Defaults:

- GRIB: `data/landing/CAMS/EAC4/*.grib`.
- Province polygons: `data/landing/reference/vietnamese-provinces-database/json/geojson/*/*.geojson`.
  Only province files are read; ward files are excluded. The supplied collection
  has 34 provinces. Their present boundaries are applied consistently to
  **all historical years**, not treated as historical administrative boundaries.
- Output: `backend/data/samples/cams/eac4_provinces` (the active portable sample includes two native years and full monthly history).

Override locations with `--input-dir`, `--boundaries` (directory or one GeoJSON
FeatureCollection), `--output-dir`, and `--minimum-coverage` (default `0.95`).
For example, the frontend's `public/data/vietnam-provinces.geojson` can also be
passed as the boundary file.

1. Read ecCodes `paramId`, units, grid section, analysis/surface level, step type
   and **validity time** from every message. Filenames do not define the metric.
   Reject unknown units, mixed grids/parameters and non-instantaneous fields.
2. Construct cells around GRIB centres using half the native increments. Current
   files use a 22 × 11 grid at 0.75°, with centres from 8.25–24° N and 102–109.5° E.
   The outer cells extend by half an increment; no extrapolation beyond them.
3. Repair invalid polygon topology, preserve islands/multipolygons/holes, and
   intersect each province with every overlapping cell. Densify edges to 0.025°
   before projecting to **EPSG:6933**, an equal-area CRS. Areas are square metres,
   never square degrees. The source's declared `areaKm2` is not the denominator.
4. For province P and cell i, `fraction_i = area(P ∩ cell_i) / area(P)`.
   `province_percent = 100 × fraction_i`. At each timestamp:

   ```text
   valid_area_fraction = Σ fraction_i                 (finite cells only)
   province_value = Σ(fraction_i × cell_value_i) / valid_area_fraction
   ```

   Missing cells are excluded and weights renormalized. If valid area is below
   95% of the **whole province**, output value is null with
   `quality_flag=insufficient_coverage`. Coverage is retained even for null rows.
   No nearest-cell fallback, zero filling, clipping of signed wind, or fabricated
   coverage for islands outside the downloaded grid. For the supplied files,
   Khánh Hòa has 65.76% spatial coverage and Đà Nẵng 94.80%; both are null at the
   default 95% threshold. The other 32 provinces are fully covered. Lowering
   `--minimum-coverage` deliberately accepts partial-area estimates; it does not
   create information for uncovered areas.
5. Convert to the units below. Keep native 3-hour UTC observations in Parquet;
   calculate a separate monthly arithmetic mean of the valid 3-hour samples.
   Monthly Parquet retains sample counts, expected calendar counts and coverage.
   The dashboard excludes months with fewer than 75% valid expected samples.
6. Verify timestamp uniqueness. Identical decoded duplicate fields are skipped
   and counted in the manifest; conflicting duplicates or out-of-order unique
   timestamps fail the build. The supplied `u10` file has 224 identical duplicates.

These are model reanalysis estimates on a coarse grid, not station measurements.
`lat`/`lon` in observation/monthly tables identify a point inside the province;
`lat`/`lon` in the weights table are original GRIB cell centres.

## Units and scientific meaning

| Metric | GRIB unit | Stored unit | Conversion |
| --- | --- | --- | --- |
| `pm1`, `pm25`, `pm10` | kg m⁻³ | µg/m³ | × 10⁹ |
| `o3_column`, `no2_column`, `so2_column`, `co_column` | kg m⁻² | mg/m² | × 10⁶ |
| `t2m`, `d2m` | K | °C | − 273.15 |
| `sp`, `mslp` | Pa | hPa | × 0.01 |
| `u10`, `v10` | m s⁻¹ | m/s | unchanged, signed components |
| `aod550` | dimensionless | 1 | unchanged |

Total-column mass is **not surface concentration**. There is no valid direct
conversion from kg/m² to µg/m³ without vertical information. The API therefore
exposes `o3Column`, `no2Column`, `so2Column`, `coColumn` separately; legacy
surface `o3`, `no2`, `so2`, `co` fields remain null for this source.

No sectoral emission inventory is present: emission arrays are empty. No AQI
method with appropriate averaging periods is implemented: snapshot `aqi` and
`status` are null. The map defaults to PM2.5 and labels its snapshot timestamp;
this is the latest valid observation in the selected source period, not live air quality.

Parameter identities/units follow the GRIB headers and the official
[CAMS reanalysis documentation](https://confluence.ecmwf.int/pages/viewpage.action?pageId=621030809)
and [ECMWF parameter database](https://codes.ecmwf.int/grib/param-db/).

## Map concentration scales

Province snapshots include `pm1` alongside `pm25` and `pm10`, using the same
snapshot month. The map offers all three PM metrics and displays them in tooltips.

The backend publishes `metadata.metrics.<metric>.mapScale` for each PM metric:
`breakpoints`, `method=absolute_concentration`, `sampleCount`, `referenceStart`,
and `referenceEnd`. The last three fields describe the available valid monthly
data at the selected temporal resolution; thresholds are fixed and are not derived separately from each distribution.

All three PM metrics share these absolute concentration bands (µg/m³):

| Label | Concentration | Color |
| --- | --- | --- |
| Tốt | ≤25 | Green |
| Trung bình | >25–50 | Yellow |
| Kém | >50–100 | Orange |
| Xấu | >100 | Bright red |

These are application-defined display categories for monthly CAMS concentrations,
not health or regulatory AQI thresholds. Using the same absolute thresholds
lets changes in PM mass concentration change the map's color distribution;
there is no percentile balancing, per-metric rescaling or percentage legend.
The same value always has the same color for PM1, PM2.5 and PM10. The latest
December 2025 snapshot has category counts 9/14/7/2 for PM1, 8/9/10/5 for PM2.5
and 3/7/14/8 for PM10 across 32 provinces with valid data.

The same API breakpoints drive both province colors and legend labels. Null and
nonfinite observations are excluded; zero is valid. Four bands are retained even
when all values fall into one band. Missing values keep the no-data color.
The separate AQI scale is retained for explicitly supplied AQI values; CAMS
still does not fabricate an AQI.

Implementation: `PM_CONCENTRATION_BREAKPOINTS` in `app/services/map_scale.py`
is the single configuration point for PM cutoffs.
`frontend/src/features/geography/mapColorScale.ts` defines colors and labels.
No GRIB/Parquet rebuild is needed; restart the API and reload the page after a
scale change to refresh cached responses.

## Parquet layout and provenance

### Separate mainland and archipelago regions

The default boundary loader (`app/etl/regions.py`) subtracts the supplied
special-region polygons from their parent provinces before computing weights:

- `48`: Đà Nẵng; `20333`: Quần đảo Hoàng Sa (Đà Nẵng, Việt Nam).
- `56`: Khánh Hoà; `22736`: Quần đảo Trường Sa (Khánh Hoà, Việt Nam).

Nearby coastal islands remain in the mainland reporting region. These are
reporting identities, not a change to administrative province codes. The default
CAMS sample now has 36 reporting regions. Each has its own area denominator,
grid intersections, coverage checks and monthly series. Missing offshore grid
coverage stays null; it never falls back to the parent province's value.

`app/etl/spatial.py` computes fractional cell overlap in EPSG:6933 and aggregates
only valid values, requiring 95% spatial coverage. The API also requires 75%
monthly temporal coverage. Existing combined averages cannot be split correctly
after aggregation, so rebuild from the supplied GRIB sample:

```powershell
$env:PYTHONPATH = 'backend'
backend/.venv/Scripts/python -m app.etl.export_regions
backend/.venv/Scripts/python -m app.etl.eac4
```

If only display labels change, run `python -m app.etl.relabel` with
`PYTHONPATH=backend`. It publishes a new generation with the same observations
and numeric monthly values, updating region names in the manifest and serving
tables.

The map exporter uses the same region boundaries and identifiers as the ETL.
`frontend/src/features/geography/ProvinceBoundaryLayer.tsx` selects each polygon
and joins its metrics by feature ID. A custom `--boundaries` GeoJSON file is
treated as an already prepared reporting-region collection; the default directory
loader performs the split using `wards/20333_hoang_sa.geojson` and
`wards/22736_truong_sa.geojson`. Boundary hashes cover the resulting features.

The row counts below describe the older 34-province generation; inspect the
active generation's manifest for current counts and coverage.

```text
backend/data/samples/cams/eac4_provinces/
├── CURRENT                         # published generation UUID
└── runs/<generation>/
    ├── manifest.json               # sources, SHA-256, conversions, period, duplicates, coverage
    ├── weights/<grid-id>.parquet    # reusable province/cell intersections
    ├── observations/<metric>/<year>/part-00000.parquet
    └── monthly/<metric>.parquet    # compact serving view
```

The directory names organize partitions; all identifying fields are also stored
inside each file, so files can be read independently without Hive inference.

The supplied 2003–2025 inputs produce **31,991,008 native rows**, **131,376
monthly rows**, and 219 province/cell intersections across 14 metrics. Each
metric has 67,208 distinct 3-hour timestamps. At the default coverage threshold,
32 provinces have values; the other two retain null observations and coverage.

Native observation grain: **province × UTC timestamp × metric**.
Columns: `timestamp`, `province_code`, `province_name`, `lat`, `lon`, `metric`,
`value`, `unit`, `valid_area_fraction`, `grid_coverage_fraction`,
`valid_cell_count`, `quality_flag`, `grid_id`, `source_file`.

Weights include `cell_index` in original GRIB scan order, centre/bounds,
`intersection_area_m2`, `province_area_m2`, `province_fraction`,
`province_percent`, normalized static `weight`, and `grid_coverage_fraction`.
The static weight covers all intersecting cells; missing-value renormalization
is applied per observation separately.

Monthly tables add `sample_count`, `source_sample_count`, `expected_sample_count`,
`temporal_coverage_fraction` and `minimum_valid_area_fraction`. `timestamp` is the
first day of the represented month. The API's `date` has the same meaning.

Parquet schema metadata stores source file SHA-256, GRIB identity/unit, conversion
factor/offset, boundary SHA-256, grid ID, CRS and coverage threshold. The manifest
also records the boundary policy, province coordinates/areas, source date ranges,
duplicate counts and generation time.

Builds use an unpublished `.staging-<UUID>` directory and replace `CURRENT` only
when every source finishes. Existing generations are retained by the ETL until
explicit cleanup. Only `CURRENT` is served; `parent_generation` is provenance,
not a runtime dependency. An unused generation can be removed after checking
that needed observations/aggregates are retained (compare checksums before
removing duplicate files) and preserving useful weights. Failed staging
folders may be removed after inspection; they are never served. The repository
caches generation metadata and reads only requested native partitions.
Native startup reads monthly timestamp columns for available years; full monthly
values are loaded lazily when monthly history is requested. It reloads when
`CURRENT` changes, returning isolated copies to callers. Never manually edit a
published generation.

Native filters push timestamp bounds into the Parquet reader. Identity, unit,
coverage and value checks run on Arrow columns; daily means are grouped in Arrow
before creating API records. UTC dates are computed directly from UTC timestamps
without per-row timezone conversion. A day still requires at least six valid
3-hour samples, and duplicates across files are rejected before aggregation.
Filtered requests copy only the requested monthly rows and their own metadata;
the cached generation remains isolated from response mutations.

Completed temporal queries use an LRU cache limited to 16 windows and 80,000
trend records. Keys contain the generation, resolution, normalized UTC bounds
and native file names/sizes/modification times. Source publication clears the
cache; added, changed or removed native files invalidate the affected window.
Concurrent identical requests share one computation. Bounded native scans,
cache copies and waiting happen outside the generation lock, so independent windows can proceed.
Failed scans are not cached and can be retried. The admin projection omits
unset optional metric fields to reduce JSON payload size.

Local repository timings on the current sample (milliseconds, excluding HTTP
serialization and browser rendering): the initial default native request changed
from 848 to 470; a repeated default window from 152 to 6; a repeated 2025 daily
window from 814 to 33. The first annual daily scan still takes about 0.9 seconds;
cache improvements apply after that window is computed. These are local timings,
not a production latency guarantee.

Example inspection from the repository root:

```python
from pathlib import Path
import pyarrow.parquet as pq

root = Path("backend/data/samples/cams/eac4_provinces")
run = root / "runs" / (root / "CURRENT").read_text().strip()
print(pq.read_table(run / "monthly/pm25.parquet").slice(0, 5).to_pylist())
print(pq.read_table(run / "observations/pm25/2025/part-00000.parquet").schema)
```

## Backend structure and checks

`app/etl` owns normalization, geometry and batch conversion;
`app/repositories/parquet` reads bounded native observations and the monthly
serving view. `app/services/admin_projection.py` derives the management view
from the chosen source; routes depend on the service contract. Temporal
validation lives in `app/services/temporal.py`.

```sh
backend/.venv/bin/python -m pip check
npm --prefix frontend run build
npm --prefix frontend run lint
```

ETL imports PROJ before ecCodes because their
bundled native libraries conflict on shutdown with the reverse import order in
the verified local environment.
