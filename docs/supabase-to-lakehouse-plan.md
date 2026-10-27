# Kế hoạch đồng bộ Supabase vào Bronze và Silver

## 1. Mục tiêu và phạm vi

Tài liệu này mô tả kế hoạch triển khai hai job:

1. Đồng bộ raw data của WAQI và API Ninjas từ Supabase Storage vào MinIO Bronze.
2. Chuẩn hóa các Bronze batch đó vào Apache Iceberg Silver.

Phạm vi hiện tại chỉ gồm thiết kế và kế hoạch triển khai. Job, DAG và schema
mới chưa được tạo.

Luồng mục tiêu:

```text
WAQI / API Ninjas
        ↓ mỗi giờ
Supabase Cron + Edge Functions
        ├── Storage raw-api: raw response + manifest
        └── PostgreSQL: collection_runs + operational snapshots
                         ↓ đồng bộ định kỳ
MinIO Bronze
        ↓ Spark ETL
Iceberg Silver
```

Supabase PostgreSQL là operational layer phục vụ collector và dashboard gần
thời gian thực. MinIO và Iceberg là analytical layer lưu lịch sử dài hạn.

## 2. Các nguyên tắc thiết kế

### 2.1. Nguồn dữ liệu gốc

- Raw objects trong private bucket `raw-api` là nguồn gốc để nạp Bronze.
- Không dùng riêng các bảng `waqi_snapshots` hoặc
  `api_ninjas_snapshots` làm nguồn duy nhất cho Bronze.
- PostgreSQL `collection_runs` được dùng để chọn run đủ điều kiện và đối chiếu
  metadata của manifest.
- Chỉ đồng bộ run có trạng thái `succeeded` hoặc `partial`.
- Không xóa raw orphan tự động. Các trường hợp Storage ghi thành công nhưng
  database hoặc manifest thất bại cần được reconciliation riêng.

### 2.2. Thời gian

Ba loại timestamp không được trộn lẫn:

| Trường | Ý nghĩa |
| --- | --- |
| `scheduled_hour_utc` | Giờ logic của collection run |
| `collected_at_utc` | Thời điểm collector nhận response |
| `waqi_time` | Thời điểm quan trắc do WAQI cung cấp |

WAQI được deduplicate theo thời điểm quan trắc của nguồn. API Ninjas được
deduplicate theo location và giờ logic của collection run.

### 2.3. Ý nghĩa không gian của API Ninjas

API Ninjas được gọi bằng một tọa độ city-proxy đại diện cho tỉnh/thành. Giá trị
nhận được không phải trung bình không gian của toàn tỉnh.

Silver sử dụng `admin_unit` làm dimension tỉnh/thành chuẩn, nhưng vẫn phải giữ:

- location ID/key của Supabase;
- query city;
- latitude/longitude thực tế đã gửi tới API;
- phương pháp biểu diễn `city_proxy`;
- phương pháp và độ tin cậy khi ánh xạ sang đơn vị hành chính.

Không thay tọa độ lịch sử bằng centroid hoặc point-on-surface suy ra từ ranh
giới hành chính. Các điểm suy ra từ ranh giới chỉ có thể dùng để tạo cấu hình
collector mới sau khi được kiểm tra.

### 2.4. Đơn vị đo

- WAQI IAQI là chỉ số của provider, không mặc định là nồng độ `ug/m3`.
- API Ninjas AQI và concentration là hai measurement kind khác nhau.
- Chỉ gán đơn vị concentration sau khi xác nhận contract chính thức của
  provider hoặc metadata nguồn.
- Không thực hiện quy đổi đơn vị dựa trên suy đoán.

## 3. Job Supabase → Bronze

### 3.1. Entry point dự kiến

```text
spark/jobs/bronze/supabase_to_bronze.py
```

Giao diện CLI dự kiến:

```text
--source waqi|api_ninjas
--window-start <UTC timestamp>
--window-end <UTC timestamp>
--batch-id <stable batch ID>
--ingestion-date <YYYY-MM-DD>
```

Supabase URL và service credential chỉ được đọc từ environment hoặc secret
backend. Secret không được đưa vào source code, manifest hoặc log.

### 3.2. Trình tự xử lý

1. Query `collection_runs` theo source và cửa sổ thời gian.
2. Chỉ chọn run `succeeded` hoặc `partial`.
3. Tải `manifest.json` của từng run từ Supabase Storage.
4. Kiểm tra SHA-256 manifest với `collection_runs.manifest_sha256`.
5. Kiểm tra source, run ID, scheduled hour, attempt và số record/object.
6. Lấy danh sách raw object từ manifest, không tự suy đoán chỉ từ prefix.
7. Tải từng raw object vào staging và kiểm tra SHA-256, kích thước.
8. Ghi raw bytes và provider manifest vào một Bronze batch bất biến.
9. Ghi `_file_metadata`.
10. Ghi `_ingestion_manifest` và `_SUCCESS` sau cùng.
11. Chỉ commit checkpoint sau khi Bronze `_SUCCESS` tồn tại và batch được đọc
    kiểm tra lại thành công.

### 3.3. Bronze path

```text
s3a://lakehouse/bronze/waqi/live/
  ingestion_date=YYYY-MM-DD/batch_id=<batch-id>/

s3a://lakehouse/bronze/api_ninjas/province_air_quality/
  ingestion_date=YYYY-MM-DD/batch_id=<batch-id>/
```

Các file bên trong `files/` giữ cấu trúc có scheduled hour và collection run ID
để retry không va chạm:

```text
files/
  YYYY/MM/DD/HH/<collection-run-id>/manifest.json
  YYYY/MM/DD/HH/<collection-run-id>/<target>.raw.json
```

### 3.4. Bronze contract

Output phải tương thích với `spark/jobs/silver/common.py`:

```text
<batch>/
├── files/
├── _file_metadata/
│   └── _SUCCESS
└── _ingestion_manifest/
    └── _SUCCESS
```

`_file_metadata` tiếp tục có các trường contract hiện tại, gồm:

```text
source_file
relative_file
source
dataset
file_format
file_size
file_sha256
modification_time
ingestion_timestamp
ingestion_date
batch_id
bronze_object
```

Có thể bổ sung metadata cấp Supabase run trong provider manifest hoặc một
sidecar riêng, nhưng không được phá contract mà các Silver job hiện tại đọc.

### 3.5. Idempotency và checkpoint

- `batch-id` phải ổn định khi retry cùng một cửa sổ.
- Fingerprint được tính từ danh sách relative path, kích thước và SHA-256.
- Nếu batch đã có `_SUCCESS` và fingerprint giống nhau, job chỉ verify và trả
  về thành công.
- Nếu cùng batch ID nhưng fingerprint khác, job phải dừng và không ghi đè.
- Không dùng duy nhất boolean `synced_to_bronze`.
- Checkpoint tối thiểu chứa source, window start/end, collection run cuối,
  scheduled hour cuối, Bronze batch ID, object count, fingerprint và thời điểm
  hoàn tất.

## 4. Job Bronze → Silver

### 4.1. Entry point dự kiến

```text
spark/jobs/silver/supabase_bronze_to_silver.py
```

Job nhận:

```text
--source waqi|api_ninjas
--bronze-path s3a://lakehouse/bronze/...
```

Phần xử lý từng nguồn có thể được tách thành module riêng, nhưng dùng chung một
entry point và các helper trong `spark/jobs/silver/common.py`.

Job sẽ tái sử dụng:

- `load_bronze_batch`;
- `register_dataset`;
- `start_run` và `finish_run`;
- `merge_dataframe`;
- `deduplicate_or_fail`;
- `data_quality_issue`.

### 4.2. WAQI live

Không tái sử dụng trực tiếp transform của `waqi_bronze_to_silver.py`, vì job đó
xử lý CSV lịch sử có grain theo ngày. WAQI Supabase là JSON snapshot theo giờ,
nhưng observation logic phải dựa vào `waqi_time`.

Các bảng Silver hiện có sẽ được sử dụng:

```text
waqi_station
waqi_station_source
waqi_station_variable
waqi_hourly_observation
waqi_hourly_measurement
variable
```

Khóa logic:

```text
waqi_hourly_observation:
(dataset_id, station_id, observation_time_utc)

waqi_hourly_measurement:
(dataset_id, station_id, observation_time_utc, variable_id)
```

Quy tắc xử lý:

- `observation_time_utc` lấy từ `waqi_time`, không lấy từ thời điểm collector.
- `collected_at_utc` được giữ riêng để đo độ trễ.
- `source_uid` được ánh xạ ổn định sang `station_id`.
- Overall AQI nằm trong observation header.
- Pollutant IAQI và weather values được đưa về measurement long format.
- Giá trị thiếu giữ `NULL` kèm `missing_reason`, không đổi thành 0.
- Hai record cùng logical key và cùng giá trị được tính là duplicate.
- Hai record cùng logical key nhưng khác giá trị tạo quality issue và dừng hoặc
  quarantine; không tự chọn một record.

### 4.3. API Ninjas province/city proxy

Tên bảng Silver được chọn theo ý nghĩa nghiệp vụ thay vì gắn cứng provider:

```text
province_air_quality_location
province_air_quality_hourly_observation
province_air_quality_hourly_measurement
```

Provider vẫn được xác định qua `dataset.source_system = 'api_ninjas'` và
`variable.source_system = 'api_ninjas'`.

#### `province_air_quality_location`

Vai trò: ánh xạ location nguồn với tỉnh/thành chuẩn và giữ tọa độ city-proxy
thực tế.

Schema dự kiến:

```text
dataset_id
proxy_location_id
source_location_id
location_key
admin_unit_version_id
admin_code
query_city
query_latitude
query_longitude
spatial_representation       -- city_proxy
mapping_method
mapping_confidence
source_file
source_file_sha256
ingestion_run_id
loaded_at
```

Khóa logic:

```text
(dataset_id, source_location_id)
```

`admin_unit_version_id` liên kết location với đúng phiên bản đơn vị hành chính.
Tên tỉnh/thành chuẩn không cần lặp lại trong bảng này; consumer join sang
`admin_unit`.

#### `province_air_quality_hourly_observation`

Vai trò: header của một snapshot theo tỉnh/thành proxy và giờ logic.

Schema dự kiến:

```text
observation_id
dataset_id
proxy_location_id
admin_unit_version_id
snapshot_hour_utc
collected_at_utc
overall_aqi
validation_status
qc_flag
source_collection_run_id
source_file
source_file_sha256
ingestion_run_id
loaded_at
```

Khóa logic:

```text
(dataset_id, proxy_location_id, snapshot_hour_utc)
```

#### `province_air_quality_hourly_measurement`

Vai trò: lưu các measurement dạng long format.

Schema dự kiến:

```text
observation_id
dataset_id
proxy_location_id
admin_unit_version_id
snapshot_hour_utc
variable_id
value_native
value_standard
missing_reason
qc_flag
ingestion_run_id
loaded_at
```

Khóa logic:

```text
(observation_id, variable_id)
```

Mỗi pollutant có hai variable riêng khi provider cung cấp đủ:

```text
pm25 + measurement_kind=concentration
pm25 + measurement_kind=aqi
```

Điều này ngăn việc trộn concentration với AQI dù chúng cùng thuộc một chất ô
nhiễm.

### 4.4. Ánh xạ với dữ liệu hành chính

Quy trình ánh xạ dự kiến:

1. Ưu tiên mã hoặc mapping cấu hình đã được xác nhận.
2. Kiểm tra query point nằm trong `admin_boundary` tương ứng.
3. Nếu không nằm trong polygon, ghi quality issue thay vì âm thầm chọn tỉnh gần
   nhất.
4. Lưu `mapping_method` và `mapping_confidence`.
5. Giữ nguyên mapping lịch sử theo `admin_unit_version_id`; không tự đổi record
   cũ khi danh giới hoặc tên hành chính thay đổi.

## 5. Data quality và lineage

Các lỗi fatal dự kiến:

- thiếu hoặc sai SHA-256;
- raw object không nằm trong manifest;
- manifest source/run/hour không khớp collection run;
- timestamp bắt buộc không parse được;
- AQI âm, không nguyên, NaN/Infinity hoặc overflow;
- concentration âm hoặc không hữu hạn;
- station/location identity xung đột;
- duplicate logical key có giá trị khác nhau;
- query point không ánh xạ được tới tỉnh/thành đã cấu hình.

Mỗi output Silver phải truy ngược được tới:

```text
Silver row
  → ingestion_run
  → Bronze batch/file/SHA-256
  → Supabase collection run
  → Supabase raw object
  → provider response
```

Consumer chỉ sử dụng dữ liệu thuộc `ingestion_run.status = 'succeeded'`. Một
attempt thất bại có thể đã commit một số chunk trước khi dừng.

## 6. Orchestration

Hiện tại `airflow/dags` chưa có DAG triển khai. Sau khi hai job được kiểm thử,
DAG hằng ngày dự kiến:

```text
sync Supabase WAQI → Bronze
                  └→ WAQI Bronze → Silver

sync Supabase API Ninjas → Bronze
                         └→ Province air quality Bronze → Silver
```

Hai source có thể sync song song. Các task cùng ghi một bảng Silver không được
chạy đồng thời. Bronze task truyền chính xác `bronze_path` cho Silver task;
Silver không tự tìm batch “mới nhất”.

Khi local lakehouse tắt, Supabase vẫn tiếp tục thu thập. Lần chạy tiếp theo sử
dụng checkpoint để tải bù raw objects đã tồn tại trên Supabase Storage.

## 7. Kế hoạch triển khai và kiểm thử

### Giai đoạn 1: xác nhận contract thực tế

- Lấy một manifest và một số raw object thật của mỗi source.
- So sánh với Edge Function TypeScript trong tài liệu.
- Xác nhận tên object thực tế (`.raw.json`), manifest schema và đơn vị API
  Ninjas.
- Xác nhận mapping 34 location với phiên bản `admin_unit` hiện hành.

### Giai đoạn 2: Supabase → Bronze

- Viết Supabase client và validation cho manifest/object.
- Viết Bronze batch theo contract hiện tại.
- Thêm unit test cho fingerprint, path safety, checksum và retry.
- Thêm integration test với fixture Supabase/Storage nhỏ.

### Giai đoạn 3: schema và Bronze → Silver

- Bổ sung ba bảng `province_air_quality_*` vào `silver.sql`.
- Viết transform WAQI live.
- Viết transform API Ninjas province proxy.
- Thêm data-quality rules, deterministic IDs và MERGE idempotent.
- Kiểm thử duplicate, conflicting retry, partial run và invalid payload.

### Giai đoạn 4: end-to-end và Airflow

- Chạy một cửa sổ nhỏ của cả hai source.
- Đối chiếu object count, checksum, run count và output row count.
- Chạy lại cùng batch để chứng minh idempotency.
- Kiểm tra query qua Trino và lineage ngược về raw object.
- Sau khi ổn định mới tạo DAG và lịch daily sync.

## 8. Tiêu chí hoàn thành

- Không mất hoặc tự sửa raw provider bytes.
- Bronze batch chỉ được coi là hoàn tất sau `_SUCCESS`.
- Retry không tạo duplicate logic trong Bronze hoặc Silver.
- WAQI dùng observation time của nguồn.
- API Ninjas dùng scheduled hour và giữ rõ semantics `city_proxy`.
- Mọi tỉnh/thành proxy ánh xạ tới `admin_unit_version_id` có kiểm chứng.
- AQI và concentration không dùng chung variable/measurement kind.
- Mọi Silver row có lineage đầy đủ và chỉ được công bố từ run `succeeded`.
