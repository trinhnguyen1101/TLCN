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

Landing -> bronze

```bash
docker compose exec -T spark-master /opt/spark/bin/spark-submit --master 'local[1]' --driver-memory 512m /opt/spark/work-dir/jobs/bronze/landing_to_bronze.py --dataset waqi/historical --batch-id "$batch_id" --ingestion-date "$ingestion_date"

docker compose exec -T spark-master /opt/spark/bin/spark-submit --master 'local[1]' --driver-memory 512m /opt/spark/work-dir/jobs/bronze/landing_to_bronze.py --dataset CAMS/EAC4 --batch-id "$batch_id" --ingestion-date "$ingestion_date"

docker compose exec -T spark-master /opt/spark/bin/spark-submit --master 'local[1]' --driver-memory 512m /opt/spark/work-dir/jobs/bronze/landing_to_bronze.py --dataset climate_trace/climate_trace_vietnam --batch-id "$batch_id" --ingestion-date "$ingestion_date"

docker compose exec -T spark-master /opt/spark/bin/spark-submit --master 'local[1]' --driver-memory 512m /opt/spark/work-dir/jobs/bronze/landing_to_bronze.py --dataset reference/vietnam_administrative_divisions --batch-id "$batch_id" --ingestion-date "$ingestion_date"

docker compose exec -T spark-master /opt/spark/bin/spark-submit --master 'local[1]' --driver-memory 512m /opt/spark/work-dir/jobs/bronze/landing_to_bronze.py --dataset reference/vietnamese-provinces-database --batch-id "$batch_id" --ingestion-date "$ingestion_date"
```

Bronze -> Silver

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
