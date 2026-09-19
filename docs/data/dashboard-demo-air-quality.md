# Thiết kế Dashboard Demo Chất lượng Không khí

## 1. Mục tiêu

Dashboard demo được chia thành hai nhóm người dùng:

- **User**: người dùng phổ thông muốn biết chất lượng không khí hiện tại, xu hướng gần đây và tình trạng tại khu vực quan tâm.
- **Admin / Management**: nhà quản lý hoặc người ra quyết định cần theo dõi xu hướng dài hạn, so sánh khu vực, phân tích phát thải và xác định khu vực cần ưu tiên.

Dữ liệu trong bản demo có thể sử dụng **mock data**, mục tiêu chính là thể hiện giao diện, luồng phân tích và các tính năng dashboard.

> **Phạm vi demo:** Đây là dashboard prototype sử dụng mock data hoặc dữ liệu đã tổng hợp để minh họa luồng tương tác và khả năng phân tích. Các chỉ số trong demo không dùng để đưa ra kết luận chuyên môn hoặc quyết định quản lý thực tế.

### Chuyển vai trò demo

- Có màn hình mở đầu hoặc toggle để chọn **User** / **Admin**.
- Mỗi vai trò chỉ hiển thị các trang và thao tác phù hợp với mục tiêu sử dụng của mình.

---

# 2. User Dashboard

## 2.1. Overview

### Thông tin chính

- AQI hiện tại.
- PM2.5.
- PM10.
- Nhiệt độ.
- Độ ẩm.
- Tốc độ gió.
- Chất ô nhiễm chính.
- Trạng thái chất lượng không khí.
- Xu hướng tăng/giảm so với hôm qua.

### Ví dụ

```text
AQI: 126 – Kém
PM2.5: 42 µg/m³
PM10: 65 µg/m³
Chất ô nhiễm chính: PM2.5
↑ 12% so với hôm qua
```

### Thành phần giao diện

- KPI Cards.
- Trend indicator.
- Thời gian cập nhật gần nhất.
- Tìm kiếm/chọn tỉnh hoặc dùng vị trí mặc định của bản demo.
- Reset filter.

### Cảnh báo và khuyến nghị

- Hiển thị màu theo trạng thái AQI trên KPI card, bản đồ và tooltip.
- Hiển thị một khuyến nghị ngắn phù hợp trạng thái, ví dụ: `AQI kém — hạn chế hoạt động ngoài trời kéo dài.`
- Khi không có dữ liệu, hiển thị trạng thái `Chưa có dữ liệu` thay vì hiển thị giá trị 0.

---

## 2.2. Air Quality Map

Hiển thị bản đồ Việt Nam theo tỉnh.

### Layer

- AQI.
- PM2.5.
- PM10.

### Tính năng

- Click tỉnh để xem chi tiết.
- Hover để xem nhanh các chỉ số.
- Click tỉnh sẽ lọc các biểu đồ còn lại.

### Popup ví dụ

```text
Hà Nội

AQI: 145
PM2.5: 48 µg/m³
PM10: 71 µg/m³
Xu hướng: ↑
```

---

## 2.3. Recent Trend

Cho phép theo dõi:

- 24 giờ.
- 7 ngày.
- 30 ngày.

### Biểu đồ

- Line chart AQI.
- Line chart PM2.5.
- Line chart PM10.

Có thể hiển thị thêm:

- Average.
- Min.
- Max.

---

## 2.4. History Compare

Cho phép so sánh:

- Hôm nay với hôm qua.
- Tháng này với tháng trước.
- Tháng này với cùng kỳ năm trước.

### Ví dụ

```text
PM2.5 tháng 9/2026 tăng 8.4%
so với tháng 9/2025.
```

### Biểu đồ

- Line chart.
- Bar chart so sánh kỳ.

---

## 2.5. Air Quality Detail

Hiển thị chi tiết các pollutant:

- PM2.5.
- PM10.
- O3.
- NO2.
- SO2.
- CO.

### Biểu đồ

- Pollutant bar chart.
- Pollutant trend chart.

Có thể hiển thị thêm:

```text
Chất ô nhiễm chính: PM2.5
Khung giờ xấu nhất: 18:00–21:00
Xu hướng: tăng
```

---

# 3. Admin / Management Dashboard

## 3.1. Executive Overview

Mục tiêu là giúp nhà quản lý nhìn nhanh tình hình chung.

### KPI

- PM2.5 trung bình.
- AQI trung bình.
- YoY change.
- Số ngày vượt ngưỡng.
- Tỉnh có PM2.5 cao nhất.
- Tỉnh tăng nhanh nhất.
- Tổng phát thải.
- Ngành phát thải lớn nhất.

### Ví dụ

```text
PM2.5 trung bình: 28.4 µg/m³
YoY: +12.7%
Số ngày vượt ngưỡng: 96
Tỉnh cao nhất: Hà Nội
Ngành phát thải lớn nhất: Manufacturing
```

### Biểu đồ

- Map.
- Long-term trend.
- Top provinces.
- Top emission sectors.

---

# 4. Spatial Analysis

Mục tiêu:

> Khu vực nào đang có chất lượng không khí kém hơn?

### Biểu đồ

- Choropleth map theo tỉnh.
- Ranking các tỉnh theo PM2.5.
- Ranking theo AQI.
- Ranking theo mức tăng YoY.

### Tính năng

```text
Vietnam
   ↓
Province
```

Click tỉnh trên bản đồ sẽ lọc toàn bộ dashboard.

---

# 5. Long-term Trend

Theo dõi xu hướng nhiều năm.

### Chỉ số

- PM2.5 trung bình năm.
- PM10 trung bình năm.
- YoY %.
- Thay đổi 5 năm.
- Số ngày vượt ngưỡng.

### Ví dụ

```text
2024: 24 µg/m³
2025: 27 µg/m³
2026: 30 µg/m³

2026 tăng 11.1% so với 2025.
```

### Biểu đồ

- Multi-year line chart.
- Annual bar chart.
- Year × Month heatmap.

---

# 6. Time Drill-down

Một trong các tính năng chính của dashboard Admin.

Luồng:

```text
Nhiều năm
   ↓
Năm
   ↓
Tháng
   ↓
Ngày
```

### Ví dụ

```text
2026: +14%
   ↓
Tháng 3: +31%
   ↓
12–18/03 có PM2.5 cao
```

### Tính năng

- Click chart để drill-down.
- Breadcrumb.
- Back.
- Compare previous period.
- Compare same period last year.

### Breadcrumb

```text
Vietnam > Hanoi > 2026 > March
```

---

# 7. Emission Analysis

Mục tiêu:

> Ngành nào đang phát thải nhiều nhất?

Hierarchy:

```text
Pollutant
   ↓
Sector
   ↓
Subsector
```

Ví dụ:

```text
PM2.5
   ↓
Manufacturing
   ↓
Cement
```

### KPI

- Tổng phát thải.
- YoY.
- Top sector.
- Top subsector.

### Biểu đồ

- Sector ranking.
- Emission trend.
- Sector share.
- Subsector ranking.
- Lớp phát thải theo tỉnh trên bản đồ.

### Tương tác theo tỉnh

- Dùng GeoJSON ranh giới tỉnh để minh họa phát thải được tổng hợp theo tỉnh.
- Click một tỉnh để xem tổng phát thải, top sector và top subsector của tỉnh đó.
- Có thể bật/tắt lớp phát thải trên bản đồ; đây là dữ liệu tổng hợp phục vụ demo, chưa khẳng định kết quả tính toán chuyên môn.

---

# 8. Factor Analysis

Mục tiêu là cho thấy các yếu tố môi trường có thể liên quan tới PM2.5.

Có thể demo:

```text
PM2.5 vs Wind Speed
PM2.5 vs Humidity
PM2.5 vs Temperature
```

### Biểu đồ

- Scatter plot.
- Dual-line time series.

### Ví dụ nội dung

```text
PM2.5 có xu hướng cao hơn trong các giai đoạn tốc độ gió thấp.
```

Chỉ nên gọi là:

```text
Relationship / Correlation
```

không kết luận quan hệ nhân quả.

---

# 9. Priority Areas

Mục tiêu:

> Khu vực nào cần được chú ý trước?

### Bảng ví dụ

| Tỉnh | PM2.5 | YoY | Ngày vượt ngưỡng | Trạng thái |
|---|---:|---:|---:|---|
| Hà Nội | 35 | +18% | 42 | Cần chú ý |
| Bắc Ninh | 32 | +14% | 38 | Cần chú ý |
| Đà Nẵng | 18 | -5% | 12 | Cải thiện |

Có thể tạo Priority dựa trên:

```text
PM2.5 cao
+
Xu hướng tăng
+
Nhiều ngày vượt ngưỡng
```

---

# 10. Tính năng chung

## Filters

- Province.
- Pollutant.
- Year.
- Month.
- Date range.
- Sector.

## Cross-filter

Ví dụ:

```text
Click Hà Nội trên map
```

→ các biểu đồ còn lại chuyển sang dữ liệu Hà Nội.

## Compare

Cho phép:

```text
Hà Nội vs Bắc Ninh
```

hoặc:

```text
2026 vs 2025
```

hoặc:

```text
March 2026 vs March 2025
```

## Khác

- Tooltip.
- Reset filter.
- Export chart.
- Export CSV.
- Breadcrumb.
- Show/hide map layer.
- Loading/empty state để minh họa khi dashboard đang tải hoặc không có dữ liệu theo bộ lọc.

---

# 11. Các biểu đồ chính nên có

| Biểu đồ | Mục đích |
|---|---|
| KPI Card | Thông tin tổng quan |
| Line Chart | Xu hướng theo thời gian |
| Horizontal Bar | Ranking tỉnh/ngành |
| Choropleth Map | So sánh không gian |
| Scatter Plot | Phân tích mối liên hệ |
| Heatmap | Year × Month hoặc mức độ theo thời gian |
| Calendar Heatmap | AQI/PM theo ngày |

---

# 12. Cấu trúc Demo cuối cùng

## User

```text
1. Overview
2. Map
3. Recent Trend
4. History Compare
5. Air Quality Detail
```

## Admin / Management

```text
1. Executive Overview
2. Spatial Analysis
3. Long-term Trend
4. Time Drill-down
5. Emission Analysis
6. Factor Analysis
7. Priority Areas
```

---

# 13. Mock Data đề xuất

Có thể dùng một bảng mock chính:

```text
province
date
aqi
pm25
pm10
o3
no2
so2
co
temperature
humidity
wind_speed
```

Bảng emissions:

```text
province
year
month
sector
subsector
pollutant
emission
```

Bảng summary:

```text
province
year
pm25_avg
pm10_avg
aqi_avg
yoy_change
exceedance_days
priority_level
```

---

# 14. Luồng demo đề xuất

Một kịch bản demo Admin:

```text
Dashboard cho thấy PM2.5 năm 2026 tăng 14%
        ↓
Click năm 2026
        ↓
Phát hiện tháng 3 tăng mạnh nhất
        ↓
Click tháng 3
        ↓
Xem các ngày có PM2.5 cao
        ↓
Chọn Hà Nội trên bản đồ
        ↓
Xem trend riêng của Hà Nội
        ↓
Xem emission sector
        ↓
Phát hiện Manufacturing là sector lớn nhất
        ↓
Xem Priority Areas
```

Luồng này thể hiện rõ:

```text
Overview
→ Detect
→ Drill-down
→ Compare
→ Analyze
→ Prioritize
```

Một kịch bản demo User:

```text
Chọn Hà Nội
        ↓
Xem AQI hiện tại, trạng thái và khuyến nghị
        ↓
Chuyển sang xu hướng 7 ngày
        ↓
So sánh với ngày hôm qua
        ↓
Xem chất ô nhiễm chính và khung giờ xấu nhất
```

---

# 15. Kết luận

Đối với bản demo, không cần triển khai toàn bộ logic xử lý dữ liệu thực tế.

Điểm cần thể hiện là:

- dashboard cho hai nhóm người dùng khác nhau;
- có phân tích theo không gian;
- có xu hướng theo thời gian;
- có drill-down;
- có so sánh;
- có phân tích phát thải;
- có phân tích yếu tố liên quan;
- có khả năng xác định khu vực cần ưu tiên.

Như vậy dashboard không chỉ là một hệ thống hiển thị AQI mà thể hiện được hướng phát triển thành một hệ thống hỗ trợ phân tích và ra quyết định.
