# Landing → Bronze trên MinIO

Cập nhật 2026-10-03. Job chạy độc lập, chưa đưa vào Airflow và chưa tạo bảng Silver/Gold. Cả năm dataset Landing hiện có đã được nạp lên MinIO và đối chiếu SHA-256 thành công, gồm cả 14 file GRIB CAMS và 3.355 file GeoJSON.

## Landing và cấu hình hiện có

Landing nằm tại `data/landing/` trên host. Compose mount chỉ đọc thư mục này vào Spark master và worker tại `/opt/spark/work-dir/landing/`.

| Dataset dùng với `--dataset` | Số file | Định dạng | Batch đã kiểm chứng (2026-10-03 UTC) |
| --- | ---: | --- | --- |
| `waqi/historical` | 17 | CSV | `raw-waqi-001` |
| `CAMS/EAC4` | 14 | GRIB | `raw-cams-001` |
| `climate_trace/climate_trace_vietnam` | 3 | CSV | `raw-climate-trace-001` |
| `reference/vietnam_administrative_divisions` | 11 | CSV, JSON, NDJSON, CFF, Markdown, LICENSE | `raw-reference-admin-001` |
| `reference/vietnamese-provinces-database` | 3.363 | 3.355 GeoJSON, JSON, Markdown | `raw-reference-geojson-001` |

Landing hiện không có Parquet. Job vẫn nhận Parquet hay định dạng khác vì chuyển file theo bytes, không phụ thuộc extension hoặc schema.

`minio-init` đã tạo bucket `lakehouse` cùng prefix `bronze/`, `silver/`, `gold/`. Job lấy tên bucket từ `spark.sql.catalog.nessie.warehouse` (`s3a://lakehouse/`) và endpoint từ `spark.hadoop.fs.s3a.endpoint` (`http://minio:9000`). `MINIO_ROOT_USER` và `MINIO_ROOT_PASSWORD` được Compose lấy từ `.env` rồi truyền vào container Spark; job không chứa credential. Spark dùng JAR `hadoop-aws` và AWS SDK trong image để kết nối MinIO qua S3A.

## Cấu trúc Bronze

Job `spark/jobs/bronze/landing_to_bronze.py` dùng Hadoop S3A trong Spark JVM để chuyển từng file theo luồng, giữ nguyên bytes, tên và thư mục con. Spark ghi một dataset Parquet nhỏ chứa metadata của từng file. Không parse CSV/JSON/GRIB, không đổi schema và không làm sạch dữ liệu.

Ví dụ:

```text
s3a://lakehouse/bronze/cams/eac4/ingestion_date=2026-10-03/batch_id=raw-cams-001/
├── files/
│   ├── pm10_2003_2025_vietnam.grib
│   └── ...
├── _file_metadata/
│   ├── part-*.snappy.parquet
│   └── _SUCCESS
└── _ingestion_manifest/
    ├── part-*.json
    └── _SUCCESS
```

`_file_metadata` có `source_file`, `relative_file`, `source`, `dataset`, `file_format`, `file_size`, `file_sha256`, `modification_time`, `ingestion_timestamp`, `ingestion_date`, `batch_id`, `bronze_object`. Manifest ghi số file, tổng bytes, fingerprint đầu vào và vị trí batch. Chỉ batch có `_ingestion_manifest/_SUCCESS` mới được xem là hoàn tất. Đây là Bronze raw file trên MinIO, chưa đăng ký Iceberg/Nessie; Silver về sau có thể chọn bộ đọc riêng cho từng định dạng.

Mỗi lần nạp mới dùng `batch_id` mới, tạo batch mới theo ngày UTC. S3A `create(..., overwrite=false)` chặn ghi đè file; job không dùng `append` hay `overwrite` với dữ liệu gốc. Nếu chạy lại cùng ID và ngày, job đọc và so SHA-256 từng object với Landing rồi thoát mà không ghi thêm. Nếu batch bị ngắt trước manifest, job bỏ qua file đã khớp, ghi những file còn thiếu, xác minh lại toàn bộ và hoàn tất metadata/manifest. Nếu file cùng đường dẫn đã khác bytes hoặc manifest thuộc đầu vào khác, job dừng để tránh ghi đè ngoài ý muốn. `overwrite` chỉ được dùng để sửa sidecar metadata/manifest chưa hoàn tất, sau khi dữ liệu gốc đã được kiểm chứng.

Hiện mỗi batch là một bản chụp đầy đủ của dataset được chọn. Job chưa tối ưu đồng bộ tăng dần giữa các batch; chạy hằng ngày với ID mới sẽ lưu lại file không đổi.

## Chạy thử

Từ thư mục gốc project trong PowerShell, sau khi Docker Desktop chạy:

```powershell
docker compose config --quiet
docker compose up -d --build minio minio-init spark-master
docker compose ps
```

Chạy độc lập trên Spark master với một luồng; cách này cũng phù hợp với máy Docker Desktop ít RAM. Tên dataset và bucket đều theo convention đã có trong repo:

```powershell
docker compose exec -T spark-master /opt/spark/bin/spark-submit --master local[1] --driver-memory 512m /opt/spark/work-dir/jobs/bronze/landing_to_bronze.py --dataset waqi/historical --check-only

docker compose exec -T spark-master /opt/spark/bin/spark-submit --master local[1] --driver-memory 512m /opt/spark/work-dir/jobs/bronze/landing_to_bronze.py --dataset waqi/historical --batch-id raw-waqi-001 --ingestion-date 2026-10-03
```

Thay dataset và batch ID để nạp các nguồn khác trong bảng. Ngày trên lệnh chỉ minh họa một batch đã kiểm chứng; batch mới nên dùng ngày UTC hiện tại và ID mới. Nếu bỏ `--batch-id`, job tự tạo UUID; nếu bỏ `--ingestion-date`, job dùng ngày UTC hiện tại. Khi tiếp tục một batch qua ngày khác, truyền lại cả ID và ngày ban đầu. Có thể chạy `--master spark://spark-master:7077` khi Spark worker hoạt động; cả master lẫn worker đã được mount Landing cùng đường dẫn.

## Kiểm tra dữ liệu thực sự lên MinIO

Job đọc lại từng object qua S3A, so kích thước và SHA-256 với file Landing **trước** khi tạo manifest. Log `Verified ... original files and their SHA-256 hashes from MinIO` và `Completed Bronze batch` xác nhận vòng này đã qua.

Liệt kê object bằng MinIO Client của service `minio-init`:

```powershell
docker compose run --rm --no-deps --entrypoint /bin/sh minio-init -c 'mc alias set local http://minio:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" >/dev/null && mc ls --recursive local/lakehouse/bronze/waqi/historical/ingestion_date=2026-10-03/batch_id=raw-waqi-001/'
```

Kết quả cần có 17 file dưới `files/`, Parquet `_file_metadata/part-*`, JSON `_ingestion_manifest/part-*` và `_ingestion_manifest/_SUCCESS`. Có thể xem cùng prefix trong MinIO Console ở cổng `MINIO_CONSOLE_PORT` của `.env` (hiện là 9001).

## File thay đổi

- Mới: `spark/jobs/bronze/landing_to_bronze.py` và tài liệu này.
- Sửa: `docker-compose.yml` mount Landing chỉ đọc cho hai Spark container và giữ JAR đã cài trong image.
- Sửa: `docker/spark/Dockerfile` cài `python3` cho `spark-submit`.
- Sửa: `spark/config/spark-defaults.conf` nạp JAR Iceberg/S3A; hai README dưới `spark/config` và `spark/jars` làm rõ cấu hình.
- Sửa: `README.md` liên kết đến tài liệu này.
