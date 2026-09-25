# Dữ liệu mẫu tạm thời

`cams/eac4_provinces/` giữ nguyên bộ số liệu dashboard hiện tại, chuyển từ vị trí cũ trong `data/gold/`. Đây là mẫu phục vụ phát triển giao diện/API, **chưa qua pipeline xử lý và kiểm định chính thức**, không phải dữ liệu Gold.

- `CURRENT`: mã phiên bản mẫu đang đọc.
- `runs/<mã>/manifest.json`: thông tin nguồn và cách tạo mẫu.
- `runs/<mã>/monthly/*.parquet`: bảng tháng dùng trực tiếp cho dashboard; được lưu cùng repository để có thể chạy ngay.
- `observations/`, `weights/` và `.staging-*`: dữ liệu chuyển đổi cục bộ, không đưa vào Git. Các file hiện có được giữ lại khi chuyển thư mục.

API chỉ đọc bảng tháng. Công cụ `app.etl.eac4` là bước chuyển đổi mẫu độc lập, mặc định ghi vào đây; không chạy trong request và không ghi vào `data/gold/`. Dữ liệu GRIB gốc vẫn ở `data/landing/CAMS/EAC4/` để tránh nhân bản nguồn dùng chung.

Thiết lập và chạy: [docs/setup-web-dashboard.md](../../../docs/setup-web-dashboard.md).
