# Dữ liệu mẫu tạm thời

`cams/eac4_provinces/` giữ nguyên bộ số liệu dashboard hiện tại, chuyển từ vị trí cũ trong `data/gold/`. Đây là mẫu phục vụ phát triển giao diện/API, **chưa qua pipeline xử lý và kiểm định chính thức**, không phải dữ liệu Gold.

- `CURRENT`: mã phiên bản mẫu đang đọc.
- `runs/<mã>/manifest.json`: thông tin nguồn và cách tạo mẫu.
- `runs/<mã>/monthly/*.parquet`: bảng tháng cho lịch sử 2003–2025.
- `runs/<mã>/observations/<chỉ số>/<năm>/*.parquet`: từng dòng là một vùng báo cáo × mốc 3 giờ UTC × chỉ số, đủ 8 mốc/ngày. Bản cục bộ hiện tại giữ 33.872.832 dòng năm 2003–2025. Phần mẫu 2.947.392 dòng năm 2024–2025 được đưa vào Git để chạy ngay sau khi clone; các năm trước là dữ liệu cục bộ.
- `weights/`, `.staging-*` và quan sát đầy đủ của các phiên bản ETL khác vẫn là dữ liệu cục bộ, không đưa vào Git.

API chỉ đọc generation được `CURRENT` trỏ tới. `parent_generation` trong manifest
ghi nguồn gốc tạo dữ liệu, không yêu cầu thư mục cha tồn tại. Generation cũ có thể
xoá sau khi xác nhận không còn được dùng và đối chiếu checksum với bản đang giữ;
không xoá các năm quan sát chỉ còn trong bản cũ. File trọng số còn hữu ích được
giữ trong `weights/` của generation hiện tại.

API mặc định đọc mốc 3 giờ trong 7 ngày cuối, có bộ lọc thời gian và độ phân giải `3h`, `daily`, `monthly`. Trung bình ngày được tính từ quan sát 3 giờ; bảng tháng phục vụ lịch sử dài hạn. API nhận diện phạm vi quan sát đang có trên đĩa. Công cụ `app.etl.eac4` chuyển đổi toàn bộ GRIB sang Parquet; `python -m app.etl.sample --years 2` xuất phiên bản gọn giữ nguyên quan sát gốc của hai năm cuối và lịch sử tháng; `--years 0` giữ toàn bộ lịch sử quan sát. Có thể chọn phiên bản nguồn bằng `--source-generation <mã>`. Khi thay mẫu trong Git, cập nhật ngoại lệ của phiên bản tương ứng trong `.gitignore`. Các công cụ mặc định ghi vào đây, không chạy trong request. Dữ liệu GRIB gốc vẫn ở `data/landing/CAMS/EAC4/`.

Thiết lập và chạy: [docs/setup-web-dashboard.md](../../../docs/setup-web-dashboard.md).
