# Tài liệu dashboard

[← Mục lục dự án](../README.md)

Dashboard gồm FastAPI và React, đọc Parquet được tạo từ CAMS EAC4 theo giờ.
Chạy dashboard độc lập không cần Docker, Spark, Airflow, MinIO hay Trino.

## Chọn tài liệu theo công việc

| Bạn muốn làm gì? | Tài liệu |
| --- | --- |
| Cài môi trường, chạy backend và frontend, mở `/user` hoặc `/admin` | **[Chạy dashboard từ backend đến frontend](run-dashboard.md)** |
| Tạo lại Parquet, kiểm tra `CURRENT`, tìm hiểu cấu trúc dữ liệu hoặc chạy kiểm thử | [Xử lý và kiểm tra dữ liệu dashboard](data-processing.md) |
| Hiểu đơn vị, mật độ khí, áp suất tầng mô hình và giới hạn dữ liệu | [Phương pháp và kết quả kiểm chứng](scientific-hourly-validation.md) |
| Tra code backend hoặc frontend | [Backend README](../../backend/README.md) · [Frontend README](../../frontend/README.md) |
| Xem các đợt chuyển đổi trước đây | [Tài liệu lưu trữ](archive/README.md) |

Nếu bạn chỉ muốn mở web, bắt đầu ở **[hướng dẫn chạy FE–BE](run-dashboard.md)**.
Chỉ đọc phần xử lý dữ liệu khi thiếu Parquet hoặc cần tạo một phiên bản mới.

## Luồng hoạt động

```text
GRIB EAC4_hourly → ETL dashboard → Parquet → FastAPI → React
                  chạy theo đợt             đọc khi mở web
```

ETL thực hiện chuyển đổi đơn vị và tổng hợp theo vùng trước khi web chạy.
API không đọc GRIB trực tiếp; frontend không tính lại mật độ hoặc nồng độ khí.

## Cách hiểu số liệu

- Mặc định xem từng giờ trong bảy ngày cuối **có trong nguồn**, không phải dữ liệu hôm nay.
- API dùng UTC; giao diện hiển thị thời điểm theo giờ Việt Nam, UTC+7.
- Dữ liệu giờ được nội suy từ phân tích EAC4 ba giờ; không phải số đo trạm theo giờ.
- CO dùng mg/m³; PM1, PM2.5, PM10, NO₂, SO₂ và O₃ dùng µg/m³.
- Khí tổng cột/AOD và khí tượng nằm trong nhóm phân tích riêng. AQI không được tự suy ra.
- Có 34 tỉnh/thành: Hoàng Sa thuộc Đà Nẵng, Trường Sa thuộc Khánh Hòa. Hai quần đảo
  được vẽ riêng nhưng không được đếm như hai tỉnh; số liệu khi chọn là số liệu toàn tỉnh chủ quản.

Tài liệu này chỉ hướng dẫn dashboard Parquet độc lập. Nếu chủ động dùng Gold mode,
xem [hướng dẫn vận hành Gold](../operations/RUN.md#silver--gold).
