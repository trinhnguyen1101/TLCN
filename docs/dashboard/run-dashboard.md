# Chạy web dashboard: backend và frontend

[← Tài liệu dashboard](README.md)

Hướng dẫn dùng Bash trên Linux, macOS hoặc WSL, với **Python 3.12** và
**Node.js 24 kèm npm**. Mọi lệnh chạy từ thư mục gốc repository, trừ khi ghi rõ khác.

Khi chạy xong, bạn có:

| Thành phần | Địa chỉ |
| --- | --- |
| User Dashboard | <http://localhost:5173/user> |
| Admin Dashboard | <http://localhost:5173/admin> |
| Kiểm tra backend | <http://127.0.0.1:8000/api/health> |
| Tài liệu API | <http://127.0.0.1:8000/docs> |

## 1. Chuẩn bị môi trường và dữ liệu

Vào thư mục dự án. Ví dụ trên máy hiện tại:

```bash
cd /home/zaneth/Projects/TLCN
```

Đổi đường dẫn trên nếu repository nằm ở vị trí khác.

**Chỉ ở lần cài đầu**, tạo môi trường và cài thư viện:

```bash
python3.12 -m venv backend/.venv
backend/.venv/bin/python -m pip install -r backend/requirements.txt
npm --prefix frontend ci
```

Nếu `backend/.venv` và `frontend/node_modules` đã được cài, có thể bỏ qua các lệnh này.
Không cần kích hoạt virtualenv vì các lệnh dùng trực tiếp Python trong `backend/.venv`.

**Backend cần bộ Parquet đã tạo.** Thư mục phục vụ mặc định:

```text
backend/data/samples/cams/eac4_provinces/
├── CURRENT
└── runs/<mã-trong-CURRENT>/
    ├── manifest.json
    ├── observations/<chỉ-số>/<năm>/*.parquet
    └── monthly/*.parquet
```

Trong workspace đã hoàn tất chuyển đổi, chỉ cần chạy web ở bước 2.
Bản clone mới có thể thiếu `observations/` vì các tệp lớn không được đưa vào Git.
Chỉ có `CURRENT` và manifest chưa đủ: nếu thiếu Parquet giờ, làm theo
[phần tạo dữ liệu](data-processing.md#2-tạo-parquet-từ-grib) trước khi chạy web.
Không cần chạy lại ETL mỗi lần mở dashboard.

## 2. Terminal thứ nhất: chạy backend

Giữ terminal này chạy tại repository root:

```bash
DASHBOARD_DATA_SOURCE=parquet \
backend/.venv/bin/python -m uvicorn app.main:app \
  --app-dir backend --host 127.0.0.1 --port 8000 --reload
```

Khi thấy `Application startup complete`, backend đã khởi động.
`--reload` dùng khi phát triển, giúp nạp lại code backend sau khi sửa.

## 3. Terminal thứ hai: chạy frontend

Mở terminal mới, vào cùng thư mục gốc rồi chạy:

```bash
cd /home/zaneth/Projects/TLCN

VITE_DASHBOARD_SOURCE=parquet \
API_PROXY_TARGET=http://127.0.0.1:8000 \
npm --prefix frontend run dev -- --host 127.0.0.1 --port 5173 --strictPort
```

Mở [User Dashboard](http://localhost:5173/user) hoặc
[Admin Dashboard](http://localhost:5173/admin).

`--strictPort` giúp giữ đúng cổng 5173: nếu cổng bận, Vite báo lỗi thay vì tự đổi
sang cổng khác. Giữ cả hai terminal chạy; nhấn **Ctrl+C** trong từng terminal để dừng.

## 4. Kiểm tra kết nối FE → BE

Frontend gọi `/api` trên cổng 5173. Vite chuyển tiếp các request đó đến backend
ở cổng 8000:

```text
Trình duyệt :5173/user → Vite /api/dashboard → FastAPI :8000 → Parquet
Trình duyệt :5173/admin → Vite /api/admin/dashboard → FastAPI :8000 → Parquet
```

Trong terminal khác, kiểm tra lần lượt:

```bash
# Backend đang hoạt động: trả {"status":"ok"}
curl --fail --silent --show-error http://127.0.0.1:8000/api/health

# Đi qua frontend proxy và đọc dữ liệu thật của một ngày có trong nguồn
curl --fail --silent --show-error \
  'http://127.0.0.1:5173/api/dashboard?resolution=hourly&start=2025-12-30&end=2025-12-30' \
  -o /tmp/dashboard-check.json
```

Lệnh thứ hai thành công khi trả HTTP 200; JSON nằm ở `/tmp/dashboard-check.json`.
`/api/health` chỉ xác nhận tiến trình đang chạy, chưa xác nhận Parquet đọc được.

Trên web, thử chọn tỉnh, CO hoặc PM2.5, đổi một mốc giờ và mở bảng chi tiết.
Bản đồ, thẻ chỉ số, biểu đồ và bảng phải phản ánh cùng bộ lọc. Ngày/tháng tổng hợp
vẫn theo lịch UTC; các thời điểm giờ được hiển thị UTC+7.

## 5. Cấu hình khi đổi cổng hoặc thư mục dữ liệu

| Biến | Đọc ở đâu? | Ý nghĩa |
| --- | --- | --- |
| `DASHBOARD_DATA_SOURCE=parquet` | Backend | Chọn dữ liệu Parquet độc lập |
| `DASHBOARD_PARQUET_PATH` | Backend | Đổi thư mục chứa `CURRENT` và `runs/`; nên dùng đường dẫn tuyệt đối |
| `API_PROXY_TARGET` | Vite dev/preview | Địa chỉ backend để chuyển tiếp `/api` |
| `VITE_DASHBOARD_SOURCE=parquet` | Frontend | Dùng giao diện ở chế độ Parquet |

Nếu đổi backend sang 8011, đổi cả `--port 8011` ở bước 2 và
`API_PROXY_TARGET=http://127.0.0.1:8011` ở bước 3.
Có thể đổi cổng frontend bằng `--port 5181`; khi đó mở web tại cổng 5181.

Backend nhận biến môi trường từ shell, **không tự đọc tệp `.env`**.
Frontend có thể dùng `frontend/.env.local`, dựa trên
[`.env.example`](../../frontend/.env.example). Sau khi sửa cấu hình Vite, khởi động lại frontend.
Các biến đặt trực tiếp trong lệnh trên được ưu tiên hơn giá trị trong tệp cấu hình.

## 6. Build và xem thử bản build

Giữ backend ở bước 2 chạy. Tại terminal khác:

```bash
VITE_DASHBOARD_SOURCE=parquet npm --prefix frontend run build

API_PROXY_TARGET=http://127.0.0.1:8000 \
npm --prefix frontend run preview -- --host 127.0.0.1 --port 4173 --strictPort
```

Mở <http://localhost:4173/user> hoặc <http://localhost:4173/admin>.
Tệp build nằm trong `frontend/dist/app/`.

Vite preview dùng để kiểm tra cục bộ. Khi triển khai, phục vụ thư mục build và
cấu hình máy chủ chuyển tiếp `/api/*` đến FastAPI, giữ nguyên tiền tố `/api`.

## 7. Xử lý lỗi thường gặp

| Hiện tượng | Kiểm tra / cách xử lý |
| --- | --- |
| `Address already in use` / `Port ... is already in use` | Dừng phiên dev cũ bằng Ctrl+C, hoặc đổi cổng và proxy theo bước 5. |
| FE báo không tải được dữ liệu, proxy báo `ECONNREFUSED` | Backend phải đang chạy; kiểm tra `API_PROXY_TARGET` trùng host/cổng backend. |
| API trả 503 | Kiểm tra terminal backend, `CURRENT`, manifest và các partition trong generation đang dùng. Nếu thiếu dữ liệu, [tạo lại Parquet](data-processing.md#2-tạo-parquet-từ-grib). |
| Có Parquet nhưng vẫn đọc sai thư mục | Kiểm tra biến `DASHBOARD_PARQUET_PATH` đang được đặt trong shell. Dùng đúng thư mục chứa `CURRENT`, không trỏ thẳng vào một tệp Parquet. |
| API trả 422 khi chọn ngày | Kiểm tra thứ tự bắt đầu/kết thúc và giới hạn khoảng giờ/ngày trong [quy ước API](data-processing.md#4-quy-ước-api-và-thời-gian). |
| Chưa có dữ liệu ở ngày hôm nay | Đây là dữ liệu lịch sử; chọn khoảng nằm trong `metadata.observationStart` và `observationEnd`. |
| AQI trống hoặc không thấy dữ liệu phát thải | Nguồn này không cung cấp AQI hợp lệ hay phát thải theo ngành; dashboard tiếp tục hiển thị nồng độ. |
| Thiếu module Python hoặc không tìm thấy Vite | Cài lại dependency đúng virtualenv và chạy `npm --prefix frontend ci` ở bước 1. |

Để chạy kiểm thử, kiểm chứng GRIB hoặc tạo generation mới, xem
[xử lý và kiểm tra dữ liệu](data-processing.md). Không cần thực hiện các bước đó
chỉ để khởi động lại web đã có dữ liệu.
