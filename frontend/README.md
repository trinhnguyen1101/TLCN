# Frontend

Cấu trúc React cho dashboard demo. Chưa khởi tạo Vite/React hoặc thêm dependency; khi bắt đầu triển khai, đặt các file khởi tạo (`main.tsx`, `App.tsx`) trong `src/app/`.

```text
frontend/
├── public/                 # Tài nguyên phục vụ trực tiếp: favicon, static files
└── src/
    ├── app/                # App shell, providers, cấu hình khởi tạo
    ├── assets/             # Ảnh, icon, font được bundle
    ├── components/
    │   ├── common/         # Thành phần dùng chung theo nghiệp vụ nhẹ
    │   ├── layout/         # Header, sidebar, dashboard layout
    │   └── ui/             # Button, card, modal, chart wrapper
    ├── features/           # Module theo nghiệp vụ
    │   ├── air-quality/    # AQI, pollutants, trends, alerts
    │   ├── emissions/      # Emission map, sector, subsector
    │   └── geography/      # GeoJSON, map, province selection
    ├── hooks/              # Custom React hooks
    ├── lib/                # Cấu hình thư viện ngoài (chart, map, query)
    ├── pages/
    │   ├── admin/          # Các trang dashboard Admin
    │   └── user/           # Các trang dashboard User
    ├── routes/             # Router và route guards theo vai trò
    ├── services/           # API client, mock data adapters
    ├── styles/             # Global CSS, theme, design tokens
    ├── types/              # Kiểu TypeScript dùng chung
    └── utils/              # Hàm tiện ích thuần
```

Khi demo, `services/` có thể trả mock data; chỉ cần thay adapter ở đây khi backend sẵn sàng, không làm thay đổi component hoặc feature.
