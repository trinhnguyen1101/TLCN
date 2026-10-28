# Gold runbook

Chạy từ root repository trên host Compose. Không chạy Silver và Gold writers đồng thời.
Spark driver dùng local[1], 2 GiB heap; Python 3.8/Java11 của image hiện có, không cần dependency Gold mới.
Engine thuần Python; spatial dùng Shapely đã có. Pilot đọc sáu biến và sampled bridge indices,
không explode archive. Spatial aggregate Spark, AQI group theo series trên workers.
Adapter hiện collect kết quả province/time bounded về driver để chuẩn hóa dimension identities;
guard100.000rows gồm11hhalo. Bắt đầu backfill chunk7ngày. Fixture34×6×31ngày
vượt guard nên đã đo bằng16+15ngày, không tăng memory/row limit.31ngày là CLI
scope ceiling, không phải bảo đảm mọi source vừa memory. Xem benchmark thực tại
[performance](../../reports/gold/performance/README.md).

## Chạy pilot và production

```bash
# CAMS validation thật, cách ly hoàn toàn khỏi gold production.
python3 scripts/run_gold.py --schema gold_pilot \
  --dataset-id cbb7d021543ec806863f7da49793290e7ea2b1c71c169a717f6a01d64418ed61 \
  --allow-validation --start-date 2003-01-01 --end-date 2003-01-02

# Native WAQI/Climate TRACE thật; independent channel.
docker compose exec -T spark-master /opt/spark/bin/spark-submit \
  --master 'local[1]' --driver-memory 2g \
  /opt/spark/work-dir/jobs/gold/native_sources.py
```

Production CAMS cùng runner, `--schema gold`, production dataset ID có source_version `EAC4`, bỏ
`--allow-validation`. Hiện dataset đó chưa được xác nhận tồn tại: command phải fail, không chọn
validation dataset thay thế. `--start-date/--end-date` là ngày Việt Nam, end exclusive.
Native branch đọc toàn bộ Silver native hiện có, chỉ khoảng 230k facts trong pilot; cần bổ sung
chunking riêng khi tăng kích thước, không áp limit này cho archive concentration.

## Fixture 1h và kiểm thử

```bash
backend/.venv/bin/python -m unittest discover -s spark/jobs/gold/tests -v

docker compose exec -T spark-master /opt/spark/bin/spark-submit \
  --master 'local[1]' --driver-memory 2g \
  /opt/spark/work-dir/jobs/gold/tests/prepare_hourly_fixture.py

backend/.venv/bin/python scripts/test_gold_pipeline.py
backend/.venv/bin/python scripts/verify_gold_serving.py
```

`gold_test_silver` sao chép geography thật, ghi rõ source snapshot trong log; concentration fixture
có dataset `hourly_fixture_only`, source `hourly_fixture`, run `fixture_not_production`.
Runner bắt buộc cả input/output namespace `gold_test*` khi `--fixture`.
`test_gold_pipeline.py` chỉ sửa/xóa concentration ở test namespace, restore sau kiểm thử.
Không đưa các namespace này vào cấu hình production hoặc export chúng dưới nhãn observation thật.

## Incremental, correction, deletion và backfill

Release nhận input snapshot IDs, contract hash, hash code+DDL, method và explicit scope;
identity deterministic. Replay một registry release không ghi lại tables. Correction/deletion tạo
snapshot đầu vào mới, build lại toàn scope từ Silver, thay sparse facts bằng nội dung mới;
không chỉ MERGE những key còn xuất hiện. Không có calendar NULL facts được sinh để lấp chỗ.
Input rỗng toàn scope bị chặn publish; cần xử lý withdrawal/unpublish có review thay vì âm thầm
xem dữ liệu cũ là bản thu thập mới. Withdrawal dùng timeline tombstone; không xóa facts hoặc snapshots.

Lấy actual changed-hour inventory từ upstream/changelog; không giả định mọi late data nằm trong lookback.
`spark/jobs/gold/incremental.py:invalidation_scope` mở rộng tới h+11 cho PM và h+7 cho O3,
bao phủ local days liên quan, rồi cộng halo input 11h trước day start. Rebuild toàn affected days
và monthly marts của release scope. Month/unit/method/geometry changes cần rebuild các scope liên quan.
Backfill nhiều chunk dùng host runner; mỗi chunk có manifest riêng, historical pointer giữ toàn bộ timeline. Correction phải rebuild toàn affected days/halo. `/api/gold/history` chọn canonical disjoint scopes; monthly gộp daily sufficient statistics, không lấy trung bình các partial-month averages. Empty-scope withdrawal phải explicit bằng tombstone.

## Publish, failure và rollback

Tables append rows có `release_id`, stage chưa công bố chỉ có thể bị thay trước khi registry tồn tại.
Validation kiểm tra grain/null keys/FK/QC/coverage/time scope/AQI status. Job chặn publish nếu
Silver head khác snapshot đã pin. Supported orchestration phải serialize các writers.
`gold_release` ghi snapshot mapping, sau đó immutable timeline version và atomic timeline pointer. Legacy single-release pointer không định nghĩa toàn bộ lịch sử.
Historical reader resolve `gold_timeline_current` một lần rồi dùng full manifest và `FOR VERSION AS OF` cho từng bảng.
Thêm snapshots/release khác vào bảng không thay kết quả request cũ.

- Fail trước registry: pointer giữ nguyên; retry cùng inputs/code thay stage chưa đăng ký rồi validate lại.
- Fail giữa registry/pointer: retry khôi phục pointer từ immutable registry nếu nó mới hơn pointer hiện tại.
- Replay release cũ không tự rollback pointer mới hơn; rollback là thao tác explicit bên dưới.
- Host runner và Spark runner có advisory flock. Chỉ hỗ trợ một Compose host/writer; không phải distributed lock.

```bash
docker compose exec -T spark-master /opt/spark/bin/spark-submit \
  --master 'local[1]' --driver-memory 2g \
  /opt/spark/work-dir/jobs/gold/activate_release.py \
  --schema gold_pilot --release-id <validated-release-id>
```

Không expire snapshots hoặc xóa files khi chúng còn trong bất kỳ registry release đang được giữ.
Retention/garbage collection tự động chưa triển khai. Stage thất bại có thể để lại files/snapshots,
cần maintenance riêng sau khi đối chiếu registry; không dùng `remove_orphan_files` một cách mù quáng.

## Backend / frontend

```bash
# Chỉ dùng cấu hình pilot cho development; chưa là production.
DASHBOARD_DATA_SOURCE=gold GOLD_SCHEMA=gold_pilot GOLD_TRINO_URI=http://127.0.0.1:8083 \
  backend/.venv/bin/uvicorn app.main:app --app-dir backend --port 8000

# Frontend chạy trong frontend/; backend cần cấu hình proxy/URL theo setup sẵn có.
VITE_DASHBOARD_SOURCE=gold npm run dev
VITE_DASHBOARD_SOURCE=gold npm run build
```

Production dùng `GOLD_SCHEMA=gold` và chỉ bật channel air_quality sau khi có release đúng source.
Mất Gold/Trino trả 503, không fallback Parquet. Đường Parquet cũ chỉ hoạt động khi cấu hình rõ ràng.
Giữ `published_release_id`, `observation_time`, source/cadence/temporal/representation, per-pollutant
quality/missing và separate computed/provider AQI trong API contracts.
`/api/gold/admin/summary` là sample-weighted concentration và counts/distribution series-days;
không phải national population-weighted exposure hoặc AQI toàn quốc.

## Airflow và monitoring

Airflow 2.10.5 có hai DAG dùng DockerOperator để chạy image Spark đã pin. Scheduler
truy cập Docker qua proxy nội bộ, không mount socket trực tiếp; job/DDL/Landing được
mount read-only và mọi Silver/Gold task dùng pool một writer. Lịch daily mặc định
paused cho đến khi hoàn tất build, import check và một manual smoke run. Host runner
đã kiểm thử vẫn là đường fallback trong giai đoạn nghiệm thu.

Theo dõi quality mart và registry scope/published_at, số sample, coverage, NULL AQI reasons,
Spark elapsed/RSS, Iceberg file count/bytes, Trino latency. Telemetry collection attempts và failed
collector runs phải onboard từ Silver riêng; không tái đọc Landing/manifest từ Gold để lấp số.

UI smoke check tùy chọn: `scripts/check_gold_ui.mjs` cần Playwright/Chrome có sẵn;
nhận module path qua argument hoặc `PLAYWRIGHT_MODULE_PATH` và browser path qua
`PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH`. Dùng saved responses từ real-stack serving checks,
không thay API integration test và không tự cài dependency vào frontend.

## Historical migration, pagination, withdrawal và rollback

Migration chỉ CREATE ba bảng mới (hai timeline + provenance sidecar), không ALTER/ghi đè dữ liệu cũ. Seed chỉ release đang visible trong legacy pointer; không tự nhận mọi registered stage là đã publish. Các chunk cũ khác chưa chứng minh visible phải được review trước khi import. Giữ nguyên registry/snapshots để rollback.

```bash
docker compose exec -T spark-master /opt/spark/bin/spark-submit --master 'local[1]' --driver-memory 2g /opt/spark/work-dir/jobs/gold/manage_timeline.py --schema gold_pilot --action migrate
# Chọn identity từ /api/gold/history/catalog hoặc immutable registry.
docker compose exec -T spark-master /opt/spark/bin/spark-submit --master 'local[1]' --driver-memory 2g /opt/spark/work-dir/jobs/gold/activate_release.py --schema gold_pilot --timeline-id <timeline-id>
# Dry run duy nhất: KHÔNG expire hoặc remove orphan files.
docker compose exec -T spark-master /opt/spark/bin/spark-submit --master 'local[1]' --driver-memory 2g /opt/spark/work-dir/jobs/gold/manage_timeline.py --schema gold_pilot --action retention
# Chỉ cho scope/method/lane đã review, bounds phải là VN midnight.
docker compose exec -T spark-master /opt/spark/bin/spark-submit --master 'local[1]' --driver-memory 2g /opt/spark/work-dir/jobs/gold/manage_timeline.py --schema <schema> --action withdraw --compatibility-id <lane> --start <utc-start> --end <utc-end>
```

`--release-id` rollback vẫn hỗ trợ legacy, khôi phục whole timeline version đã publish release đó khi có mapping. Sau rollback, replay release từng publish không tự bật lại timeline đã rút. Muốn re-activate phải chọn timeline explicitly. Nếu failure sau immutable timeline insert nhưng trước pointer, retry chỉ khôi phục staged view có parent đúng pointer hiện tại; không đè một rollback/publication mới hơn.

`GET /api/gold/history?resolution=hourly&start=...&end=...&source=...` trả timeline, release IDs, missing scopes và next_cursor. Giữ nguyên filters khi gửi cursor; cursor tự pin timeline dù có publish mới. Daily/monthly dùng VN-midnight bounds, monthly không có AQI trung bình. `/history/aqi-distribution` đếm canonical series-days; `/history/quality` tách measurement coverage với collection telemetry NULL. Dashboard tự compose lịch sử; giới hạn render 25.000 rows/pollutant để tránh đưa hàng triệu điểm vào browser. Dùng monthly hoặc paginated API cho phạm vi dài hơn.

Normalized production province adapter chỉ bật với `require_measurement_intervals=true`, complete `metric_policies`, `minimum_spatial_coverage`, source review và successful Silver runs. `normalized-hourly-v3.json` là fixture-only contract hiện tại; v1/v2 giữ nguyên để replay lịch sử. Station/proxy không được dùng province adapter; không đổi reviewed_for_production để lách thiếu input thật. Không onboard provider snapshot vào fact có observed_at NOT NULL bằng scheduled timestamp; cần migration đã review trước activation.

## Acceptance commands

```bash
PYTHONPATH=backend backend/.venv/bin/python -m pytest backend/tests -q
backend/.venv/bin/python -m unittest discover -s spark/jobs/gold/tests -v
npm --prefix frontend test
# Mỗi full run history dùng namespace mới để giữ immutable evidence/rollback views.
GOLD_HISTORY_TEST_SCHEMA=gold_test_history_<unique_suffix> backend/.venv/bin/python scripts/test_gold_history.py
backend/.venv/bin/python scripts/test_gold_pipeline.py
backend/.venv/bin/python scripts/test_gold_operations.py
node scripts/check_gold_history_ui.mjs <playwright-module-path>
```

Operation acceptance dùng namespace `gold_test_history_v2` đã chuẩn bị bởi full history test. UI acceptance yêu cầu FastAPI Gold cùng namespace, Vite --mode gold port5178. Chỉ chạy một Spark acceptance/benchmark tại một thời điểm. Test fixture nằm riêng gold_test*, không export production. Scripts không tự cleanup snapshots.

Retention hiện **fail closed**: dry-run bảo vệ tất cả registry/timeline rollback references; chưa có cleanup. Iceberg 1.7.1 có snapshot references/retention primitives, nhưng chưa nghiệm thu tag lifecycle cùng Nessie trong project; không bật expiry dựa trên khả năng của tài liệu thư viện. Chưa có chính sách archive/TTL được đo cho multi-year production; phải xử lý storage growth trước khi bật cleanup.

Complete metric withdrawal regression: `backend/.venv/bin/python scripts/test_gold_metric_withdrawal.py`. Fixture restore chỉ tác động `gold_test_deletion_silver`; ca cuối cố ý đổi CO vertical support và **phải bị từ chối**. Exit code 1 của `metric-reject.log` là expected negative case, không phải failure của test driver. Driver exit0 và `metric-withdrawal.json.result` là tiêu chí pass. Không bỏ validation để làm fixture sai trở thành hợp lệ.

Host runner hỗ trợ nguồn hourly qua `--adapter normalized_hourly --silver-schema <silver-schema> --contract <container-contract-path>`; bắt buộc explicit contract để tránh dùng nhầm mapping CAMS. Production contract vẫn phải qua review/metric/interval/coverage gates. `--fixture` chỉ dùng khi input/output đều gold_test*. Bằng chứng backfill hai chunk + replay nằm trong readiness/host-runner*.txt; không dùng namespace fixture làm nguồn production.

## Performance và retention inventory

```bash
# Cô lập fixture34tỉnh ×31ngày; không chạy cùng writer khác.
docker compose exec -T spark-master /opt/spark/bin/spark-submit --master 'local[1]' --driver-memory 2g /opt/spark/work-dir/jobs/gold/tests/prepare_performance_fixture.py --help
# Metadata-only archive simulation, không ghi Iceberg snapshots.
backend/.venv/bin/python scripts/benchmark_gold_timeline.py after
# Read-only inventory; công cụ khóa cùng writer và dùng local[1].
docker compose exec -T spark-master /opt/spark/bin/spark-submit /opt/spark/work-dir/jobs/gold/tests/inventory_retention.py --schema gold_test_perf_month34 --output /tmp/gold-retention-month34.json
# API fixture acceptance + measured Trino queries, cần benchmark inputs đã build.
backend/.venv/bin/python scripts/verify_gold_serving.py --performance
```

`measure_process.py` nhận các args của Gold runner; `GOLD_BENCH_OUTPUT` đặt thư mục
raw log/metrics trong container. AQI/spatial phase timings, process RSS, Spark
tasks/stages/shuffle và file bytes có scope riêng.31ngày34×6 chạy16+15ngày; một
chunk31ngày bị collect guard từ chối, không tăng limit để che thiếu phân tán.
Data-equivalence checks dùng exact raw concentration/AQI và tolerance chỉ cho
SQL floating reductions của daily/monthly statistics.

New publication ghi wire manifestv2, deduplicate series metadata; v1 vẫn đọc được.
Roll out readers hỗ trợ cả hai trước writersv2; rollback reader binary về bản chỉ
đọc v1 sau publicationv2 là không tương thích. Có thể rollback timeline về v1
đã lưu nếu cần; không sửa manifest/ID cũ. Không đổi physical DDL cho codec này.
API cursorsv2 có scope page+offset; giữ filters và timelineID. Hourly/daily scan
tối đa16segments; aggregate/monthly32. Monthly page không split một tháng; nếu
tháng có hơn32segments hãy rebuild/coalesce compatible daily-aligned scopes.

Retention policy hiện giữ tất cả registered releases, mọi timeline rollback
version, legacy current pointers, named refs, current heads và toàn bộ source
tables. Unreferenced snapshots mới hơn90ngày được hold. Older unreferenced
snapshots chỉ là danh sách **review**, không phải được phép xóa. Missing registry,
unknown release hoặc inventory thiếu phải fail closed; `delete_candidates=[]`
trong mọi trường hợp. Head-file inventory không bao phủ MinIO object store hoặc
union mọi retained snapshot. Stage files không được tự coi là orphan. Vẫn không
chạy expiry/orphan cleanup; codec giảm size nhưng immutable-version growth vẫn
O(n²), cần archive/rollback retention review trên production evidence.

Unknown actual observation clocks tiếp tục bị chặn trước writes. Kế hoạch additive
[observation-clock-v2](OBSERVATION-TIME-MIGRATION.md) phải phối hợp nullable fact,
explicit record presence, quality và serving trước khi bật nguồn snapshot mới.
Không thay observation time bằng collection/schedule. Airflow vẫn thiếu verified
submit transport; host runner là supported operational path, không thêm socket/DAG.
