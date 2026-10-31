# Dataset-aware Landing to Gold operations

## Trigger from Airflow without editing JSON

The existing `landing_batch_to_gold` DAG now resolves an empty UI trigger to
`DEFAULT_FULL_RUN_CONF` in `airflow/dags/landing_batch_to_gold.py`: all five
populated registered Landing datasets through Bronze/Silver, then native Gold
and hourly CAMS Gold from 2003-01-01 through 2026-01-02 (exclusive), in 14-day
chunks. Batch IDs derive from the DagRun ID; ingestion dates use the DagRun UTC
logical date. Retries/clears keep those identities stable. No JSON input is
required. The CAMS dataset ID is preconfigured for `EAC4-hourly-v1`.

After the scheduler reloads the mounted DAG file, refresh Airflow, enable the
DAG if paused, and create a new run using Trigger. Existing DagRuns with explicit
configuration retain their overrides; a partial `gold` override merges into the
code defaults, and `publish_gold=false` still selects Silver-only execution.
This is full-archive Silver processing; verify disk capacity and keep the
`iceberg_writer` pool at one slot. Empty ERA5 and live collections are not added
to this five-dataset batch DAG. Live collection uses `supabase_daily_to_gold`.

The host runner `scripts/run_medallion.py` discovers every source/dataset directory recursively, inventories immutable source bytes and checksums, dispatches existing source-specific Silver jobs, and optionally executes Gold. Unknown datasets are reported with missing adapters; empty sources are blocked independently. Ancillary files within a registered dataset are retained. No raw source is rewritten.

```bash
backend/.venv/bin/python scripts/inventory_landing.py
backend/.venv/bin/python scripts/run_medallion.py --execute --cams-pilot --gold
```

The second command serializes work, runs a three-hour real GRIB pilot into a unique validation dataset, uses an isolated `gold_test_medallion_runner` Gold schema, and processes available non-CAMS datasets at their native grains. It does **not** publish validation data to production. Dataset checkpoints preserve the original date and content-derived batch ID on retry. Timestamped stage logs and `orchestration-results.json` distinguish failure, missing input, skipped work and successful normalization. The native Gold branch uses the existing registered native Silver snapshots; administrative references enter Gold through the CAMS geography dimensions. Existing native Gold currently requires both WAQI and Climate TRACE Silver snapshots, an onboarding dependency if either has never been initialized.

Production full CAMS normalization requires `--include-full-cams`, followed by a bounded 1..31-day Gold scope (`--start-date`, `--end-date`). Do not use that archive option until measured storage and runtime permit it. `scripts/run_gold.py` remains the bounded multi-chunk backfill runner. Single-writer locking is local/advisory; do not run another host or Airflow writer concurrently.

## Source and normalization contracts

* CAMS Silver pipeline 4.1 accepts aligned hourly instantaneous step-zero analyses; default source version is `EAC4-hourly-v1`. The historical `EAC4` source identity remains available explicitly. Gold's new default `cams-eac4-hourly-v1.json` is separate from historical `cams-eac4-v1.json`, which can still be passed explicitly. Source version and contract must match. No resampling or forecast/analysis blending occurs.
* PM native kg/m³ is multiplied by 10⁹ once in Silver. Gases at hybrid level 60 use aligned surface pressure, model-level temperature, specific humidity and verified L60 coefficients to derive density. Gold reads standardized arrays without scaling them again. Original values remain reproducible from checksummed Bronze GRIB and timestamp/grid index.
* Column masses retain mg/m². Temperature uses °C, pressure hPa, vector components m/s, specific humidity kg/kg and AOD dimensionless units. Signed wind and Celsius temperature are valid. Invalid native concentrations, unknown units, nonfinite values, inconsistent grids and incompatible vertical coordinates fail Silver without clipping.
* WAQI history remains provider daily indices, not concentration. Climate TRACE quantities retain unknown units when the CSV does not declare them; sector/gas/period and point versus regional source identities remain separate. Administrative references preserve 34 root provinces and linked archipelago components.

`landing-inventory.json`, `variable-registry.json` and the full GRIB metadata audit under `reports/medallion_migration` are regenerated with the supplied scripts. CSV structural validation is not a substitute for Silver semantic validation. ERA5 is presently empty; its decoder/normalizer must be reviewed when actual source metadata arrives. Live WAQI and API Ninjas use the existing Supabase ingestion path and cannot be production-validated with empty local collections.

## Gold physical metrics and release safety

The six concentration pollutants retain existing facts and API-facing schemas. Fourteen additional CAMS metrics use `fact_environmental_hourly`, `mart_environmental_daily`, and `mart_environmental_monthly`. All current variables are intensive instantaneous fields: area-weighted state/column-density means are appropriate; wind components are averaged separately. The contract admits no accumulated field or scalar wind-direction averaging. Temporal means represent available instantaneous samples, not measured hourly/daily means. Period statistics retain sum and valid sample count; monthly means use individual samples rather than equally weighted daily means.

Every environmental hourly row retains dataset/location, physical metric/unit, vertical support, cadence, temporal support, input run IDs, input snapshot and spatial coverage. Gold releases pin these additive tables alongside concentration and AQI outputs. Older output snapshot maps remain valid; no old release is rewritten. Future API exposure of the new tables requires a separate downstream task.

VN_AQI remains `vn-aqi-1459-2019-project-v1`, with the retained Decision 1459 PDF and SHA-256. Instantaneous CAMS analyses are ineligible: concentration facts remain populated, hourly/daily calculated AQI is NULL with explicit reasons. Station-reference inputs require verified monitoring-station hourly means and PM participation. The existing 24/24 daily gate is conservative project policy. Eligible mathematical paths are tested using isolated fixtures, never presented as real station production evidence.

Use the existing Gold runbook for correction/withdrawal invalidation, timeline publication, rollback and snapshot retention. Failed staging and validation must not advance the current pointer. The validation report records actual release IDs, snapshots, evidence scope and remaining production limitations.

## Final acceptance and evidence-only recovery

[Migration validation](../../reports/medallion_migration/VALIDATION.md) records the bounded acceptance scope and source-specific blockers. Reconcile saved execution results without launching Spark or requiring network access:

```bash
backend/.venv/bin/python scripts/finalize_medallion_acceptance.py
```

This checks all four outer exit markers, native dependency ordering, numerical tolerances, current inventory hashes against the full GRIB audit, and final unit-suite results. It regenerates the report and `acceptance-summary.json`. Exact local unit commands and exit codes are retained in `final-test-commands.json`.

To repeat native validation when Docker is available, use the project runner directly; no temporary shell script is required:

```bash
backend/.venv/bin/python scripts/run_medallion.py --execute --gold \
  --dataset climate_trace/climate_trace_vietnam --dataset waqi/historical \
  --output reports/medallion_migration/runner-final-native
```

The retained checkpoint file reuses the existing immutable Bronze batches. Native Gold publication runs after all selected native Silver dependencies succeed; a selected failed/missing dependency blocks that shared branch. The CAMS pilot and empty ERA5 status remain independent.
