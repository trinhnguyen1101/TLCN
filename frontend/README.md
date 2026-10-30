# Frontend dashboard

React, TypeScript, Vite, Tailwind CSS và Leaflet.

**[Hướng dẫn chạy đầy đủ FE–BE](../docs/dashboard/run-dashboard.md)** là tài liệu
chính để cài môi trường, chạy server, đổi cổng, kiểm tra proxy và xem bản build.

## Route và dữ liệu

| Route | API |
| --- | --- |
| `/user` | `GET /api/dashboard` |
| `/admin` | `GET /api/admin/dashboard` |

Vite dev/preview chuyển tiếp `/api` đến `API_PROXY_TARGET`, mặc định
`http://127.0.0.1:8000`. Xem [`.env.example`](.env.example).
Bản build nằm trong `dist/app/`; khi triển khai, máy chủ cần chuyển tiếp `/api/*`
đến FastAPI và giữ nguyên tiền tố.

Frontend mặc định xem hourly. API dùng UTC; mốc giờ hiển thị theo UTC+7. Bộ lọc
tỉnh, chỉ số và kỳ dữ liệu được dùng chung cho bản đồ, thẻ, biểu đồ và bảng.
Truy vấn thời gian có giới hạn, dùng cache ngắn và hủy/bỏ qua request cũ.
Frontend không đọc GRIB, không tính mật độ và không tự nội suy dữ liệu thiếu.

Bảy chỉ số chính là PM2.5, PM10, PM1, NO₂, SO₂, CO và O₃. CO dùng mg/m³; sáu
chất còn lại dùng µg/m³. Admin tách khí tổng cột/AOD và khí tượng thành nhóm riêng.
Thông tin nguồn và phương pháp mở từ biểu tượng thông tin trên dashboard.

## Cấu trúc code

| Thư mục / tệp | Vai trò |
| --- | --- |
| `src/App.tsx` | Chọn route User/Admin; tải trang theo nhu cầu |
| `src/pages/user/UserDashboard.tsx` | Bản đồ, nồng độ, xu hướng và bảng User |
| `src/pages/admin/` | KPI, bản đồ, xếp hạng và các tab phân tích |
| `src/features/dashboard/api/`, `hooks/` | Gọi API, cache, loading, retry và request cũ |
| `src/features/dashboard/model/` | Đồng bộ bộ lọc, thời gian, đơn vị và thống kê |
| `src/features/dashboard/components/` | Bộ lọc, KPI, bảng và thông tin nguồn |
| `src/features/geography/` | Bản đồ Leaflet và tương tác chọn vùng |
| `src/features/analytics/` | Biểu đồ SVG và xuất biểu đồ |
| `src/components/ui/` | Điều khiển, trạng thái và xuất dữ liệu dùng chung |
| `src/index.css` | Tailwind, theme và kiểu Leaflet |
| `public/data/` | GeoJSON ranh giới và bản đồ nền được phục vụ tĩnh |

## Quy ước giao diện

- Dùng theme token và Tailwind utility đã có; giữ tên class động ở dạng đầy đủ.
- Giữ các trạng thái loading, lỗi, rỗng và thiếu dữ liệu riêng biệt. Không thay NULL bằng 0.
- Bản đồ giữ các layer khi đổi bộ lọc. ResizeObserver cập nhật kích thước Leaflet.
- Màu nồng độ có đơn vị vật lý; không gán mức sức khỏe AQI cho nồng độ thô.
- CSV xuất giá trị đúng đơn vị và timestamp UTC, không phải chuỗi đã định dạng để hiển thị.
- Điều khiển chọn vùng/chỉ số hỗ trợ tìm kiếm và bàn phím.

## Tệp bản đồ

Frontend dùng `public/data/vietnam-provinces.geojson` và
`public/data/world-countries.geojson` ngay từ cùng origin, không cần Python/GIS
khi chỉ chạy frontend. Bộ dữ liệu có 34 tỉnh/thành; Hoàng Sa thuộc Đà Nẵng (48),
Trường Sa thuộc Khánh Hòa (56). Bản đồ giữ 36 hình học để hiển thị riêng phần
đất liền và quần đảo, nhưng dùng mã tỉnh chủ quản để chọn và tra số liệu.
Không đổi mã tỉnh hoặc đơn giản hóa ranh giới khi chỉ sửa layout.

Bản đồ nền dựa trên [Natural Earth](https://www.naturalearthdata.com/about/terms-of-use/),
không tải image tiles khi pan/zoom. Nếu thay tài sản bản đồ, phải kiểm tra lại
đường biên chung giữa ranh giới Việt Nam và nền xung quanh.

## Lệnh phát triển

Chạy từ repository root:

```bash
npm --prefix frontend test
npm --prefix frontend run lint
npm --prefix frontend run build
```

Xem [hướng dẫn dữ liệu và kiểm thử](../docs/dashboard/data-processing.md#5-kiểm-thử-cho-người-phát-triển)
để chạy kiểm tra trình duyệt hoặc đối chiếu API với nguồn GRIB.
