"""Validate retained execution evidence and regenerate migration acceptance artifacts.

Read-only against lakehouse/source data; writes only local report/evidence files.
Run from any directory with the project Python environment.
"""
import os
from pathlib import Path
os.chdir(Path(__file__).resolve().parents[1])
from pathlib import Path
import json,re
root=Path('reports/medallion_migration')
x=json.loads((root/'landing-inventory.json').read_text())
grib=json.loads((root/'grib/inventory.json').read_text())
registry=json.loads((root/'variable-registry.json').read_text())
num=json.loads((root/'numerical-gold.json').read_text())
lines=['# Medallion migration validation — 2026-10-31','', '## Acceptance and evidence scope','',
'Bounded real-source Landing → Bronze → Silver → Gold processing passed for five populated datasets. CAMS archive integrity was checked by rehashing every current file against retained full ecCodes audit results. Three real hours, rather than the full 23-year archive, were materialized through Silver and Gold. No production full-archive backfill is claimed. APIs, frontend and dashboard code were not modified. Existing raw data, legacy cubes and published release snapshots were preserved.', '',
'ERA5 and live-provider production acceptance remain blocked by missing input. Climate TRACE native quantities are usable at their native grain, but verified mass-unit analytics remain blocked because current CSV files contain no unit declaration. The overall system is **accepted for bounded source-aware integration; not certified for a full production archive rollout**.', '', '## Dataset acceptance matrix','',
'| Dataset | Files / bytes | Landing | Bronze | Silver | Gold | Final status |','|---|---:|---|---|---|---|---|']
for d in x['datasets']:
 name=d['dataset_id'];count=d['file_count'];size=d['total_bytes']
 if name=='.gitkeep':continue
 if not count:states=['empty','blocked','blocked','blocked','missing source; no observations invented']
 elif name=='CAMS/EAC4':states=['full checksum/metadata','real three-hour pilot + replay','20 variables, 34,500 values','612 concentration + 1,428 environmental rows','passed real bounded data']
 elif name.startswith('reference/'):states=['parsed + hashed','real existing batch verified','identity/geometry/hierarchy checked','34 roots + 2 components in CAMS dimensions','passed real data']
 elif name=='waqi/historical':states=['CSV structure + hashes','real existing batch verified','179,843 provider daily entries','179,843 native daily entries','passed native provider indices; not concentration']
 else:states=['CSV structure + hashes','real existing batch verified','17,280 aggregates + 32,384 sources','native facts + 216 country-period rows','passed native semantics; mass units unverified']
 lines.append('| '+name+' | '+str(count)+' / '+str(size)+' | '+' | '.join(states)+' |')
lines+=['| WAQI live | no local collection | unavailable | implemented Supabase adapter | fixture/regression only | not production validated | blocked by missing input |','| API Ninjas | no local collection | unavailable | implemented Supabase adapter | fixture/regression only | not production validated | blocked by missing input |','',
'Inventory details: [landing-inventory.json](landing-inventory.json), [runtime-state.txt](runtime-state.txt), [all-silver-audit.txt](all-silver-audit.txt). All 3,414 audited Bronze objects matched SHA-256. The two geography datasets share dimensions but retain distinct source lineage. Unknown future datasets are discovered dynamically and held as raw-only pending a reviewed adapter; they are not assigned CAMS semantics.', '',
'## All twenty CAMS variables and normalization','',
'Every field has 201,622 distinct aligned timestamps from 2003-01-01 00:00 UTC through 2025-12-31 21:00 UTC; no missing interior hourly slots or duplicate messages. The final two hours of 2025 are outside available source coverage, not fabricated. Grid dimensions are 23 × 25 (575 ordered points). The six hybrid fields are at model level 60. Source metadata is instantaneous analysis, step zero, matching valid/reference time.', '',
'| Metric | paramId / shortName | Native unit | Standard unit | Formula | Vertical support |','|---|---|---|---|---|---|']
metadata_by_metric={g['file'].split('_2003')[0]:g for g in grib}
for r in [r for r in registry if r['dataset_id']=='CAMS/EAC4']:
 g=metadata_by_metric[r['source_variable']]
 # Join by source identity; lexical filename and metric ordering differ for PM1/PM10.
 c=r['source_variable'];formula='native × local density × 10⁹' if c in ('co','no2','so2','o3') else 'native × '+str(r['conversion_parameters']['scale'])+' + '+str(r['conversion_parameters']['offset'])
 lines.append(f"| {c} | {g['paramId']} / {g['shortName']} | {r['native_unit']} | {r['standard_unit']} | {formula} | {g['typeOfLevel']}:{g['level']} |")
lines+=['',
'Density uses p_half = A + B × surface pressure; p_full60 = (p_half59 + p_half60)/2; Tv = T × [1 + (1−0.621981)/0.621981 × q]; rho = p_full60 / (287.05 × Tv). The original GRIB L60 coefficients are validated against the retained ECMWF reference. Gas conversion is per time/grid point before area aggregation. Mean sea-level pressure is not used for density. Original bytes and native values remain recoverable via Bronze hash, timestamp and grid-point index; standardized float arrays are not converted again in Gold.', '',
'Unit/variable registry: [variable-registry.json](variable-registry.json). Full file-level metadata, hashes, grid ordering and QC evidence: [grib/inventory.json](grib/inventory.json), [grib-audit.txt](grib-audit.txt). Reference: [ECMWF CAMS documentation](https://confluence.ecmwf.int/pages/viewpage.action?pageId=188040388).', '',
'## Real numerical reconciliation','',
f"Independent ecCodes decoding, conversion and recorded area weights were compared with Trino Gold results for {num['compared_values']:,} province-hour-metric values covering all {num['metrics']} variables. Maximum relative difference was {num['max_relative_error']:.3g}, consistent with final Silver float32 storage. Independent Bronze-to-Silver checks covered all 34,500 scalar pilot values; maximum relative float32 error was 5.96e-8. No missing values were replaced by zero; three legitimate PM zeros were retained.", '',
'[numerical-gold.json](numerical-gold.json) retains raw point examples, independent province means, Gold results, spatial weight sums, errors and release snapshots. [cams-real-integration.txt](cams-real-integration.txt) verifies raw checksums, grid alignment, all conversions, MERGE retry identity, successful-run skipping and unchanged legacy snapshots.', '',
'## Gold facts, marts and release provenance','',
'The concentration pilot contains 34 province series × 3 hours × 6 pollutants = 612 sparse observations. Environmental facts contain 34 × 3 × 14 = 1,428 observations. The corresponding daily and monthly environmental marts each expect 476 rows (34 × 14); the retained SQL checks verify sum/count/mean consistency for matched mart rows, but do not separately certify row-count completeness for these two new marts. Area coverage gates apply before publication; parent geometry is unioned with linked archipelago components without double counting. Six concentration metrics and fourteen physical metrics remain separate. Wind components retain signed vector-component semantics; column burdens retain mg/m²; model-level temperature/humidity retain model-level identity.', '',
'Daily/monthly statistics describe available instantaneous samples. They are not measured daily mean concentrations. Monthly concentration means use sum/count, and environmental monthly means aggregate individual hourly samples. No monthly AQI is invented. Gold source lineage includes dataset, input snapshots and run IDs; environmental rows also carry cadence, vertical support, QC reason and coverage. Additive DDL leaves legacy release snapshot maps readable.', '',
f"Initial twenty-metric release: `{num['release_id']}` in `gold_test_medallion_hourly`. Its full input/output snapshot map is retained in the numerical evidence. Native release: `2c98e552e69817f96189e4b67b650de5a707e1f0db161066f44bc906059f352b` in `gold_test_medallion_native`. Latest runner release IDs and stage timings are retained under `runner/` and summarized below when available.", '',
'## VN_AQI eligibility and method verification','',
'The retained Decision 1459 reference SHA-256 is `968c4cbb9bf5cf03e4a9bf30850afd8695d130f767324ac57ca02e2d54a48c26`; method version is `vn-aqi-1459-2019-project-v1`. The official document remains available and authoritative monitoring sites continue citing it; the checked sources did not reveal a replacement. This is a scoped current-use check, not a legal-register certification. [Official guidance](https://vea.mae.gov.vn/Data/files/QD%201459%20TCMT%20ngay%2012_11_2019%20AQI%281%29.pdf).', '',
'Actual CAMS hourly/daily calculated AQI is NULL: hourly instantaneous model analyses do not satisfy verified monitoring-station hourly-mean eligibility. Concentrations remain available. The mathematical fixture path produces 48 hourly and 2 daily valid AQI values, separately labeled as isolated eligible-mean fixtures. PM participation, both NowCast branches, age-preserving missing slots, zero handling, CO µg/m³ breakpoints, O3 rolling 8-hour bases/cutoff, local-day boundaries, ties and rounding are covered by golden tests. The 24/24 daily completeness gate is a versioned conservative project policy. The PDF printed NO2 example gives 60 for 118.7 while interpolation gives 59.35 → 59; the documented formula takes precedence.', '',
'## Regression diagnosis and fixes','',
'The reported outer-driver failure was not reproduced: the retained driver JSON completes its final assertions. Inner Spark exit codes 1 at failed_stage and failed_after_registry are intentional negative tests. The resumed outer driver explicitly exited 0; see [release-regression-resumed.exit](release-regression-resumed.exit) and [release-regression-resumed.txt](release-regression-resumed.txt). No assertions were weakened. Corrections, withdrawals, failed-pointer safety, registry recovery, historical old-release reads, rollback and month-boundary builds passed.', '',
'Confirmed defects fixed: obsolete Silver hour%3 rejection; missing hourly source identity/Gold cadence contract; missing fourteen-metric Gold path; an initial additive DDL quotation typo (retained failed log followed by repaired successful run); missing environmental vertical/QC fields; host runner stopping before Gold; and native publication ordering that could publish before all selected native Silver dependencies completed. The last condition now defers shared native publication and is covered by a failure-injection runner unit test. The initial Airflow unit invocation lacked PYTHONPATH; rerunning with the documented DAG path passed. A sandbox Trino denial was resolved through mandatory command escalation, not a service fallback.', '',
'## Final unit/regression evidence','',
'| Suite | Passed | Failed/errors | Skips | Evidence |','|---|---:|---:|---:|---|']
for title,name in [('Framework','framework-acceptance-final.txt'),('Silver','silver-acceptance-final.txt'),('Gold','gold-acceptance-final.txt'),('Airflow config','airflow-acceptance-final.txt')]:
 text=(root/name).read_text();m=re.search(r'Ran (\d+) tests?',text);n=int(m[1]) if m else 0
 lines.append(f'| {title} | {n if text.rstrip().endswith("OK") else 0} | {0 if text.rstrip().endswith("OK") else "see log"} | 0 | [{name}]({name}) |')
lines+=['',
'Integration evidence distinguishes real available input from isolated fixtures. Read-only Silver audit passed five datasets; independent Gold comparison passed twenty metrics; native real Gold passed 179,843 WAQI daily records, 17,280 emission aggregates and 32,384 source observations. Empty provider branches are not counted as production successes.', '',
'## Resources, operations and limitations','',
'The measured original twenty-metric Gold pilot completed in 36.28 s with local[1], 2 GiB configured driver heap, 612 bounded driver-collected concentration rows and one collect call. Its phase durations and output snapshot IDs are in [cams-gold-environmental-repaired.txt](cams-gold-environmental-repaired.txt). Spark worker configuration is 2 cores/2 GiB; source inventory totals approximately 8.5 GB. These are bounded-pilot measurements, not extrapolated archive throughput. Peak RSS, full-archive storage/shuffle and multi-host writer behavior are not certified. Environmental mart sum/count/mean checks passed, while a separate exact row-count assertion for these new marts remains an acceptance limitation. The process uses local advisory locks and a single writer; distributed locking remains a production prerequisite for multiple orchestration hosts.', '',
'No full archive backfill was launched. A full hourly archive entails 201,622 cube rows and about 2.32 billion scalar fields; unbounded explode/driver collection is prohibited. Silver keeps 512-timestep commit chunks; Gold scopes stay at 1..31 local days with halo history. Use measured larger chunks before production expansion. Source corrections/deletions use existing dependency invalidation and historical timeline publication; published references and snapshots must not be deleted.', '',
'Climate TRACE unit metadata, live provider payloads/timestamps, ERA5 source contracts, full-archive runtime/storage benchmarking and production hourly backfill remain open upstream/operational work. New environmental tables are not exposed by APIs; any API adoption is a future change outside this task. The native Gold script currently requires both initialized WAQI and Climate TRACE tables, documented as an onboarding dependency.', '',
'## Changed implementation and operating guide','',
'Changes cover `scripts/inventory_landing.py`, `audit_medallion_grib.py`, `run_medallion.py`, `verify_medallion_gold.py`, framework tests, Silver CAMS cadence/version and tests, Gold hourly contract/runner, environmental facts/marts and additive DDL. Existing Bronze immutable storage, Silver physics, native source adapters, VN_AQI engine and release/timeline architecture were reused. See [medallion operations](../../docs/lakehouse/medallion-modernization.md) for execution, retry, contract and backfill details. All evidence, including failed intermediate attempts, remains retained.']

# Validate outer-driver outcomes separately from expected inner failure injections.
for marker in ['runner-driver.exit','runner-final-native-driver.exit','numerical-runner-gold.exit','release-regression-resumed.exit']:
 assert (root/marker).read_text().strip()=='0',marker
runner=json.loads((root/'runner/orchestration-results.json').read_text())
native=json.loads((root/'runner-final-native/orchestration-results.json').read_text())
final_numeric=json.loads((root/'numerical-runner-gold.json').read_text())
assert final_numeric['compared_values']==2040 and final_numeric['metrics']==20
assert final_numeric['max_relative_error']<1e-6
assert final_numeric['period_checks']=={'daily':'passed_sum_count_average','monthly':'passed_sum_count_average'}
assert len([r for r in runner if r['dataset']!='ERA5/single_levels'])==5
assert next(r for r in runner if r['dataset']=='ERA5/single_levels')['status']=='blocked_missing_source'
assert all(r['gold']['exit_code']==0 for r in native)
assert all(r['bronze']['exit_code']==r['silver']['exit_code']==0 for r in native)
commands=json.loads((root/'final-test-commands.json').read_text())
assert all(r['exit_code']==0 for r in commands)
unit_count=0
for command in commands:
 log=Path(command['log']).read_text()
 assert log.rstrip().endswith('OK'),command['suite']
 unit_count+=int(re.search(r'Ran (\d+) tests?',log)[1])
assert unit_count==84
current_files={Path(f['path']).name:f for d in x['datasets'] if d['dataset_id']=='CAMS/EAC4' for f in d['files']}
assert len(current_files)==20
assert all(current_files[g['file']]['sha256']==g['source_sha256'] for g in grib)
assert sum(d['file_count'] for d in x['datasets'])==3414

native_log=Path(native[0]['gold']['log']).read_text()
match=re.search(r'GOLD_NATIVE_(?:PUBLISHED|REPLAY) ([0-9a-f]{64})',native_log)
assert match
native_release=match[1]
latest_native_silver=max(Path(r['silver']['log']).name.split('-20')[-1] for r in native)
assert Path(native[0]['gold']['log']).name.split('-20')[-1]>latest_native_silver
lines+=['','## Final execution reconciliation','',
'Both interrupted jobs finished before final recovery. No duplicate writer was launched. The temporary native verification script exists, and its recorded driver exit is 0. Reproduction no longer depends on it: use the project runner commands in the operations guide.', '',
'| Operation | Outer exit | Result | Evidence |','|---|---:|---|---|',
'| All-dataset runner | 0 | Five populated datasets passed; empty ERA5 reported independently | [runner results](runner/orchestration-results.json) |',
'| Final native dependency ordering | 0 | Both Silver stages completed before shared native Gold publication | [native results](runner-final-native/orchestration-results.json) |',
'| Independent runner Gold verification | 0 | 2,040 values, 20 metrics; daily/monthly statistics passed | [numerical results](numerical-runner-gold.json) |',
'| Correction/deletion/publication/rollback regression | 0 | Expected negative stages rejected; outer driver passed | [regression output](release-regression-resumed.txt) |','',
'Final runner CAMS release: `'+final_numeric['release_id']+'` in `gold_test_medallion_runner`. Final native release: `'+native_release+'` in the same namespace on its separate native channel. The numerical evidence retains the CAMS current-pointer snapshot map captured at verification time. Native and CAMS channels do not replace one another. Current live pointers were not re-queried after the final interruption because Docker access is now sandbox-denied; this does not replace the retained successful runtime checks with a claim of a fresh live check.', '',
'The runner CAMS pilot took 30.356 seconds including Bronze/Silver replay checks; its Gold stage took 40.258 seconds including Spark startup. Final native replay took 17.347 seconds. Trino reported one environmental hourly data file of 19,830 bytes for the checked test table at that time. These are bounded observed measurements, not estimates of archive performance.', '',
'Final cheap suites: 84 tests passed, zero failures, zero errors, zero skips. Exact commands, environment overrides and exit codes: [final-test-commands.json](final-test-commands.json). Expensive integration runs were reused because their affected transformation code was unchanged after successful execution. Final documentation review corrected a PM1/PM10 report-row join error; parameter IDs now join by metric identity rather than list order. The underlying transformation and numerical verification had always used parameter identities.', '',
'### Consistent acceptance statuses','',
'| Source | Real-data status | Fixture status | Remaining blocker |','|---|---|---|---|',
'| CAMS hourly, all 20 variables | Implemented and verified (bounded three-hour path) | Implemented and verified for scientific rejection/AQI eligibility | Full production archive backfill and resource certification |',
'| WAQI historical | Implemented and verified | Implemented and verified for malformed indices | None for native daily index use |',
'| Climate TRACE | Implemented and verified for native quantities | Implemented and verified for period/nonfinite rejection | Source units unverified for standardized mass analytics |',
'| Both administrative sources | Implemented and verified through shared Gold dimensions | Implemented and verified for hierarchy/spatial invariants | Standalone Gold facts: Not applicable |',
'| ERA5 | Blocked by missing input | Not applicable: no scientifically reviewed ERA5 contract | Empty Landing directory |',
'| WAQI live / API Ninjas | Blocked by missing input | Implemented and verified by retained provider/unit regression suites; production payloads not verified | Empty local collections and source-specific onboarding evidence |','',
'Future additional datasets remain implemented at raw discovery/Bronze capability and are not fully validated for Silver/Gold until an adapter is reviewed. No arbitrary new source is promoted through a generic concentration transform.', '',
'### Reproducible final validation','',
'```bash',
'backend/.venv/bin/python scripts/finalize_medallion_acceptance.py',
'backend/.venv/bin/python scripts/run_medallion.py --execute --gold --dataset climate_trace/climate_trace_vietnam --dataset waqi/historical --output reports/medallion_migration/runner-final-native',
'```','',
'The second command requires the approved development Docker environment and reuses retained checkpoints. It must run with no other writer. The first command validates retained evidence without Docker or network access.']
(root/'VALIDATION.md').write_text('\n'.join(lines)+'\n')
summary=dict(status='bounded_available_datasets_verified',unit_tests_passed=84,unit_tests_failed=0,unit_test_errors=0,unit_tests_skipped=0,
 cams_release_id=final_numeric['release_id'],native_release_id=native_release,
 numerical_values=2040,numerical_max_relative_error=final_numeric['max_relative_error'],
 runner_exit_code=0,native_runner_exit_code=0,gold_regression_exit_code=0,
 blocked_sources=['ERA5: missing input','WAQI live: missing local input','API Ninjas: missing local input'],
 production_limitations=['Climate TRACE units unverified','Full archive backfill/resource certification outstanding','Current Docker access sandbox-denied','New environmental mart row-count completeness not separately asserted'])
(root/'acceptance-summary.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps(summary,indent=2))
