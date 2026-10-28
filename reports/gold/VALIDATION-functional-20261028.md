# Gold audit, fixes và readiness — 28/10/2026

Gold vẫn dùng hourly grain, Spark/Iceberg/Nessie/MinIO và Trino serving. Đã nghiệm thu trên stack development: multi-chunk historical serving, corrections/deletions, metric withdrawal, AQI fixtures 1h và dashboard. **Chưa production ready**: chưa có EAC4 production/hourly-mean Silver thật, station/proxy onboarding, emission-unit certification hoặc Airflow submit transport; full-archive throughput và bounded snapshot lifecycle chưa được chứng minh.

Báo cáo MVP trước đó được giữ ở [VALIDATION-MVP.md](VALIDATION-MVP.md). Kết quả hiện tại ưu tiên evidence trong [readiness/](readiness/); không suy pass từ báo cáo cũ. Các negative tests có Spark exit1 được ghi rõ dưới đây.

## 1. Re-audit và baseline

- Đọc DDL/jobs, AQI reference/engine/tests, release registry, backend repositories/routes/contracts, dashboard selectors/rendering và tài liệu Gold/v2.
- Baseline trước sửa: Gold **16 pass**; backend **11 pass, 1 fail, 2 errors**; frontend **19 pass**. Con số backend này là lần chạy thực của re-audit, khác lần báo cáo MVP đầu tiên 9 pass vì suite đã có thêm tests.
- Baseline stack integration và serving cũng được chạy lại, lưu cùng registry/snapshot evidence tại [baseline](readiness/baseline/). Không xóa hoặc reset các thay đổi hợp lệ có sẵn.
- Runtime: Spark3.5.4/Python3.8/Java11, Iceberg1.7.1, Nessie0.104.5, Trino476, Airflow2.10.5. Host khoảng15GiB RAM; Spark pilot local[1], heap2GiB.
- Actual Silver vẫn có ba CAMS standard time/grid rows của `EAC4-validation-*`; không phải production archive. WAQI live inputs rỗng; expected Ninjas `province_air_quality_*` chưa sẵn sàng. Succeeded native historical/emission inputs có thật.
- Schema audit so sánh ordered column names/types với executable DDL: **29 definitions, không drift trên bảy namespaces** trong [schema-audit.log](readiness/schema-audit.log). Nullability khi đọc Spark không được coi là PK/FK enforcement; ETL kiểm tra logical keys/FKs riêng.
- [Runtime after](readiness/runtime-after.json) giữ Silver readiness, hierarchy, published snapshot mappings, row counts và storage evidence. Airflow log symlink thay ngày do runtime; không sửa orchestration hiện có để che blocker.

## 2. Confirmed bugs và root causes

| Lỗi | Nguyên nhân | Sửa và bằng chứng |
| --- | --- | --- |
| Publish chunk mới làm historical default chỉ thấy một chunk | `gold_current_release` đại diện một scope; backend bắt request vừa một release | Thêm immutable timeline + atomic embedded-manifest pointer; dashboard tự compose disjoint published scopes |
| Overlap/correction có nguy cơ duplicate hoặc resurrect deleted input | Chỉ chọn rows/upsert không đủ để thay scope đã bị rút | Overlay thay toàn `[start,end)` của cùng compatible lane; ngoài scope giữ nguyên, withdrawal là tombstone |
| Monthly partial chunks không thể gộp bằng mean-of-means | Monthly materialization chỉ đại diện scope chunk | Historical monthly dùng canonical daily `concentration_sum`/`valid_hours`; `valid_days` là đủ expected slots, `observed_days` tách riêng; không tạo monthly AQI |
| Backend 1 failure/2 errors | Thiếu `DashboardService.get_analytics` và fixture ASGI `client` | Triển khai analytics/cache thật, route aliases/validation và isolated legacy fixture; giữ tests phát hiện lỗi, không xóa/bỏ qua |
| Withdraw toàn pollutant đổi compatibility | Dimension metric list được suy từ observations còn tồn tại | Contract v3 khai báo đầy đủ metric/unit/vertical policy; dimension giữ declared scope dù SO₂ không còn observation |
| Withdraw toàn pollutant làm SO₂ biến mất khỏi mart | Serving spine lấy distinct series/metric từ sparse facts | Declared-source spine lấy expected metric scope từ contract/dimensions; facts vẫn sparse, serving SO₂ NULL/missing |
| Policy ở thời kỳ khác chặn dashboard query hẹp | Resolve compatibility trên toàn timeline trước khi áp dụng requested dates | Select theo requested interval trước; metadata lịch sử lấy trong lane đã chọn, không chọn latest policy tùy tiện |
| QC/timestamp của pollutant cuối lấn pollutant khác khi pivot | Một field QC chung bị overwrite trong loop six pollutant rows | `metricQuality` giữ QC/reason/observation time/coverage từng pollutant; tooltip dùng đúng pollutant; wide summary là partial khi thiếu chất và không kế thừa coverage cuối |
| National concentration KPI có thể mean các province means với sample counts khác nhau | Projection làm mất trọng số khi tổng hợp lần hai | Gold KPI và analytics dùng actual sample weights; AQI không mean/sum across provinces/time |
| YoY gộp spatial/temporal scope không trùng baseline | Mean current scope gồm tỉnh/giờ không có dữ liệu năm trước | Matched province/calendar slots, loại unmatched/leap-day không có counterpart; giữ sample weights |
| Nhãn UTC cho daily/monthly Gold | UI/table/export label hardcoded dù metadata là VN calendar | Hiển thị/CSV dùng calendar timezone; hourly slots vẫn UTC; legend basis chuyển sang nhãn phân tích dễ đọc |
| Threshold metadata mặc định 0.95 cho mọi source | Hardcoded backend threshold | Chỉ resolve policy khi full contract hash khớp; không xác nhận được thì NULL, không áp current policy lên historical release |

**Unit/vertical conflict gần nhất là expected rejection.** Fixture cố ý đổi CO từ `model_surface` thành `surface` trái với `normalized-hourly-v3.json`. Adapter phải raise `Input unit/vertical support conflicts with declared metric policy`; test driver xác nhận pointer không đổi rồi exit0. Không nới validation, không sửa method/breakpoint. [Metric withdrawal result](readiness/metric-withdrawal.json) ghi cả expected failed Spark invocation và các assertions pass.

Frontend full-entrypoint audit còn phát hiện `npm test` dùng stale import path và bỏ sót `.mjs` suites: baseline thực của entrypoint là5pass/1file-error. Sau sửa harness, test YoY tái hiện150% thay vì200% vì province không có prior-year pair làm loãng phép so sánh. Giữ numerical assertions, cập nhật đường dẫn/public model fields; implementation nay so sánh matched province/calendar slots, loại unmatched giờ và không dùng Feb28 hai lần cho Feb29. Full suite sau sửa là34pass, gồm regression cases hourly/leap-day và UTC/VN-calendar labels. Các log trước sửa được giữ ở `frontend-default-before.txt` và `frontend-all-before-fix.txt`.

Trong quá trình triển khai, red tests đã phát hiện spine còn dùng observed metrics; harness cũng được sửa camelCase API keys, Python executable trong container và explicit reactivation khi lặp rollback test. Những lượt fail trung gian không được dùng làm evidence pass; báo cáo dùng kết quả rerun cuối.

## 3. Implementation, migration và file groups

- **Storage/publication:** `lakehouse/gold/gold.sql`, `spark/jobs/gold/{timeline,publication,runtime,run,activate_release,manage_timeline}.py`.
- **Contracts/ETL:** `adapters.py`, `marts.py`, `validation.py`, `source_contracts.py`, `station_proxy.py`; versioned normalized v1/v2/v3, color/unit-review/geography contracts.
- **Backend:** Gold history/serving/dashboard/colors/contracts repositories, dashboard/Gold routes, schemas, analytics/service and regression fixtures/tests.
- **Frontend:** Gold source mode, hourly/date controls, weighted selectors, concentration scale/legend, per-pollutant tooltip QC, Admin `GoldAnalyticsPanel` và User/Admin projections.
- **Acceptance:** `scripts/test_gold_{history,pipeline,metric_withdrawal,timeline_recovery,operations}.py`, `verify_gold_{serving,readiness}.py`, `check_gold_history_ui.mjs`, Spark schema/fixture/failure/measurement tests.
- **Docs:** Gold README/SCHEMA/RUNBOOK, archived v2 schema, implementation-plan links và báo cáo này.

Migration là additive: thêm `gold_timeline`, `gold_timeline_current`, `fact_measurement_provenance`, tổng29 definitions. Bootstrap không ALTER old facts hoặc thay old values/methods. Legacy pointer/registry vẫn tồn tại. Seed migration chỉ nhận release đang visible trong legacy pointer, không import mọi registered stage. Rollback phục hồi whole timeline manifest; giữ tất cả referenced snapshots.

Không xóa Bronze/Silver thật, snapshots hoặc published releases; mutation/delete tests chỉ chạy trên fixture namespaces `gold_test*`. Không bật Gold pilot/fixtures làm production default, không đổi Supabase storage và không publish validation data vào `gold.air_quality`.

## 4. Trạng thái từng phase

| Phase | Status | Phạm vi đã kiểm chứng / giới hạn |
| --- | --- | --- |
| 0 Re-audit | **Implemented and verified** | Actual code/catalog + captured baseline; phân biệt source readiness với DDL |
| 1 Historical serving P0 | **Implemented and verified** | Three chunks, cross-month/year, overlap/correction/delete, missing scope, pagination, concurrent publish, rollback/withdrawal và real API; full archive performance còn tách riêng |
| 2 Backend regression P0 | **Implemented and verified** | Full backend suite, legacy analytics và real Gold API contracts |
| 3 Future Silver 1h P0 | **Implemented and verified** | Explicit interval/source clocks/provenance fixtures; 24 hourly slots + hourly/daily AQI. Production source vẫn bị gate |
| 4 Dashboard P1 | **Implemented and verified** | Scoped MVP: fixed versioned six-pollutant scales, weighted KPI/trends/ranking, daily AQI distribution, source measurement coverage/QC và live User/Admin E2E |
| 5 Station/proxy P1 | **Blocked by upstream/runtime** | Pure transforms/isolated fixtures có; chưa có succeeded Silver live inputs/mapping, chưa kích hoạt Spark production adapter hoặc Ninjas unit migration |
| 6 Operations P1/P2 | **Implemented but not fully validated** | Single-host runner, bounded builds, failure recovery/rollback, dry-run retention và limited telemetry. Distributed writers/cleanup/archive scale chưa nghiệm thu |
| 6 Airflow P2 | **Blocked by upstream/runtime** | Python3.12.9, không Spark CLI/job mounts/tested transport; không gắn Docker socket hoặc tạo DAG giả |
| 6 Emissions P2 | **Blocked by upstream/runtime** | Native facts/mart/API giữ unit NULL/unverified và GADM unallocated; chưa có metadata chứng nhận để normalize/allocate |
| 7 Documentation | **Implemented and verified** | Physical schema tách archived wide-v2 target; keys/partitions/release/history/source contracts và runbook khớp implementation |
| 8 Acceptance | **Implemented but not fully validated** | Các suites và development-stack scenarios bên dưới pass; production-data/scale acceptance chưa đủ điều kiện |

PM1/AOD/weather/column Gold analytics và advanced annual Admin projections: **Deferred, with technical justification**. Chưa có reviewed metric-kind/unit/vertical/aggregation contracts cho branch này; không áp arithmetic mean bừa cho vector/column và không đưa chúng vào AQI. Existing legacy choices không được gán Gold data giả.

## 5. Kết quả kiểm thử thực chạy

| Nhóm | Kết quả | Evidence |
| --- | --- | --- |
| Gold AQI/time/spatial/source/timeline unit | **23 pass, 0 fail** | [gold-after.txt](readiness/gold-after.txt) |
| Full backend regression | **23 pass, 0 fail/error/skip** | [backend-after.txt](readiness/backend-after.txt); một Starlette deprecation warning |
| Full frontend entrypoint (.ts + .mjs) | **34 pass, 0 fail/skip** | [frontend-all-after.txt](readiness/frontend-all-after.txt) |
| User/Admin TypeScript + Vite Gold build | **Pass** | [frontend-build.txt](readiness/frontend-build.txt) |
| Real Spark replay/correction/delete/QC/failure/rollback + partition boundaries | **Pass** | [pipeline checks](readiness/pipeline-checks.json), [latest log](readiness/pipeline-after.txt) |
| Real multi-chunk Spark/Iceberg/Trino/FastAPI | **Pass** | [history checks](readiness/history-checks.json), [latest run](readiness/history-final.txt) |
| Complete SO₂ withdrawal + wrong vertical metadata rejection | **Pass** | [metric-withdrawal.json](readiness/metric-withdrawal.json) |
| Failure after timeline registry, before pointer | **Pass** | [timeline-recovery.json](readiness/timeline-recovery.json): staged view unavailable, retry activates exact immutable view |
| Incompatible spatial policy + explicit rollback + bounded telemetry | **Pass in fixture scope** | [operations-checks.json](readiness/operations-checks.json) |
| Real historical API/source filters/analytics/map/per-pollutant QC | **Pass** | [final-serving.json](readiness/final-serving.json) |
| Live Chrome User/Admin E2E | **Pass** | [history-ui.json](readiness/history-ui.json), [User](readiness/history-user.png), [Admin](readiness/history-admin-monthly.png) |

Các suite đơn vị không thay thế integration/E2E. Schema audit và source readiness có evidence riêng. Không cộng số scenarios thành số pytest tests hoặc coi negative Spark exit1 là suite failure.

### CAMS 3h và AQI reference

Pilot mới nhất: **612 concentration rows**, 34 series, source timestamps00/03/06UTC thực, cadence180/instantaneous; **816 hourly AQI overall rows và34 daily overall rows đều không hợp lệ/NULL** đúng eligibility. Serving hourly4896 rows; daily/monthly/quality mỗi204 rows. Expected serving slots không phải concentration observations. Spatial weights được cache theo grid/boundary/method; 34 provinces cộng hai archipelago children trong geography, không thành36provinces.

[Runtime after](readiness/runtime-after.json), [CAMS process log](readiness/cams-process.log) giữ snapshots/counts và telemetry. Không forward-fill, resample hoặc coi model level60 là station observation.

Engine giữ method `vn-aqi-1459-2019-project-v1`, PDF checksum `968c4cbb9bf5cf03e4a9bf30850afd8695d130f767324ac57ca02e2d54a48c26`. Tests cover breakpoints, half-up/invalid/zero, hai NowCast branches, fixed12slots/missing ages, PM participation, O3 rolling8h qua midnight, conservative daily completeness, ties và VN calendar boundaries. Ví dụ PDF NO2=118.7 in60 nhưng công thức59.35→59 vẫn được ghi nhận; không sửa engine để khớp lỗi số học. Không có thay đổi AQI method/breakpoints trong task này.

### Hourly mean và historical scenarios

- 48 hourly means +11halo trong isolated fixture tiếp tục cho48 AQI giờ và2 AQI ngày hợp lệ. Fixture7ngày cho168 AQI giờ/7AQI ngày.
- Three chunks Dec30/Dec31/Jan1, publish A→C→B: lúc thiếu B đọc48hourly rows +missing interval; đủ ba chunk đọc**72hourly,3daily,2monthly**. PM25 monthly sample counts ban đầu48/24; sau deletion47/24, không mean partial averages.
- Correction chunk đầu và rebuild halo; delete PM25 ở chunk giữa và O3 ở23hlocal; sparse facts cũ không xuất hiện trong selected new scope. Old immutable timeline vẫn đọc values cũ.
- Request đang chạy giữ view72rows khi concurrent publish D; request mới thấy96rows. Cursor giữ timeline cũ. Rollback whole view bỏ D khỏi current view, withdrawal B trả48rows +withdrawn_scope, không resurrect older B.
- Complete SO₂ withdrawal: compatibility vẫn **một lane**; facts không có SO₂ observations mới, serving giữ**48 SO₂ NULL/missing slots**, daily valid_hours0, monthly valueNULL. Other pollutants/AQI không bị mất; old snapshot SO₂=10 còn đọc được.
- Broad multi-year API bounds trả dữ liệu đã publish và missing scopes rõ ràng. Đây là nghiệm thu **query contract**, không phải tuyên bố đã có nhiều năm production data. Unrelated policy thời kỳ khác không chặn narrow request; incompatible overlapping scopes vẫn cần explicit lane.
- Admin E2E xác nhận**3 series-days**, không18 pollutant-rows; PM25 **71/72** valid slots, counts2good/1moderate. Map34 và hour picker24, hourly/daily/monthly requestsHTTP200, khôngJSerrors hoặc silent sample fallback. UI và [CSV tháng](readiness/history-monthly.csv) ghi đúng VN calendar, hourly vẫn UTC.

## 6. Performance và snapshot safety

| Pilot | Runtime | Maximum child RSS | Output / diagnostics |
| --- | --- | --- | --- |
| Real CAMS bounded1day | 36.615s process;33.847s build | 1,779,380KiB ≈1.70GiB | 612facts,415tasks, shuffle read/write2,273,812B; global max/median task337/9ms |
| Synthetic1location7days | 29.416s process;26.49s build | 1,587,084KiB ≈1.51GiB | 1,074facts+provenance incl halo,168AQIh/7AQId,291tasks, shuffle read1,692,385B/write1,692,537B |

7day storage: facts2files/18,940B; provenance2/16,801B; hourly mart2/23,033B; daily1/12,375B; monthly1/7,357B. UTC month boundary explains two partitions/files. Historical query pilot≈0.126s. Measured timeline13versions≈53,788manifest bytes, max≈5,532B/version. See [operations](readiness/operations-checks.json).

Child RSS không phải tổng peak Docker memory; global task runtime ratios không chứng minh stage skew. Chưa đo riêng Python driver collect peak, large grid/archive throughput hoặc latency với hàng nghìn chunk. Driver collection có budget100,000rows; vượt phải giảm chunk. Host runner đã nhận explicit adapter/Silver-schema/contract, có isolation guard cho fixtures và không mặc định biến normalized source thành CAMS. Hai chunk1h tổng7ngày và replay được kiểm tra qua `host-runner.txt`, `host-runner-replay.txt` và final-serving counts. Default host chunks7days, bound1–31days. Không chạy full archive.

Retention chỉ **dry run**, bảo vệ all registry/rollback referenced snapshots. Không chạy `expire_snapshots`/`remove_orphan_files`; không xóa production snapshots. Iceberg [DDL references](https://iceberg.apache.org/docs/1.7.1/spark-ddl/#branching-and-tagging-ddl) và [maintenance procedures](https://iceberg.apache.org/docs/1.7.1/spark-procedures/#expire_snapshots) là căn cứ đánh giá khả năng, chưa phải bằng chứng tag lifecycle đã được triển khai cùng Nessie. Full embedded manifests và giữ mọi rollback version còn có storage-growth risk; cần benchmark/archive policy trước cleanup production.

## 7. Blockers và bước còn lại

1. **Production concentration/AQI:** cần succeeded Silver source thật với reviewed temporal/unit/QC/location contract. 60-minute instantaneous/provider snapshot vẫn ineligible; không đổi label để vượt gate.
2. **Station/proxy:** WAQI cần verified station mapping; Ninjas cần actual succeeded Silver tables, provenance/unit certification và reviewed nullable-observation-time migration. Provider xác nhận concentration [µg/m³](https://api-ninjas.com/api/airquality); không tự nhân1000 từ label cũ chưa kiểm chứng. Pure transforms/fixtures không được tính là production adapter đã chạy.
3. **Operations:** giữ host runner một Compose writer; [Airflow transport audit](readiness/airflow-transport.json) xác nhận thiếu CLI/mount/transport. Không có distributed lock hoặc DAG production được nghiệm thu.
4. **Archive/storage:** cần tăng dần pilot trên production inputs, đo per-stage skew/driver memory/thousands-of-chunks queries và thiết kế retention/archive trước cho phép cleanup.
5. **Emissions:** existing native facts giữ WAQI179,843 provider rows, emissions aggregates17,280, point/GADM observations32,384 và national native mart216; units vẫn unverified, không hiển thị tonnes hoặc phân bổ GADM bằng centroid.

Deployment/default production source chưa được thay đổi. Không có input/scale evidence để tuyên bố toàn Gold production ready. Quy trình vận hành và acceptance commands: [RUNBOOK](../../lakehouse/gold/RUNBOOK.md); deployed contracts/partitions: [SCHEMA](../../lakehouse/gold/SCHEMA.md).

Machine-readable acceptance summary: [SUMMARY.json](readiness/SUMMARY.json). Các preview servers chỉ dùng local validation fixture; không phải deployment production.
