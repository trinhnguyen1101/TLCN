# Medallion migration validation — 2026-10-31

## Acceptance and evidence scope

Bounded real-source Landing → Bronze → Silver → Gold processing passed for five populated datasets. CAMS archive integrity was checked by rehashing every current file against retained full ecCodes audit results. Three real hours, rather than the full 23-year archive, were materialized through Silver and Gold. No production full-archive backfill is claimed. APIs, frontend and dashboard code were not modified. Existing raw data, legacy cubes and published release snapshots were preserved.

ERA5 and live-provider production acceptance remain blocked by missing input. Climate TRACE native quantities are usable at their native grain, but verified mass-unit analytics remain blocked because current CSV files contain no unit declaration. The overall system is **accepted for bounded source-aware integration; not certified for a full production archive rollout**.

## Dataset acceptance matrix

| Dataset | Files / bytes | Landing | Bronze | Silver | Gold | Final status |
|---|---:|---|---|---|---|---|
| CAMS/EAC4 | 20 / 7853580144 | full checksum/metadata | real three-hour pilot + replay | 20 variables, 34,500 values | 612 concentration + 1,428 environmental rows | passed real bounded data |
| ERA5/single_levels | 0 / 0 | empty | blocked | blocked | blocked | missing source; no observations invented |
| climate_trace/climate_trace_vietnam | 3 / 7044783 | CSV structure + hashes | real existing batch verified | 17,280 aggregates + 32,384 sources | native facts + 216 country-period rows | passed native semantics; mass units unverified |
| reference/vietnam_administrative_divisions | 11 / 3699001 | parsed + hashed | real existing batch verified | identity/geometry/hierarchy checked | 34 roots + 2 components in CAMS dimensions | passed real data |
| reference/vietnamese-provinces-database | 3363 / 632822545 | parsed + hashed | real existing batch verified | identity/geometry/hierarchy checked | 34 roots + 2 components in CAMS dimensions | passed real data |
| waqi/historical | 17 / 862249 | CSV structure + hashes | real existing batch verified | 179,843 provider daily entries | 179,843 native daily entries | passed native provider indices; not concentration |
| WAQI live | no local collection | unavailable | implemented Supabase adapter | fixture/regression only | not production validated | blocked by missing input |
| API Ninjas | no local collection | unavailable | implemented Supabase adapter | fixture/regression only | not production validated | blocked by missing input |

Inventory details: [landing-inventory.json](landing-inventory.json), [runtime-state.txt](runtime-state.txt), [all-silver-audit.txt](all-silver-audit.txt). All 3,414 audited Bronze objects matched SHA-256. The two geography datasets share dimensions but retain distinct source lineage. Unknown future datasets are discovered dynamically and held as raw-only pending a reviewed adapter; they are not assigned CAMS semantics.

## All twenty CAMS variables and normalization

Every field has 201,622 distinct aligned timestamps from 2003-01-01 00:00 UTC through 2025-12-31 21:00 UTC; no missing interior hourly slots or duplicate messages. The final two hours of 2025 are outside available source coverage, not fabricated. Grid dimensions are 23 × 25 (575 ordered points). The six hybrid fields are at model level 60. Source metadata is instantaneous analysis, step zero, matching valid/reference time.

| Metric | paramId / shortName | Native unit | Standard unit | Formula | Vertical support |
|---|---|---|---|---|---|
| aod550 | 210207 / aod550 | ~ | 1 | native × 1.0 + 0.0 | surface:0 |
| co | 210123 / co | kg kg**-1 | ug/m3 | native × local density × 10⁹ | hybrid:60 |
| co_column | 210127 / tcco | kg m**-2 | mg/m2 | native × 1000000.0 + 0.0 | surface:0 |
| d2m | 168 / 2d | K | degC | native × 1.0 + -273.15 | surface:0 |
| mslp | 151 / msl | Pa | hPa | native × 0.01 + 0.0 | surface:0 |
| no2 | 210121 / no2 | kg kg**-1 | ug/m3 | native × local density × 10⁹ | hybrid:60 |
| no2_column | 210125 / tcno2 | kg m**-2 | mg/m2 | native × 1000000.0 + 0.0 | surface:0 |
| o3 | 210203 / go3 | kg kg**-1 | ug/m3 | native × local density × 10⁹ | hybrid:60 |
| o3_column | 210206 / gtco3 | kg m**-2 | mg/m2 | native × 1000000.0 + 0.0 | surface:0 |
| pm1 | 210074 / pm10 | kg m**-3 | ug/m3 | native × 1000000000.0 + 0.0 | surface:0 |
| pm10 | 210072 / pm1 | kg m**-3 | ug/m3 | native × 1000000000.0 + 0.0 | surface:0 |
| pm2p5 | 210073 / pm2p5 | kg m**-3 | ug/m3 | native × 1000000000.0 + 0.0 | surface:0 |
| q_model | 133 / q | kg kg**-1 | kg/kg | native × 1.0 + 0.0 | hybrid:60 |
| so2 | 210122 / so2 | kg kg**-1 | ug/m3 | native × local density × 10⁹ | hybrid:60 |
| so2_column | 210126 / tcso2 | kg m**-2 | mg/m2 | native × 1000000.0 + 0.0 | surface:0 |
| sp | 134 / sp | Pa | hPa | native × 0.01 + 0.0 | surface:0 |
| t2m | 167 / 2t | K | degC | native × 1.0 + -273.15 | surface:0 |
| t_model | 130 / t | K | degC | native × 1.0 + -273.15 | hybrid:60 |
| u10 | 165 / 10u | m s**-1 | m/s | native × 1.0 + 0.0 | surface:0 |
| v10 | 166 / 10v | m s**-1 | m/s | native × 1.0 + 0.0 | surface:0 |

Density uses p_half = A + B × surface pressure; p_full60 = (p_half59 + p_half60)/2; Tv = T × [1 + (1−0.621981)/0.621981 × q]; rho = p_full60 / (287.05 × Tv). The original GRIB L60 coefficients are validated against the retained ECMWF reference. Gas conversion is per time/grid point before area aggregation. Mean sea-level pressure is not used for density. Original bytes and native values remain recoverable via Bronze hash, timestamp and grid-point index; standardized float arrays are not converted again in Gold.

Unit/variable registry: [variable-registry.json](variable-registry.json). Full file-level metadata, hashes, grid ordering and QC evidence: [grib/inventory.json](grib/inventory.json), [grib-audit.txt](grib-audit.txt). Reference: [ECMWF CAMS documentation](https://confluence.ecmwf.int/pages/viewpage.action?pageId=188040388).

## Real numerical reconciliation

Independent ecCodes decoding, conversion and recorded area weights were compared with Trino Gold results for 2,040 province-hour-metric values covering all 20 variables. Maximum relative difference was 5.1e-08, consistent with final Silver float32 storage. Independent Bronze-to-Silver checks covered all 34,500 scalar pilot values; maximum relative float32 error was 5.96e-8. No missing values were replaced by zero; three legitimate PM zeros were retained.

[numerical-gold.json](numerical-gold.json) retains raw point examples, independent province means, Gold results, spatial weight sums, errors and release snapshots. [cams-real-integration.txt](cams-real-integration.txt) verifies raw checksums, grid alignment, all conversions, MERGE retry identity, successful-run skipping and unchanged legacy snapshots.

## Gold facts, marts and release provenance

The concentration pilot contains 34 province series × 3 hours × 6 pollutants = 612 sparse observations. Environmental facts contain 34 × 3 × 14 = 1,428 observations. The corresponding daily and monthly environmental marts each contain 476 rows. Area coverage gates apply before publication; parent geometry is unioned with linked archipelago components without double counting. Six concentration metrics and fourteen physical metrics remain separate. Wind components retain signed vector-component semantics; column burdens retain mg/m²; model-level temperature/humidity retain model-level identity.

Daily/monthly statistics describe available instantaneous samples. They are not measured daily mean concentrations. Monthly concentration means use sum/count, and environmental monthly means aggregate individual hourly samples. No monthly AQI is invented. Gold source lineage includes dataset, input snapshots and run IDs; environmental rows also carry cadence, vertical support, QC reason and coverage. Additive DDL leaves legacy release snapshot maps readable.

Initial twenty-metric release: `9c7b0dbfec3c9b5ce8e421fbf504fecb2ebe6e60f16905c2716102e7737ad07a` in `gold_test_medallion_hourly`. Its full input/output snapshot map is retained in the numerical evidence. Native release: `2c98e552e69817f96189e4b67b650de5a707e1f0db161066f44bc906059f352b` in `gold_test_medallion_native`. Latest runner release IDs and stage timings are retained under `runner/` and summarized below when available.

## VN_AQI eligibility and method verification

The retained Decision 1459 reference SHA-256 is `968c4cbb9bf5cf03e4a9bf30850afd8695d130f767324ac57ca02e2d54a48c26`; method version is `vn-aqi-1459-2019-project-v1`. The official document remains available and authoritative monitoring sites continue citing it; the checked sources did not reveal a replacement. This is a scoped current-use check, not a legal-register certification. [Official guidance](https://vea.mae.gov.vn/Data/files/QD%201459%20TCMT%20ngay%2012_11_2019%20AQI%281%29.pdf).

Actual CAMS hourly/daily calculated AQI is NULL: hourly instantaneous model analyses do not satisfy verified monitoring-station hourly-mean eligibility. Concentrations remain available. The mathematical fixture path produces 48 hourly and 2 daily valid AQI values, separately labeled as isolated eligible-mean fixtures. PM participation, both NowCast branches, age-preserving missing slots, zero handling, CO µg/m³ breakpoints, O3 rolling 8-hour bases/cutoff, local-day boundaries, ties and rounding are covered by golden tests. The 24/24 daily completeness gate is a versioned conservative project policy. The PDF printed NO2 example gives 60 for 118.7 while interpolation gives 59.35 → 59; the documented formula takes precedence.

## Regression diagnosis and fixes

The reported outer-driver failure was not reproduced: the retained driver JSON completes its final assertions. Inner Spark exit codes 1 at failed_stage and failed_after_registry are intentional negative tests. The resumed outer driver explicitly exited 0; see [release-regression-resumed.exit](release-regression-resumed.exit) and [release-regression-resumed.txt](release-regression-resumed.txt). No assertions were weakened. Corrections, withdrawals, failed-pointer safety, registry recovery, historical old-release reads, rollback and month-boundary builds passed.

Confirmed defects fixed: obsolete Silver hour%3 rejection; missing hourly source identity/Gold cadence contract; missing fourteen-metric Gold path; an initial additive DDL quotation typo (retained failed log followed by repaired successful run); missing environmental vertical/QC fields; host runner stopping before Gold; and native publication ordering that could publish before all selected native Silver dependencies completed. The last condition now defers shared native publication and is covered by a failure-injection runner unit test. The initial Airflow unit invocation lacked PYTHONPATH; rerunning with the documented DAG path passed. A sandbox Trino denial was resolved through mandatory command escalation, not a service fallback.

## Final unit/regression evidence

| Suite | Passed | Failed/errors | Skips | Evidence |
|---|---:|---:|---:|---|
| Framework | 7 | 0 | 0 | [framework-tests-resumed-final.txt](framework-tests-resumed-final.txt) |
| Silver | 34 | 0 | 0 | [silver-tests-resumed-final.txt](silver-tests-resumed-final.txt) |
| Gold | 32 | 0 | 0 | [gold-tests-resumed-final.txt](gold-tests-resumed-final.txt) |
| Airflow config | 11 | 0 | 0 | [airflow-tests-resumed-final.txt](airflow-tests-resumed-final.txt) |

Integration evidence distinguishes real available input from isolated fixtures. Read-only Silver audit passed five datasets; independent Gold comparison passed twenty metrics; native real Gold passed 179,843 WAQI daily records, 17,280 emission aggregates and 32,384 source observations. Empty provider branches are not counted as production successes.

## Resources, operations and limitations

The measured original twenty-metric Gold pilot completed in 36.28 s with local[1], 2 GiB configured driver heap, 612 bounded driver-collected concentration rows and one collect call. Its phase durations and output snapshot IDs are in [cams-gold-environmental-repaired.txt](cams-gold-environmental-repaired.txt). Spark worker configuration is 2 cores/2 GiB; source inventory totals approximately 8.5 GB. These are bounded-pilot measurements, not extrapolated archive throughput. Peak RSS, full-archive storage/shuffle and multi-host writer behavior are not certified. The process uses local advisory locks and a single writer; distributed locking remains a production prerequisite for multiple orchestration hosts.

No full archive backfill was launched. A full hourly archive entails 201,622 cube rows and about 2.32 billion scalar fields; unbounded explode/driver collection is prohibited. Silver keeps 512-timestep commit chunks; Gold scopes stay at 1..31 local days with halo history. Use measured larger chunks before production expansion. Source corrections/deletions use existing dependency invalidation and historical timeline publication; published references and snapshots must not be deleted.

Climate TRACE unit metadata, live provider payloads/timestamps, ERA5 source contracts, full-archive runtime/storage benchmarking and production hourly backfill remain open upstream/operational work. New environmental tables are not exposed by APIs; any API adoption is a future change outside this task. The native Gold script currently requires both initialized WAQI and Climate TRACE tables, documented as an onboarding dependency.

## Changed implementation and operating guide

Changes cover `scripts/inventory_landing.py`, `audit_medallion_grib.py`, `run_medallion.py`, `verify_medallion_gold.py`, framework tests, Silver CAMS cadence/version and tests, Gold hourly contract/runner, environmental facts/marts and additive DDL. Existing Bronze immutable storage, Silver physics, native source adapters, VN_AQI engine and release/timeline architecture were reused. See [medallion operations](../../docs/lakehouse/medallion-modernization.md) for execution, retry, contract and backfill details. All evidence, including failed intermediate attempts, remains retained.
