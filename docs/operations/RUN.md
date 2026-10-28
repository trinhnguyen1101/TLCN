# Chạy pipeline Lakehouse thủ công

[Mục lục tài liệu](../README.md) / **Vận hành**

Chạy các lệnh từ **thư mục gốc repository**, nơi có `docker-compose.yml`.
Các lệnh dưới đây không chờ nhập xác nhận. Chạy tuần tự các Spark writers;
không chạy Silver và Gold cùng lúc khi chúng sử dụng cùng input/table scope.

- [Mô tả lớp Silver](../lakehouse/SILVER.md)
- [Mô tả lớp Gold](../lakehouse/GOLD.md)
- [Silver → Gold: lệnh chạy thủ công](#silver--gold)
- [Gold runbook chi tiết](../../lakehouse/gold/RUNBOOK.md)

## Khởi động hạ tầng

```bash
docker compose config --quiet
docker compose up -d --build
docker compose ps -a
```

```bash
ingestion_date=$(date -u +%F)
batch_id="raw-$(date -u +%Y%m%dT%H%M%SZ)"

printf 'Ngày: %s\nBatch: %s\n' "$ingestion_date" "$batch_id"
```

## Landing → Bronze

```bash
docker compose exec -T spark-master /opt/spark/bin/spark-submit --master 'local[1]' --driver-memory 512m /opt/spark/work-dir/jobs/bronze/landing_to_bronze.py --dataset waqi/historical --batch-id "$batch_id" --ingestion-date "$ingestion_date"

docker compose exec -T spark-master /opt/spark/bin/spark-submit --master 'local[1]' --driver-memory 512m /opt/spark/work-dir/jobs/bronze/landing_to_bronze.py --dataset CAMS/EAC4 --batch-id "$batch_id" --ingestion-date "$ingestion_date"

docker compose exec -T spark-master /opt/spark/bin/spark-submit --master 'local[1]' --driver-memory 512m /opt/spark/work-dir/jobs/bronze/landing_to_bronze.py --dataset climate_trace/climate_trace_vietnam --batch-id "$batch_id" --ingestion-date "$ingestion_date"

docker compose exec -T spark-master /opt/spark/bin/spark-submit --master 'local[1]' --driver-memory 512m /opt/spark/work-dir/jobs/bronze/landing_to_bronze.py --dataset reference/vietnam_administrative_divisions --batch-id "$batch_id" --ingestion-date "$ingestion_date"

docker compose exec -T spark-master /opt/spark/bin/spark-submit --master 'local[1]' --driver-memory 512m /opt/spark/work-dir/jobs/bronze/landing_to_bronze.py --dataset reference/vietnamese-provinces-database --batch-id "$batch_id" --ingestion-date "$ingestion_date"
```

## Bronze → Silver

Dùng cùng `ingestion_date` và `batch_id` của các bước Landing -> Bronze ở
trên. Nếu dùng batch đã có, đặt hai biến này theo đúng batch đó trước khi
chạy. Các job chỉ đọc batch có manifest và metadata hoàn tất; tự tạo schema
Silver nếu chưa có. Chạy tuần tự, bắt đầu bằng hai dataset hành chính:

```bash
docker compose exec -T spark-master /opt/spark/bin/spark-submit --master 'local[1]' --driver-memory 1g --conf spark.sql.shuffle.partitions=4 --py-files /opt/spark/work-dir/jobs/silver/common.py /opt/spark/work-dir/jobs/silver/admin_bronze_to_silver.py --bronze-path "s3a://lakehouse/bronze/reference/vietnam_administrative_divisions/ingestion_date=$ingestion_date/batch_id=$batch_id"

docker compose exec -T spark-master /opt/spark/bin/spark-submit --master 'local[1]' --driver-memory 2g --conf spark.sql.shuffle.partitions=4 --py-files /opt/spark/work-dir/jobs/silver/common.py /opt/spark/work-dir/jobs/silver/admin_bronze_to_silver.py --bronze-path "s3a://lakehouse/bronze/reference/vietnamese-provinces-database/ingestion_date=$ingestion_date/batch_id=$batch_id"

docker compose exec -T spark-master /opt/spark/bin/spark-submit --master 'local[1]' --driver-memory 1g --conf spark.sql.shuffle.partitions=4 --py-files /opt/spark/work-dir/jobs/silver/common.py /opt/spark/work-dir/jobs/silver/waqi_bronze_to_silver.py --bronze-path "s3a://lakehouse/bronze/waqi/historical/ingestion_date=$ingestion_date/batch_id=$batch_id"

docker compose exec -T spark-master /opt/spark/bin/spark-submit --master 'local[1]' --driver-memory 1g --conf spark.sql.shuffle.partitions=4 --py-files /opt/spark/work-dir/jobs/silver/common.py /opt/spark/work-dir/jobs/silver/climate_trace_bronze_to_silver.py --bronze-path "s3a://lakehouse/bronze/climate_trace/climate_trace_vietnam/ingestion_date=$ingestion_date/batch_id=$batch_id"
```

CAMS/EAC4 cần đủ 20 tệp GRIB. Job chuẩn hóa từng ô lưới ở bước thời gian gốc
3 giờ, không tính AQI. Cần đủ dung lượng tạm để sao chép toàn bộ batch GRIB.

```bash
docker compose exec -T spark-master /opt/spark/bin/spark-submit --master 'local[1]' --driver-memory 1g --conf spark.sql.shuffle.partitions=4 --py-files /opt/spark/work-dir/jobs/silver/common.py,/opt/spark/work-dir/jobs/silver/cams_physics.py /opt/spark/work-dir/jobs/silver/cams_bronze_to_silver.py --bronze-path "s3a://lakehouse/bronze/cams/eac4/ingestion_date=$ingestion_date/batch_id=$batch_id"
```

Kiểm tra trạng thái cả 5 dataset và lỗi chất lượng dữ liệu của batch:

```bash
docker compose exec -T trino trino --execute "SELECT d.source_system, d.dataset_name, r.pipeline_version, r.status, r.input_rows, r.output_rows, r.duplicate_rows, r.invalid_rows, r.error_message FROM iceberg.silver.ingestion_run r JOIN iceberg.silver.dataset d ON r.dataset_id = d.dataset_id WHERE r.bronze_batch_id = '$batch_id' ORDER BY d.dataset_name, r.started_at DESC"

docker compose exec -T trino trino --execute "SELECT d.dataset_name, q.rule_id, q.severity, count(*) AS issues FROM iceberg.silver.data_quality_issue q JOIN iceberg.silver.ingestion_run r ON q.ingestion_run_id = r.run_id JOIN iceberg.silver.dataset d ON q.dataset_id = d.dataset_id WHERE r.bronze_batch_id = '$batch_id' GROUP BY d.dataset_name, q.rule_id, q.severity"
```

Sau khi chạy đủ 5 lệnh, mỗi dataset phải có lần chạy `succeeded` cho phiên
bản pipeline hiện tại. Ý nghĩa số đếm khác nhau theo từng luồng:

| Dataset | `input_rows` | `output_rows` |
| --- | --- | --- |
| `vietnam_administrative_divisions` | Tỉnh/xã trong hai JSON chính | Đơn vị hành chính sau loại trùng |
| `vietnamese-provinces-database` | Đơn vị hành chính + feature ranh giới | Đơn vị hành chính + ranh giới sau loại trùng |
| `waqi/historical` | Dòng CSV | Dòng ngày/trạm/biến, gồm cả ô trống có `missing_reason` |
| `climate_trace_vietnam` | Dòng CSV | Bản ghi tổng hợp + quan trắc nguồn phát thải sau loại trùng |
| `CAMS/EAC4` | Phần tử của cả 20 biến | Dòng thời gian/lưới, mỗi dòng chứa 20 mảng |

WAQI giữ AQI có sẵn trong nguồn, không phải nồng độ; các cột vắng mặt được
ghi nhận trong `waqi_station_variable`. Climate TRACE giữ lượng phát thải
native, chưa gán đơn vị chuẩn khi CSV không khai báo. Hai nguồn hành chính
cùng ghi vào `admin_unit`, giữ provenance riêng trong `admin_unit_source`;
`is_current` được xác định bằng ngày snapshot, không phải ngày hiệu lực pháp lý.

Kiểm tra một ô lưới CAMS đã chuẩn hóa:

```bash
docker compose exec -T trino trino --execute "SELECT c.valid_time, cardinality(c.co) AS grid_points, c.co[1] AS co_ug_m3, c.pm2p5[1] AS pm2p5_ug_m3, c.t_model[1] AS t_model_degC FROM iceberg.silver.cams_cube_standard c JOIN iceberg.silver.ingestion_run r ON c.ingestion_run_id = r.run_id WHERE r.status = 'succeeded' ORDER BY c.loaded_at DESC, c.valid_time LIMIT 5"
```

Đầu ra v4 nằm trong `cams_cube_standard`; đơn vị và phương pháp nằm trong
`cams_cube_standard_source`. Bảng `cams_cube` cũ giữ giá trị gốc, không dùng
lẫn với bảng chuẩn hóa. Không áp dụng lại hệ số chuyển đổi lên
`cams_cube_standard`. PM bằng 0 hợp lệ được giữ nguyên.

Cả 5 luồng bỏ qua batch đã thành công với cùng dataset/version/pipeline
version. Lần chạy lỗi có thể đã ghi một phần bảng hoặc chunk; kiểm tra run
`succeeded` trước khi sử dụng dữ liệu. Không chạy đồng thời các job ghi cùng
bảng. Bronze không bị ghi lại bởi job Silver.

## Silver → Gold

Gold có lệnh chạy thủ công. Host runner `scripts/run_gold.py` chia scope theo
chunk và gọi Spark bên trong container; host chỉ cần Python3 và Docker Compose.
Không cần Airflow cho đường chạy này. Spark dùng `local[1]`, driver heap2GiB.
DDL, dimensions, concentration facts, AQI, marts, validation và publish được chạy
trong cùng Gold job; không cần tạo từng bảng thủ công trước.

`--start-date`/`--end-date` là **ngày Việt Nam**, end exclusive. Ví dụ
`2003-01-01` đến `2003-01-02` tương ứng
`[2002-12-31 17:00Z, 2003-01-01 17:00Z)`. Giữ hourly grain ngay cả khi nguồn3h.

### 1. Kiểm tra Silver đầu vào

```bash
docker compose ps

docker compose exec -T trino trino --execute "SELECT d.dataset_id, d.dataset_name, d.source_version, max(r.finished_at) AS latest_success FROM iceberg.silver.dataset d JOIN iceberg.silver.ingestion_run r ON r.dataset_id = d.dataset_id WHERE d.source_system = 'cams' AND r.status = 'succeeded' GROUP BY d.dataset_id, d.dataset_name, d.source_version ORDER BY latest_success DESC"
```

Chỉ sử dụng rows có successful Silver lineage. Không chọn validation dataset
thay production. Theo evidence28/10/2026, nguồn CAMS đã kiểm chứng mới là
`EAC4-validation-*`, chưa có full EAC4 production hoặc hourly-mean production.

### 2. Chạy CAMS pilot với dữ liệu Silver đã kiểm chứng

Lệnh có thể dùng ngay khi stack và Silver pilot của repository còn được giữ:

```bash
python3 scripts/run_gold.py \
  --schema gold_pilot \
  --silver-schema silver \
  --adapter cams \
  --dataset-id cbb7d021543ec806863f7da49793290e7ea2b1c71c169a717f6a01d64418ed61 \
  --allow-validation \
  --start-date 2003-01-01 \
  --end-date 2003-01-02 \
  --chunk-days 1
```

Pilot đã nghiệm thu612concentration facts từ3timestamps00/03/06UTC,34province
series. Các giờ khác giữ missing trong serving, không tạo observation giả.
AQI giờ/ngày NULL đúng eligibility của instantaneous3h. Đây là validation input,
không phải production AQI. Nếu dataset không còn tồn tại, job phải fail;
không tự thay nguồn.

Có thể gọi Spark trực tiếp cho **cùng một scope**, thay cho host runner:

```bash
docker compose exec -T spark-master /opt/spark/bin/spark-submit \
  --master 'local[1]' --driver-memory 2g \
  /opt/spark/work-dir/jobs/gold/run.py \
  --schema gold_pilot --silver-schema silver --adapter cams \
  --dataset-id cbb7d021543ec806863f7da49793290e7ea2b1c71c169a717f6a01d64418ed61 \
  --allow-validation --start-date 2003-01-01 --end-date 2003-01-02
```

Chọn một trong hai cách; không khởi chạy đồng thời. Với cùng input snapshots,
contract, code/DDL, method và scope, re-run nhận `GOLD_REPLAY` thay vì thêm duplicate.

### 3. Backfill CAMS production khi đầu vào đủ điều kiện

Mẫu dưới đây chỉ dùng sau khi có dataset `source_version='EAC4'`, succeeded
Silver runs và dữ liệu thật bao phủ khoảng yêu cầu. Đặt `GOLD_DATASET_ID` bằng ID
đã kiểm tra ở bước1; điều chỉnh ngày theo source coverage thực tế.

```bash
: "${GOLD_DATASET_ID:?Cần đặt GOLD_DATASET_ID bằng dataset_id EAC4 production đã kiểm chứng}"

python3 scripts/run_gold.py \
  --schema gold --silver-schema silver --adapter cams \
  --dataset-id "$GOLD_DATASET_ID" \
  --start-date 2003-01-01 --end-date 2003-02-01 \
  --chunk-days 7
```

Không thêm `--allow-validation` vào production. CLI cho phép1–31ngày/chunk,
nhưng adapter có guard100.000rows **gồm11giờ halo**. Bắt đầu7ngày/chunk;
giảm scope khi tăng số series/metrics. Fixture34tỉnh×6chất×31ngày đã đo bằng
16+15ngày, không chạy31ngày trong một collect vượt budget.

### 4. Kiểm tra Gold hourly mean/AQI bằng fixture riêng

Chỉ dùng development: tạo dữ liệu kiểm thử trong `gold_test_manual*`, không ghi
Silver production. Fixture này có **1tỉnh**,6chất,48hourly means và11giờ halo;
không phải dataset34tỉnh hoặc observation thực.

```bash
docker compose exec -T spark-master /opt/spark/bin/spark-submit \
  --master 'local[1]' --driver-memory 2g \
  /opt/spark/work-dir/jobs/gold/tests/prepare_hourly_fixture.py \
  --namespace gold_test_manual_silver --start-date 2026-01-02 --days 2

python3 scripts/run_gold.py \
  --schema gold_test_manual --silver-schema gold_test_manual_silver \
  --adapter normalized_hourly \
  --contract /opt/spark/work-dir/lakehouse/gold/contracts/normalized-hourly-v3.json \
  --dataset-id hourly_fixture_only --fixture \
  --start-date 2026-01-02 --end-date 2026-01-04 --chunk-days 2
```

Fixture nguyên vẹn cho48AQI giờ và2AQI ngày hợp lệ. Contractv3 fixture-only,
không được bật thành production chỉ bằng đổi cờ review. Nguồn1h thật cần unit,
vertical support, intervals, QC, mapping và successful run IDs đã xác minh.
Cadence60phút hoặc snapshot gọi mỗi giờ không tự đồng nghĩa hourly mean.

### 5. Nhánh WAQI historical/Climate TRACE native

Chạy riêng sau khi Silver native đã succeeded. Job materialize native facts/mart
và publish channel `native_sources`, độc lập channel concentration/AQI.

```bash
docker compose exec -T spark-master /opt/spark/bin/spark-submit \
  --master 'local[1]' --driver-memory 2g \
  /opt/spark/work-dir/jobs/gold/native_sources.py --schema gold
```

WAQI daily giữ provider AQI. Climate TRACE giữ native values và unit status;
unit chưa xác minh vẫn NULL/unverified. Không đổi sang tonnes theo suy đoán,
không phân bổ GADM bằng centroid hoặc cộng chồng totals/sectors/subsectors.

### 6. Kiểm tra publish và đọc qua API

Host runner lưu log tại `reports/gold/<start-date>-<schema>.log` và in exit code
của từng chunk. Đọc các marker `GOLD_BEGIN`, `GOLD_TIMINGS`, `GOLD_PUBLISHED`
hoặc `GOLD_REPLAY`. Nếu job failed, không coi các table heads/staging là đã publish.

```bash
docker compose exec -T trino trino --execute "SELECT release_id, channel, scope_start_utc, scope_end_utc, published_at FROM iceberg.gold_pilot.gold_release ORDER BY published_at DESC LIMIT 5"

docker compose exec -T trino trino --execute "SELECT channel, timeline_id, published_at FROM iceberg.gold_pilot.gold_timeline_current"
```

Registry có thể chứa release đang chờ pointer recovery. Historical API resolve
`gold_timeline_current` một lần, đọc snapshot mappings đã publish; không coi legacy
`gold_current_release` là toàn lịch sử. Không dùng trực tiếp table heads để dựng
dashboard hoặc đếm chung nhiều releases.

Chạy FastAPI trong terminal riêng, chọn namespace muốn xem. Đổi `gold_pilot`
thành `gold_test_manual` nếu kiểm tra fixture ở bước4:

Các lệnh API/tests dùng `backend/.venv` và dashboard dùng dependencies đã cài
trong `frontend/`; nếu cài môi trường mới, làm theo
[hướng dẫn setup backend/frontend](../dashboard/setup-web-dashboard.md) trước.

```bash
DASHBOARD_DATA_SOURCE=gold GOLD_SCHEMA=gold_pilot \
  GOLD_TRINO_URI=http://127.0.0.1:8083 \
  backend/.venv/bin/uvicorn app.main:app --app-dir backend --port 8000
```

Đọc API từ terminal khác:

```bash
curl --fail --silent --show-error 'http://127.0.0.1:8000/api/gold/map?pollutant=pm25'

curl --fail --silent --show-error 'http://127.0.0.1:8000/api/gold/history?resolution=hourly&start=2002-12-31T17:00:00Z&end=2003-01-01T17:00:00Z&pollutant=pm25&limit=1000'
```

Đối với fixture ở bước4, dùng khoảng
`start=2026-01-01T17:00:00Z&end=2026-01-03T17:00:00Z`. API hỗ trợ
`resolution=hourly|daily|monthly`. Giữ nguyên filters khi gửi `next_cursor` qua
tham số `cursor`; frontend không phải tự ghép release IDs. Daily/monthly bounds
phải tại VN midnight; không có chỉ số AQI tháng.

Chạy User/Admin dashboard Gold trong một terminal riêng:

```bash
(cd frontend && npm run dev -- --mode gold --host 127.0.0.1 --port 5178)
```

Truy cập `http://127.0.0.1:5178/user` hoặc `/admin`. Backend phải bật Gold mode
như trên: default backend hiện vẫn là legacy Parquet, frontend mode không tự đổi
repository backend. Khi Gold lỗi, API không tự fallback sample. Nếu port đã có
server, dùng server tương ứng hoặc chọn port/proxy phù hợp, không chạy chồng.

### 7. Kiểm thử và giới hạn vận hành

```bash
backend/.venv/bin/python -m unittest discover -s spark/jobs/gold/tests -v
PYTHONPATH=backend backend/.venv/bin/python -m pytest backend/tests -q
npm --prefix frontend test
npm --prefix frontend run build -- --mode gold
```

Các lệnh trên kiểm tra logic/contracts/build, không tự thay thế Spark/Trino/E2E.
Integration runners có thể ghi/correct/delete **test fixtures**, chỉ chạy tuần tự
theo [Gold runbook](../../lakehouse/gold/RUNBOOK.md). Không chạy full archive trước
pilot; không expire snapshots/remove orphan files hoặc xóa published references.
Airflow chưa có verified Spark submit transport; host runner là đường vận hành
hiện có. Rollback, withdrawal và retention dry-run xem runbook, không sửa pointer
bằng SQL thủ công.

Kết quả đã chạy và các blocker được giữ ở
[VALIDATION](../../reports/gold/VALIDATION.md) và
[performance](../../reports/gold/performance/README.md). Việc cập nhật hướng dẫn này
không tự chạy lại ETL hoặc thay đổi dữ liệu.
