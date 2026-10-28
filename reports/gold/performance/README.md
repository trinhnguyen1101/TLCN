# Gold performance hardening — 28 October 2026

Status: **development fixtures verified; production/archive readiness incomplete**.
These results supplement the functional acceptance in `../readiness/`; no
production data, method/breakpoints, source snapshots or published history were
deleted. All new hourly data is confined to `gold_test_perf*`.

## Runtime and dataset

Spark 3.5.4 / Iceberg 1.7.1, Java11/Python3.8, local[1], driver heap2GiB;
Nessie/MinIO/Trino476 on the existing Compose host. No executor scaling claim.
Fixture generator uses Spark range/crossJoin, six concentrations in verified
fixture ug/m3/model_surface, 34 real province identities, 24 means/day, explicit
intervals, observation at interval end and independent collection/schedule.
It includes two absent observations, one invalid QC value and one explicit NULL
in the full 31-day input. Contract `benchmark-hourly-v1` is not production reviewed.

## Spark measurements

| Case | Process / build seconds | Collected input rows incl. 11h halo | Jobs / stages / tasks | Driver Python peak RSS KiB |
| --- | --- | --- | --- | --- |
| 1 province × 7 days | 29.010 / 26.239 | 1,073 | 201 / 196 / 201 | 68,060 |
| 34 provinces × 1 day | 26.800 / 23.997 | 7,140 | 201 / 196 / 201 | 89,440 |
| 34 provinces × 7 days, before | 33.355 / 30.555 | 36,514 | 290 / 285 / 291 | 231,740 |
| 34 provinces × 7 days, after | 32.500 / 29.695 | 36,514 | 201 / 196 / 201 | 232,156 |
| 34 provinces × 16 days | 40.084 / 37.274 | 80,578 | 201 / 196 / 201 | 449,044 |
| 34 provinces × 15 days | 41.088 / 38.321 | 75,684 | 208 / 208 / 213 | 422,220 |

Raw Spark logs and metrics live in each case directory. Phase timings separately
record adapters, AQI, marts, validation and publish. The 16-day case used 10.020s
adapter, 8.218s AQI, 3.620s validation and 1.425s publish. The 15-day case used
9.472s/8.129s/4.379s/1.871s respectively. A normalized-area fixture does not
measure spatial aggregation; the native CAMS regression measures that separately.

One 31-day build would exceed the unchanged 100,000-row collection guard
(154,018 source rows). It was deliberately run as **16 + 15 days**, total process
81.172s. Default production onboarding starts with 7-day chunks. For this exact
34×6 contract the upper theoretical 19-day scope is not a recommended budget;
additional series/metrics require smaller chunks. Adapter remains bounded driver
processing, not a distributed normalization refactor. Backpressure is explicit:
over-budget input rejects publication; retry a smaller scope with the host runner.
The two month releases record distinct code hashes because the unused retention
tool was added between runs. Their concentration/AQI algorithms, source snapshot,
method and semantic contract are unchanged; both registered lineages remain
visible. This is not a claim that every measurement used one identical code hash.

RSS is sampled from `/proc` every0.2s. Local Spark driver/executor share one JVM.
JVM peaks were 1,743,076KiB for 7days and 2,022,880KiB for 15days; sampled process
tree peaks 2,103,744/2,579,440KiB may double-count shared pages. Maximum child RSS
is a separate Linux rusage statistic, **not total Docker RAM**. No memory reduction
is claimed. Global task maxima/medians do not establish skew across unlike stages;
per-stage task runtimes are retained, and this local run mostly has one task/stage.

## Changes justified by measurements

- Three grain/null/duplicate scans per output table became one grouped aggregate.
- An eager AQI count before the four cached-output writes was removed.
- Snapshot discovery reads Iceberg `currentSnapshot()` rather than sorting
  creation timestamps. An isolated rollback probe demonstrated the former helper
  selected a newer abandoned snapshot. Before/after JSON records the real probe.

Jobs decreased31%; process runtime improved only2.6% in one trial, within possible
run-to-run noise. Shuffle did not improve (10,564,176 →10,589,348 read bytes).
Avoid repeated benchmarking or claiming an unmeasured archive speedup.
`equivalence-34d7.json` compares20 tables: facts, lineage and all AQI results exact;
daily/monthly floating-point sufficient statistics permit abs1e-9 + rel1e-12
because parallel SQL summation changed last bits (e.g.267.6 vs267.59999999999997).
NULLs, keys, counts, statuses and other fields remain exact. AQI engine unchanged.

## Materialized month and actual serving

`api-month34.json` is real FastAPI → Trino → pinned Iceberg acceptance over the
two published monthly chunks, not a mock. It verifies25,296 hourly rows/pollutant
in pages10,000/10,000/5,296,1,054 daily rows and34 monthly rows; all34 provinces
in the dashboard. PM2.5 has25,295 valid values and one absent slot. O3 absence,
SO2 invalid QC and NO2 present-but-NULL remain separate. The two chunks do not
duplicate halo measurements in serving. Hourly/day AQI are model/area estimates,
not official station values. Monthly AQI remains NULL/not_defined_for_month.
Distribution is1,054 series-days (1good/1,053moderate), not six pollutant copies.

Thirty measured Trino statements took0.024–0.211s each in this run; HTTP hourly
pages took0.750/0.689/0.426s including serialization. Query IDs, engine planning,
CPU, physical input and client times are in the artifact. This is a warm local
fixture result, not a concurrent-user SLA or production archive benchmark.

Current head storage for the two chunks:

| Table | Files | Compressed bytes | Head records |
| --- | --- | --- | --- |
| Concentration fact | 3 | 62,709 | 156,262 incl. per-chunk halos |
| Hourly AQI overall | 3 | 34,026 | 25,296 |
| Hourly mart | 3 | 102,406 | 151,776 |
| Daily mart | 2 | 41,774 | 6,324 |
| Monthly mart | 2 | 21,003 | 408 partial-chunk rows |

Strongly repetitive fixture values compress unusually well. These are selected
table heads, not all retained snapshots or MinIO object-store consumption. No
full-archive storage extrapolation is certified. Monthly API composes daily
sum/count instead of averaging these two partial-month materializations.

## Historical metadata scaling

`timeline-before.json` / `timeline-after.json` simulate100/500/1,200 seven-day
chunks with34 series and6 snapshot mappings; no thousands of real snapshots.

| Chunks | v1 manifest bytes | v2 bytes |
| --- | --- | --- |
| 100 | 1,318,552 | 97,052 |
| 500 | 6,592,552 | 435,052 |
| 1,200 | 15,822,052 | 1,026,552 |

Wire format2 dictionary-encodes repeated series metadata. Snapshot mappings stay
inline; v1 remains readable; old IDs/manifests are never rewritten. At1,200chunks
resolve fell0.255→0.062s, Python traced allocation peak31,475,932→2,160,766B,
overlay0.341→0.020s. These are metadata-only timings. Query generation uses a
fake statement collector, **not actual Trino planning on1,200 physical snapshots**.
First-page scan count fell1,200→16; SQL bytes411,672→5,560. Backend regression
visits all1,200 segments in75 pinned pages, with no head re-resolution.

Hourly/daily data pages cap16snapshot scans. Monthly pages contain whole VN
calendar months, at most12months/32segments; a month split into more than32segments
requires coalescing/rebuild rather than an unbounded query. Aggregate quality/AQI
queries process batches of32snapshots and merge small server-side summaries;
they never fetch all historical measurement rows into Python. Dashboard rendering
retains a25,000-row/pollutant cap with an explicit scope error. Old small cursors
remain readable; oversized v1 cursors must restart. All v2 cursors pin one timeline.

Keeping every immutable prefix version is still quadratic in retained metadata.
Exact serialization size for this simulation is9,501,173,400B v1 vs623,969,400B
v2 across all1,200prefixes. This is a calculated encoding total, not physical
Iceberg file growth. Future archive policy must address version retention; no
release protocol delta-chain or automatic garbage collection was introduced.

## Snapshot lifecycle and blockers

`retention-month34.json` inventories actual registry, current/rollback timeline,
input, table-head and named snapshot references:48protected,0missing,0review
candidates, no delete candidates. Pure tests fail closed for missing/unknown
references and incomplete inventory. All source-table snapshots are held.
Unregistered head files are possible stages, not proven orphan files. Head file
bytes exclude retained-snapshot unions. No snapshot/file/object cleanup ran.

The first inventory attempt used standalone executors without configured AWS
region transport and failed. The read-only inventory now explicitly uses local[1],
matching supported host orchestration. A shell command denied Docker access and
the attempted live Chrome E2E was blocked at setsockopt by the sandbox; these
attempts are not counted as pass. Previous E2E evidence remains distinct.
Fresh-namespace history launch was also denied Docker access before any work.

Silver production hourly mean/EAC4 archive, station/proxy succeeded inputs,
unknown-clock migration, verified emission units/mapping and safe Airflow submit
transport remain upstream/runtime blockers. See `OBSERVATION-TIME-MIGRATION.md`
and the operational runbook. No production source or scheduler was enabled.

Additional read-only inventories: `retention-native.json` protects50 snapshots in
`gold` native/source references; `retention-pilot.json` protects177 for CAMS
pilot/rollback/input references. Both inventories complete with0missing references,
0review candidates and cleanup disabled. These per-schema protected counts overlap
on source tables; do not sum them as unique global snapshots. `serving-current.json`
also verifies current CAMS and hourly User/Admin contracts and native unverified
emission units after hardening.
