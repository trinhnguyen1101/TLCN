# Thiết lập web dashboard

## 1. Yêu cầu

- Python **3.12**, Node.js **24** kèm npm.
- Các lệnh dùng Bash (Linux/macOS/WSL), chạy từ **thư mục gốc dự án**.
- Không cần Docker, Airflow, Spark hay MinIO để chạy dashboard.

## 2. Chạy backend

```bash
python3.12 -m venv backend/.venv
backend/.venv/bin/python -m pip install -r backend/requirements.txt
backend/.venv/bin/python -m uvicorn app.main:app --app-dir backend --reload --port 8000
```

API dùng bộ số liệu hiện tại trong **`backend/data/samples/cams/eac4_provinces/`**. Mẫu đã có sẵn, không cần chạy ETL. Đây là dữ liệu tạm để phát triển dashboard, **chưa qua pipeline xử lý/kiểm định chính thức**, không lưu ở `data/gold/`.

- Kiểm tra API: <http://localhost:8000/api/health>.
- Kiểm tra dữ liệu: <http://localhost:8000/api/dashboard>.
- Tài liệu API: <http://localhost:8000/docs>.

## 3. Chạy frontend

Mở terminal thứ hai tại thư mục gốc:

```bash
cd frontend
npm ci
npm run dev
```

Mở URL Vite in ra, mặc định <http://localhost:5173>. Frontend chuyển tiếp `/api` đến `http://127.0.0.1:8000`.

Nếu đổi địa chỉ API, sao chép `frontend/.env.example` thành `frontend/.env.local`, sửa `API_PROXY_TARGET` rồi khởi động lại Vite. Backend nhận biến môi trường từ terminal, không tự đọc `.env`.

## 4. Kiểm tra và build

Từ thư mục gốc:

```bash
npm --prefix frontend run lint
npm --prefix frontend run build
backend/.venv/bin/python -m pip install -r backend/requirements-dev.txt
backend/.venv/bin/python -m pytest backend/tests -q
```

Xem bản build bằng `npm --prefix frontend run preview` khi API vẫn chạy. Khi triển khai, phục vụ **`frontend/dist/app/`** và cấu hình reverse proxy `/api/*` đến FastAPI, giữ nguyên `/api`. Không dùng Vite preview làm máy chủ production.

## Lỗi thường gặp

- **API trả 503:** kiểm tra log, file `CURRENT` và thư mục `runs/` trong bộ mẫu. Nếu dùng nơi lưu khác, đặt `DASHBOARD_PARQUET_PATH` trước khi chạy API. `/api/health` chỉ kiểm tra tiến trình, không xác nhận dữ liệu sẵn sàng.
- **Không tải số liệu:** kiểm tra cổng backend và `API_PROXY_TARGET`, sau đó bấm **Thử lại**. Tải lại trang sau khi thay bộ dữ liệu.
- **AQI/phát thải trống:** bộ CAMS hiện tại không có phát thải theo ngành và chưa tính AQI. Bản đồ dùng trung bình tháng; tỉnh không đủ độ phủ sẽ để trống.

Chỉ khi cần tạo lại mẫu từ GRIB mới cài `backend/requirements-etl.txt` và chạy công cụ chuyển đổi theo [backend/README.md](../backend/README.md). Công cụ mặc định cũng ghi vào `backend/data/samples/`.
