# Air Quality backend

FastAPI serves the **temporary CAMS EAC4 sample** from
`backend/data/samples/cams/eac4_provinces` by default. This preserves the current
dashboard values; it is not a validated Gold dataset or an official processing
pipeline. The compact monthly sample is included in the repository. Python 3.12
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

- `GET /api/dashboard`: province snapshots, monthly trends and source metadata.
- `GET /api/admin/dashboard`: management dashboard trends, province comparisons,
  priority areas, emissions, and annual summaries. The mock source includes
  illustrative management values; the CAMS sample leaves AQI, exceedance days,
  and emissions unavailable because that source does not provide them.
- `GET /api/health`: application liveness (not dataset readiness).
- `/docs`: generated API documentation.
- `DASHBOARD_DATA_SOURCE=parquet` is the default; `mock` explicitly enables the
  old demo for development/tests. Missing/corrupt Parquet returns HTTP 503;
  it never falls back to mock or a stale generation.
- `DASHBOARD_PARQUET_PATH` overrides `backend/data/samples/cams/eac4_provinces`.

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
- Output: `backend/data/samples/cams/eac4_provinces` (monthly sample is included; large intermediates are ignored).

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
`status` are null. The map defaults to PM2.5 and labels its snapshot month;
this is the latest valid monthly mean, not current air quality.

Parameter identities/units follow the GRIB headers and the official
[CAMS reanalysis documentation](https://confluence.ecmwf.int/pages/viewpage.action?pageId=621030809)
and [ECMWF parameter database](https://codes.ecmwf.int/grib/param-db/).

## Map concentration scales

Province snapshots include `pm1` alongside `pm25` and `pm10`, using the same
snapshot month. The map offers all three PM metrics and displays them in tooltips.

The backend publishes `metadata.metrics.<metric>.mapScale` for each PM metric:
`breakpoints`, `method=absolute_concentration`, `sampleCount`, `referenceStart`,
and `referenceEnd`. The last three fields describe the available valid monthly
data; thresholds are fixed and are not derived separately from each distribution.

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
when every source finishes. Existing generations stay available. Failed staging
folders may be removed after inspection; they are never served. The repository
caches only the active monthly view and reloads when `CURRENT` changes, returning
copies to callers. Never manually edit a published generation.

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
`repositories/parquet` reads the monthly serving view. Routes/services remain
source-independent. `repositories/mock` retains the explicit test/demo source.

```sh
backend/.venv/bin/python -m pip install -r backend/requirements-dev.txt
PYTHONPATH=backend OPENBLAS_NUM_THREADS=1 backend/.venv/bin/python -m pytest backend/tests -q
backend/.venv/bin/python -m pip check
npm --prefix frontend run build
npm --prefix frontend run lint
```

Tests cover the old mock contract, area fractions, holes, partial coverage,
latitude-dependent areas, missing-cell renormalization, unit conversions,
actual synthetic GRIB → Parquet → API, duplicate handling, atomic publication,
source errors and cache refresh. ETL imports PROJ before ecCodes because their
bundled native libraries conflict on shutdown with the reverse import order in
the verified local environment.
