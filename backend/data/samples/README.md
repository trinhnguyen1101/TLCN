# Thư mục Parquet phục vụ dashboard

`cams/eac4_provinces/` là vị trí phục vụ hiện tại, được giữ tên để tương thích
cấu hình. Đây là dữ liệu dashboard độc lập, không phải một lớp Lakehouse.

| Thành phần | Ý nghĩa |
| --- | --- |
| `CURRENT` | Mã generation API đang đọc |
| `runs/<id>/manifest.json` | Nguồn, hash, đơn vị, phương pháp và phạm vi thời gian |
| `runs/<id>/observations/<metric>/<year>/*.parquet` | Giá trị giờ theo vùng, độ phủ và chất lượng |
| `runs/<id>/monthly/<metric>.parquet` | Trung bình tháng và số mẫu |
| `runs/<id>/weights/*.parquet` | Trọng số vùng / ô lưới |

Các partition giờ lớn và trọng số được tạo cục bộ, không đi kèm bản clone Git.
Tạo hoặc kiểm tra chúng theo [hướng dẫn xử lý dữ liệu](../../../docs/dashboard/data-processing.md).
Không sửa trực tiếp các tệp trong generation đã công bố.

- [Chạy backend và frontend](../../../docs/dashboard/run-dashboard.md).
- [Phương pháp và biên bản kiểm chứng](../../../docs/dashboard/scientific-hourly-validation.md).
