# Xử lý và kiểm tra dữ liệu dashboard

[← Tài liệu dashboard](README.md) · [Chạy web FE–BE](run-dashboard.md)

Trang này dành cho người tạo dữ liệu hoặc bảo trì backend. Nếu Parquet đã có
và bạn chỉ muốn mở web, dùng hướng dẫn chạy FE–BE.

## 1. Phân biệt dữ liệu nguồn và dữ liệu web đọc

```text
data/landing/CAMS/EAC4_hourly/*.grib      # Nguồn; ETL đọc, không sửa
              ↓
backend/app/etl/eac4.py                 # Chuyển đơn vị, QC, tổng hợp theo vùng
              ↓
backend/data/samples/cams/eac4_provinces/
├── CURRENT                            # Mã generation API đang đọc
└── runs/<generation>/
    ├── manifest.json                  # Nguồn, đơn vị, phương pháp, hash
    ├── observations/<metric>/<year>/  # Giá trị giờ theo vùng
    ├── monthly/<metric>.parquet       # Trung bình tháng và số mẫu
    └── weights/<grid-id>.parquet      # Trọng số diện tích vùng / ô lưới
```

**Generation** là một phiên bản Parquet đã xuất xong. API chỉ đọc phiên bản được
`CURRENT` trỏ đến. Tên thư mục `samples` được giữ để tương thích cấu hình cũ;
không có nghĩa dữ liệu hiện tại là số liệu mock.

Các partition giờ lớn và tệp trọng số là dữ liệu tạo cục bộ, không đi kèm bản
clone Git. GRIB cũng cần được cung cấp cục bộ. GeoJSON frontend có sẵn trong
`frontend/public/data/`, độc lập với dữ liệu nồng độ.

## 2. Tạo Parquet từ GRIB

Tất cả lệnh dưới đây chạy từ repository root. Cần virtualenv ở
[bước chuẩn bị môi trường](run-dashboard.md#1-chuẩn-bị-môi-trường-và-dữ-liệu).

Trước khi chạy ETL, cần có đủ hai nhóm tệp cục bộ:

- GRIB giờ trong `data/landing/CAMS/EAC4_hourly/`.
- Ranh giới nguồn trong `data/landing/reference/vietnamese-provinces-database/json/geojson/`,
  gồm ranh giới đầy đủ 34 tỉnh/thành và quần đảo trực thuộc. Các tệp tham chiếu này cũng
  không đi kèm Git; giữ đúng nguồn ranh giới đã dùng để tạo dữ liệu.

Chạy web từ Parquet đã tạo thì không cần đọc lại hai nhóm tệp này.

Cài thêm thư viện chỉ dành cho ETL:

```bash
backend/.venv/bin/python -m pip install -r backend/requirements-etl.txt
```

Kiểm tra nguồn bằng ecCodes trước khi tạo dữ liệu:

```bash
backend/.venv/bin/python scripts/inventory_hourly_grib.py
```

Kết quả kiểm kê nằm trong `reports/dashboard/science/grib-inventory.json`.
Script kiểm tra tham số, đơn vị, timestamp, ô lưới và hệ tọa độ đứng. Các kết quả
đã kiểm kê có thể được dùng lại khi SHA-256 của tệp nguồn vẫn khớp.

Tạo generation mới:

```bash
PYTHONPATH=backend OPENBLAS_NUM_THREADS=1 \
backend/.venv/bin/python -m app.etl.eac4 \
  --input-dir data/landing/CAMS/EAC4_hourly \
  --cadence-hours 1 --temporal-origin interpolated --workers 4
```

ETL xử lý dữ liệu theo luồng và các batch giới hạn bộ nhớ. Đây là tác vụ nhiều
năm dữ liệu, không cần chạy mỗi lần mở dashboard. API không thực hiện tác vụ này
trong request. Có thể giảm `--workers` nếu máy ít tài nguyên.

| Tùy chọn | Khi nào dùng? |
| --- | --- |
| `--input-dir` | Đổi thư mục nguồn GRIB |
| `--output-dir` | Đổi thư mục phục vụ Parquet; nhớ cấu hình `DASHBOARD_PARQUET_PATH` khi chạy API |
| `--boundaries` | Chọn nguồn ranh giới dùng trong phép tổng hợp; không đổi khi chỉ cập nhật dữ liệu |
| `--minimum-coverage` | Ngưỡng độ phủ không gian; mặc định 0.95 |
| `--workers` | Số tiến trình xử lý các partition độc lập; CLI mặc định 1, ví dụ trên chọn 4 |
| `--reuse-generation <id>` | Tái sử dụng partition không đổi từ generation **còn tồn tại**, sau khi các hash và điều kiện xử lý khớp |

Không dùng `--reuse-generation` với các mã cũ đã bị dọn. Không gán nguồn giờ nội
suy thành `--temporal-origin native`. Các phép chuyển đổi và điều kiện hợp lệ
được giải thích ở [báo cáo khoa học](scientific-hourly-validation.md).

## 3. Công bố và kiểm tra generation

ETL ghi vào `.staging-<id>` trước. Chỉ khi toàn bộ phần xử lý hoàn tất, thư mục
mới được đưa vào `runs/<id>` và `CURRENT` được thay thế nguyên tử. Lần build thất
bại không chuyển `CURRENT` sang phần dữ liệu đang viết dở.

Xem phiên bản đang dùng:

```bash
cat backend/data/samples/cams/eac4_provinces/CURRENT
```

Để biết kỳ dữ liệu, chỉ số và cách chuyển đổi, đọc `manifest.json` trong đúng
thư mục `runs/<id>` đó, hoặc `metadata` của API.

Sau khi build, chạy kiểm chứng đầy đủ:

```bash
PYTHONPATH=backend backend/.venv/bin/python scripts/verify_hourly_dashboard.py
```

Script cần cả GRIB và generation đã tạo. Nó đối chiếu nồng độ với phép tính độc
lập từ ô lưới, kiểm tra API User/Admin, 24 mốc giờ trong một ngày hoàn chỉnh,
trung bình ngày/tháng và metadata. Kết quả được ghi vào
`reports/dashboard/science/integration.json`.

Không sửa trực tiếp generation đã công bố. Muốn cập nhật dữ liệu, tạo generation
mới. Nếu thay bộ dữ liệu hoặc cấu hình đang phục vụ, tải lại trang; khởi động lại
backend khi thay biến môi trường.

## 4. Quy ước API và thời gian

| Endpoint | Chức năng |
| --- | --- |
| `/api/health` | Kiểm tra tiến trình, không kiểm tra Parquet |
| `/api/dashboard` | Dữ liệu User Dashboard; mặc định hourly |
| `/api/admin/dashboard` | Dữ liệu Admin Dashboard; mặc định hourly |
| `/api/dashboard/analytics` | Thống kê; mặc định monthly, có thể chọn resolution và khoảng thời gian |
| `/docs` | OpenAPI của backend đang chạy |

Hai endpoint dashboard nhận `resolution=hourly|daily|monthly`; `3h` được giữ cho
khả năng tương thích. Dùng `start` và `end` để giới hạn kỳ truy vấn.

```text
/api/dashboard?resolution=hourly&start=2025-12-30&end=2025-12-30
/api/admin/dashboard?resolution=hourly&start=2025-12-30T01:00:00Z&end=2025-12-30T05:00:00Z
/api/dashboard?resolution=daily&start=2025-12-01&end=2025-12-31
/api/dashboard?resolution=monthly
/api/dashboard/analytics?resolution=hourly&metric=co&start=2025-12-30&end=2025-12-30
```

- Timestamp trao đổi bằng UTC; offset khác được chuẩn hóa về UTC. Thời gian không
  ghi offset được hiểu là UTC.
- Ngày kết thúc dạng `YYYY-MM-DD` bao gồm toàn bộ ngày UTC; timestamp kết thúc
  chính xác được tính bao gồm mốc đó.
- Khoảng giờ phải ngắn hơn 31 ngày; khoảng ngày ngắn hơn 366 ngày. Muốn xem dài
  hơn, dùng monthly. Ví dụ toàn bộ 31 ngày lịch có thể hợp lệ vì thời lượng từ
  đầu ngày đầu đến cuối ngày cuối vẫn nhỏ hơn đúng 31 × 24 giờ.
- Mặc định hourly lấy bảy ngày lịch cuối của nguồn. Không dùng ngày hiện tại
  của máy để giả định nguồn có số liệu mới.
- Trung bình ngày cần ít nhất 18/24 slot giờ hợp lệ; tháng cần 75% số slot kỳ vọng.
  Trung bình qua nhiều kỳ dùng số mẫu hợp lệ làm trọng số.
- Số slot biểu thị độ phủ và trọng số, không phải số quan sát vật lý độc lập.
- Giao diện hiển thị thời điểm giờ ở UTC+7; kỳ tổng hợp ngày/tháng vẫn là lịch UTC.
- Dữ liệu thiếu giữ NULL. Lỗi nguồn trả 503; bộ lọc không hợp lệ trả 422.

## 5. Kiểm thử cho người phát triển

Các kiểm thử ETL cần thư viện ở `requirements-etl.txt`; bộ test backend cũng
cần pytest và httpx:

```bash
backend/.venv/bin/python -m pip install pytest httpx

PYTHONPATH=backend backend/.venv/bin/python -m pytest backend/tests -q
npm --prefix frontend test
npm --prefix frontend run lint
npm --prefix frontend run build
```

Các test đọc GRIB thật có thể bỏ qua nếu nguồn không có cục bộ; một số test số
học vẫn import thư viện ETL ngay khi nạp bộ test. Không dùng kết quả bỏ qua làm
bằng chứng đã kiểm chứng dữ liệu thật.

Kiểm tra trình duyệt bằng script có sẵn cần module Playwright, Chromium/Chrome
và hai server đang chạy ở cổng 8011/5181. Chạy server theo
[hướng dẫn FE–BE](run-dashboard.md#5-cấu-hình-khi-đổi-cổng-hoặc-thư-mục-dữ-liệu), rồi:

```bash
PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/usr/bin/google-chrome \
node scripts/check_hourly_dashboard.mjs /duong/dan/toi/playwright/index.mjs
```

Thay đường dẫn module và trình duyệt bằng vị trí trên máy. Script không thuộc
bước khởi động web thông thường.

## 6. Dữ liệu cũ và phạm vi thay đổi

Các generation cũ chỉ được dọn sau khi bộ mới qua kiểm chứng số liệu, API và giao
diện. [Danh sách đã xóa](../../reports/dashboard/science/deleted-files.json) là
biên bản của lần triển khai trước, không phải lệnh dọn dữ liệu định kỳ.

Không xóa GRIB nguồn, tệp địa lý hay test fixture để giải quyết lỗi API.
Toàn bộ hướng dẫn trên chỉ dùng pipeline dashboard độc lập, không chạy các
pipeline Bronze/Silver/Gold hoặc thay đổi kiến trúc Lakehouse.

## Phân cấp hành chính: 34 tỉnh/thành

- Hoàng Sa (`20333`) là khu vực trực thuộc Đà Nẵng (`48`).
- Trường Sa (`22736`) là khu vực trực thuộc Khánh Hòa (`56`).
- Parquet và API dùng 34 mã tỉnh/thành. Bộ lọc, KPI, xếp hạng và CSV cùng dùng
  các mã này; không đếm hai quần đảo thành hai tỉnh.
- Bản đồ vẫn có thể vẽ 36 hình học (tách đất liền/quần đảo để có tooltip riêng).
  Chọn quần đảo sẽ chọn tỉnh chủ quản, tô sáng cả phần đất liền và quần đảo;
  tooltip ghi rõ giá trị là số liệu toàn tỉnh/thành.

ETL mới tổng hợp trực tiếp trên ranh giới đầy đủ của tỉnh, bao gồm quần đảo.
Đối với generation cũ có 36 vùng rời nhau, có thể chuyển một lần:

```bash
PYTHONPATH=backend backend/.venv/bin/python -m app.etl.province_hierarchy
```

Lệnh này kiểm tra dữ liệu vùng gốc có đủ độ phủ hợp lệ, ghép theo **diện tích
hợp lệ**, rồi tính lại tháng từ các giá trị giờ đã ghép. Nếu vùng bị mất giá trị
hoặc không đủ độ phủ, lệnh dừng và yêu cầu tạo lại từ GRIB, không tự suy giá trị.
Generation mới được kiểm tra trước khi chuyển `CURRENT` nguyên tử; generation
cũ được giữ để khôi phục. Không chạy lại lệnh khi generation hiện tại đã có 34 tỉnh.
