# Sửa phân cấp tỉnh/thành dashboard — 30/10/2026

## Kết quả dữ liệu

- Hoàng Sa (`20333`) thuộc Đà Nẵng (`48`); Trường Sa (`22736`) thuộc Khánh Hòa (`56`).
- API và Parquet dùng **34 tỉnh/thành**, 18 chỉ số, 123.392.664 dòng giờ.
- Generation đang hoạt động: `b52d8b7368414758b151fed3f3b2531a`.
- Parquet được chuyển trong generation `e07dd55ba65b4362a8fb5f3b554bf09f`;
  generation hoạt động là bản hoàn thiện metadata ranh giới nguồn, dùng hardlink
  tới cùng Parquet, không chuyển đổi số liệu lần thứ hai.
- Generation gốc 36 vùng `5febe7dde83c41fdac2e3ba5a5532844` được giữ để khôi phục.
- ETL mới dùng ranh giới đầy đủ của tỉnh. Dữ liệu hiện có được chuyển bằng
  `app.etl.province_hierarchy`: gộp hai vùng rời nhau theo diện tích hợp lệ, trước
  khi tính lại chuỗi tháng. Không lấy trung bình đơn giản hai vùng, không suy thêm
  dữ liệu thiếu và không tính lại mật độ khí trong API.
- Chỉ chuyển khi hai vùng có giá trị hợp lệ và độ phủ bằng độ phủ lưới đã kiểm chứng.
  Nếu không, công cụ dừng và yêu cầu tạo lại từ GRIB.
- Trọng số sau chuyển khớp giao diện tích tính trực tiếp trên ranh giới đầy đủ,
  sai số lớn nhất `5.551115123125783e-17`.
- Bản đồ giữ 36 hình học để tooltip phân biệt quần đảo; thao tác chọn và màu đều
  dùng tỉnh chủ quản. Tooltip ghi rõ giá trị của toàn tỉnh/thành. Khi chọn tỉnh,
  cả phần đất liền và quần đảo được tô đường viền.
- Không sửa GRIB nguồn hay thành phần Lakehouse.

## Kiểm chứng

- Backend: **52 passed**, một cảnh báo deprecation từ Starlette/httpx.
- Frontend: 4 tệp kiểm thử đạt; lint và build đạt.
- Trình duyệt: **6/6 trường hợp đạt** (`/user`, `/admin` × 1440/768/390 px),
  kiểm tra 34 tỉnh trong API, 35 mục lựa chọn gồm Toàn quốc, chọn hai quần đảo
  về đúng tỉnh chủ quản và highlight cả hai phần hình học; không có lỗi console
  hoặc tràn ngang.
- Kiểm thử phân cấp mới: 34 mã hành chính, bảo toàn hình học, trung bình theo diện
  tích và từ chối đầu vào thiếu.
- `/api/dashboard` và `/api/admin/dashboard`: 34 snapshot, 816 dòng cho đủ 24 giờ
  ngày 30/12/2025; không còn mã quần đảo như tỉnh riêng.
- Tháng 12/2025: 1.054 dòng ngày, 34 dòng tháng; bảy chất ô nhiễm được kiểm tra lại
  bằng giá trị giờ. Analytics có 816/816 giá trị CO hợp lệ ở ngày kiểm chứng.
- Bốn khí được đối chiếu độc lập với GRIB tại sáu mốc trên toàn bộ 34 tỉnh; đạt.
- Bằng chứng chi tiết: [integration.json](science/integration.json),
  [backend-tests.txt](science/backend-tests.txt),
  [browser-results.json](science/browser-results.json),
  [nhật ký chuyển dữ liệu](province-hierarchy-migration.txt).

## Mã và tài liệu

- `backend/app/etl/regions.py`: mặc định trả ranh giới hành chính đầy đủ.
- `backend/app/etl/export_regions.py`: tách hình học chỉ để hiển thị bản đồ.
- `backend/app/etl/province_hierarchy.py`: chuyển generation hiện có, xuất bất biến
  và chuyển `CURRENT` nguyên tử sau kiểm tra.
- `backend/app/etl/eac4.py`: metadata phân cấp khi tạo generation mới từ GRIB.
- `frontend/src/features/geography/ProvinceBoundaryLayer.tsx`: chọn, tooltip và
  highlight theo tỉnh chủ quản.
- `backend/tests/test_province_hierarchy.py`, `scripts/verify_hourly_dashboard.py`,
  `scripts/check_hourly_dashboard.mjs`: kiểm thử hồi quy phân cấp.
- Tài liệu dashboard, frontend README cập nhật để phân biệt 34 tỉnh với 36 hình học.
