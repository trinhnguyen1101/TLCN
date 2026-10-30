# Backend dashboard

FastAPI đọc Parquet cho dashboard độc lập. Backend không đọc GRIB trong request;
phần chuyển đổi và tổng hợp dữ liệu được thực hiện trước bằng ETL dashboard.

## Tài liệu cần đọc

| Công việc | Hướng dẫn |
| --- | --- |
| Cài và chạy cả backend/frontend | **[Chạy dashboard FE–BE](../docs/dashboard/run-dashboard.md)** |
| Tạo Parquet, tìm hiểu API, chạy kiểm thử | [Xử lý dữ liệu dashboard](../docs/dashboard/data-processing.md) |
| Kiểm tra công thức, đơn vị và bằng chứng | [Phương pháp và kiểm chứng](../docs/dashboard/scientific-hourly-validation.md) |

## Các điểm vào code

| Vị trí | Vai trò |
| --- | --- |
| `app/main.py` | Tạo ứng dụng FastAPI |
| `app/core/config.py` | Đọc cấu hình; mặc định `DASHBOARD_DATA_SOURCE=parquet` |
| `app/api/routes/dashboard.py` | API User/Admin và analytics |
| `app/repositories/parquet/dashboard.py` | Đọc generation, truy vấn giới hạn, tổng hợp và cache |
| `app/etl/eac4.py` | Chuyển GRIB sang generation Parquet |
| `app/etl/metrics.py`, `atmosphere.py`, `grib_fields.py` | Nhận diện tham số, chuyển đổi và ghép trường khí tượng |
| `app/etl/spatial.py` | Trọng số và tổng hợp diện tích theo vùng |
| `app/schemas/dashboard.py` | Hợp đồng dữ liệu API |
| `tests/` | Kiểm thử backend, số học và ETL |

Dữ liệu phục vụ mặc định nằm ở `data/samples/cams/eac4_provinces/` tính từ thư
mục `backend/`. Xem [README dữ liệu](data/samples/README.md) để phân biệt `CURRENT`,
manifest và các partition.

Cấu hình Gold mode có hướng dẫn riêng trong [RUN](../docs/operations/RUN.md#silver--gold).
Không cần các dịch vụ đó để chạy chế độ Parquet ở tài liệu FE–BE.
