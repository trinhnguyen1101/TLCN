# Từ điển dữ liệu trong thư mục `data/`

Ngày kiểm tra: **2026-09-19**. Tài liệu mô tả các file đang có trên máy, các trường dữ liệu, ý nghĩa, đơn vị và những điểm cần chú ý khi đọc. Đây là cấu trúc dữ liệu nguồn, không phải schema cơ sở dữ liệu đích; thiết kế lưu trữ được trình bày riêng trong [database-schema.md](database-schema.md).

## 1. Phạm vi và danh mục file

Đã kiểm kê **368 file**, tổng cộng **1.386.140.435 byte**: 367 file trong `landing/` và một file `data/.gitkeep`. Không có file đuôi `.grid`; dữ liệu lưới thực tế dùng đuôi **`.grib`**.

| Nhóm | Vị trí tính từ `data/` | Số file | Nội dung |
|---|---|---:|---|
| CAMS EAC4 theo năm | `landing/CAMS/EAC4/yearly/<biến>/<biến>_<năm>_vietnam.grib` | 322 | 14 biến × 23 năm, từ 2003 đến 2025 |
| CAMS EAC4 đã ghép | `landing/CAMS/EAC4/merged/<biến>_2003_2025_vietnam.grib` | 14 | Cùng dữ liệu trên, ghép thành một file cho mỗi biến |
| WAQI | `landing/waqi/historical/*.csv` | 17 | Chuỗi chất lượng không khí theo địa điểm và ngày |
| Climate TRACE | `landing/climate_trace/climate_trace_vietnam/` | 3 CSV | Phát thải quốc gia theo năm/tháng và phát thải theo nguồn |
| Danh mục hành chính | `landing/reference/vietnam_administrative_divisions/` | 7 | 1 CSV, 5 JSON và 1 NDJSON; gồm dữ liệu và schema |
| Metadata hành chính | `landing/reference/vietnam_administrative_divisions/metadata/` | 4 | `source.json`, `README.md`, `CITATION.cff`, `LICENSE` |
| File giữ thư mục | `.gitkeep` | 1 | Không chứa bảng dữ liệu |

Theo phần mở rộng: **336 GRIB, 21 CSV, 6 JSON, 1 NDJSON, 1 CFF, 1 Markdown, 1 file LICENSE không có phần mở rộng và 1 `.gitkeep`**.

Các thư mục `data/bronze/`, `data/silver/`, `data/gold/` và `data/landing/ERA5/single_levels/` đang trống. Chưa có dữ liệu ERA5 để xác định các trường hoặc đơn vị thực tế.

Quy ước trong tài liệu:

- **Đọc trực tiếp**: tên cột, số dòng, giá trị, cấu trúc JSON và metadata GRIB đã kiểm tra từ file.
- **Diễn giải theo nhà cung cấp**: ý nghĩa khoa học/đơn vị được đối chiếu tài liệu nguồn, dẫn liên kết tại phần tương ứng.
- **Chưa xác minh**: file không cung cấp đủ metadata hoặc lịch sử xuất dữ liệu. Không tự gán một giả định thành thông tin đã xác nhận.
- CSV không lưu kiểu dữ liệu như một cơ sở dữ liệu. Cột “kiểu khi đọc” dưới đây là kiểu nên dùng sau khi parse; mã định danh phải được giữ dạng chuỗi.

## 2. CAMS EAC4 — dữ liệu lưới GRIB

### 2.1. Cách tổ chức và đơn vị của một bản ghi

Mỗi file là một chuỗi **GRIB message**. Mỗi message biểu diễn **một biến tại một thời điểm trên 242 điểm lưới**. Một message không tương đương một điểm đo.

Sau giải mã và loại trùng, có thể hình dung một biến dưới dạng:

```text
value[time, latitude, longitude]
shape = (67.208 thời điểm, 22 vĩ độ, 11 kinh độ)

Nếu chuyển thành bảng dài:
variable | valid_time | latitude | longitude | value | units
```

Các tên `time`, `valid_time`, `latitude`, `longitude`, `value` ở ví dụ bảng dài là cách biểu diễn sau giải mã; GRIB không có một hàng header CSV chứa các cột đó. Các bảng metadata bên dưới dùng tên khóa ecCodes trả về.

Toàn bộ 336 file là **GRIB edition 1**. Header của mọi message được kiểm tra cấu trúc; metadata đầu/cuối của mỗi file được giải mã bằng ecCodes. Mỗi file chỉ có một chữ ký trường và một chữ ký lưới trong phạm vi kiểm tra header.

CAMS EAC4 là sản phẩm tái phân tích thành phần khí quyển. Lưới đều 0,75° và dữ liệu analysis mỗi 3 giờ phù hợp với [tài liệu CAMS của ECMWF](https://confluence.ecmwf.int/spaces/CKB/pages/83395896/CAMS%2BReanalysis%2Bdata%2Bdocumentation). Phạm vi năm ghi dưới đây lấy từ file cục bộ.

### 2.2. Danh mục đầy đủ 14 biến

Mỗi tên ở cột đầu có **23 file năm 2003–2025** và **1 file merged** theo mẫu đường dẫn ở mục 1. `shortName`, `paramId` và đơn vị được đọc bằng ecCodes; ý nghĩa tiếng Việt diễn giải từ tên đại lượng.

| Tiền tố tên file / thư mục biến | `shortName` | `paramId` | Đơn vị gốc | Ý nghĩa |
|---|---|---:|---|---|
| `aod550` | `aod550` | 210207 | `~` — không thứ nguyên | Tổng độ dày quang học aerosol ở bước sóng 550 nm; đặc trưng suy giảm ánh sáng do aerosol trên cột khí quyển |
| `co_column` | `tcco` | 210127 | kg/m² | Tổng khối lượng carbon monoxide (CO) trong cột khí quyển trên một đơn vị diện tích |
| `no2_column` | `tcno2` | 210125 | kg/m² | Tổng cột nitrogen dioxide (NO₂) |
| `o3_column` | `gtco3` | 210206 | kg/m² | Tổng cột ozone (O₃); tên ecCodes là `GEMS Total column ozone` |
| `so2_column` | `tcso2` | 210126 | kg/m² | Tổng cột sulphur dioxide (SO₂) |
| `pm1` | `pm1` | 210072 | kg/m³ | Nồng độ khối lượng bụi có đường kính ≤ 1 µm |
| `pm2p5` | `pm2p5` | 210073 | kg/m³ | Nồng độ khối lượng bụi có đường kính ≤ 2,5 µm |
| `pm10` | `pm10` | 210074 | kg/m³ | Nồng độ khối lượng bụi có đường kính ≤ 10 µm |
| `t2m` | `2t` | 167 | K | Nhiệt độ không khí ở độ cao 2 m |
| `d2m` | `2d` | 168 | K | Nhiệt độ điểm sương ở độ cao 2 m; liên quan lượng hơi nước trong không khí |
| `sp` | `sp` | 134 | Pa | Áp suất tại bề mặt địa hình |
| `mslp` | `msl` | 151 | Pa | Áp suất quy về mực nước biển trung bình |
| `u10` | `10u` | 165 | m/s | Thành phần gió theo hướng đông–tây ở độ cao 10 m; chiều dương về phía đông |
| `v10` | `10v` | 166 | m/s | Thành phần gió theo hướng bắc–nam ở độ cao 10 m; chiều dương về phía bắc |

Tên file không luôn trùng với tên biến giải mã: ví dụ `t2m → 2t`, `u10 → 10u`, `o3_column → gtco3`. Khi xác định biến nên giữ cả tên file, `paramId` và `shortName`. ECMWF cung cấp [cơ sở dữ liệu tham số](https://codes.ecmwf.int/grib/param-db/) để tra cứu mã đại lượng.

Các trường `*_column` là đại lượng tích phân theo cột khí quyển; không thể đổi trực tiếp kg/m² thành nồng độ gần mặt đất µg/m³ chỉ bằng một hệ số đổi đơn vị. AOD cũng không phải nồng độ PM2.5.

### 2.3. Trường metadata, thời gian và giá trị

| Khóa / trường giải mã | Kiểu | Giá trị quan sát hoặc ý nghĩa |
|---|---|---|
| `edition` | integer | Phiên bản định dạng GRIB; ở đây là `1` |
| `paramId` | integer | Mã đại lượng ECMWF; xem bảng 14 biến |
| `shortName` | string | Tên ngắn của biến do ecCodes diễn giải |
| `name` | string | Tên đầy đủ của đại lượng |
| `units` | string | Đơn vị gốc, ví dụ `kg m**-3`, `kg m**-2`, `K`, `Pa` |
| `dataDate` | integer `YYYYMMDD` | Ngày tham chiếu, ví dụ `20030101` |
| `dataTime` | integer `HHMM` | Giờ tham chiếu UTC; `0` nghĩa là 00:00, `2100` nghĩa là 21:00 |
| `validityDate`, `validityTime` | integer | Ngày/giờ có hiệu lực của trường dữ liệu; bằng ngày/giờ tham chiếu ở các message đầu/cuối đã giải mã |
| `stepType` | string | `instant`: giá trị tức thời, không phải tổng tích lũy trong kỳ |
| `stepRange` | string | `0`: bước thời gian tính từ thời điểm tham chiếu bằng 0 |
| `dataType` | string | `an`: analysis / phân tích |
| `experimentVersionNumber` | string | `eac4`: định danh phiên bản thí nghiệm/sản phẩm |
| `typeOfLevel` | string | `surface` trong metadata đầu/cuối các file |
| `level` | number | `0` trong metadata; không dùng giá trị này để suy rằng biến 2 m/10 m được đo ở độ cao 0 m |
| `values` | mảng số thực | 242 giá trị đã giải mã, theo thứ tự quét lưới |
| `latitudes`, `longitudes` | mảng số thực | Tọa độ tương ứng của từng phần tử trong `values`, đơn vị độ |
| `packingType` | string | `grid_simple` ở message đầu của 14 file merged đã lấy mẫu |
| `bitsPerValue` | integer | Mẫu đầu: 24 bit cho aerosol/tổng cột/PM; 16 bit cho nhiệt độ, áp suất và gió. Đây là thông tin đóng gói, không phải độ chính xác của phép đo |
| `numberOfMissing` | integer | Số điểm thiếu trong message; bằng 0 ở 14 message đầu đã lấy mẫu, chưa kết luận cho toàn bộ chuỗi |

`surface` ở metadata là cách mã hóa sản phẩm single-level này. Ý nghĩa vật lý phải dựa thêm vào `paramId`/`name`: có biến tại 2 m, 10 m, bề mặt và cả tổng cột.

Thời gian đọc được: **2003-01-01 00:00 UTC → 2025-12-31 21:00 UTC**. Sau loại trùng, mỗi biến có **67.208 mốc**, đủ các giờ `00, 03, 06, 09, 12, 15, 18, 21 UTC`; kiểm tra tập thời gian trong 14 file merged không thấy thiếu mốc hoặc mốc lệch bước 3 giờ.

### 2.4. Cấu trúc lưới không gian

| Khóa | Giá trị | Ý nghĩa |
|---|---:|---|
| `gridType` | `regular_ll` | Lưới kinh độ–vĩ độ đều |
| `Ni` | 11 | Số điểm theo kinh độ |
| `Nj` | 22 | Số điểm theo vĩ độ |
| `numberOfPoints` | 242 | `11 × 22` điểm trong mỗi message |
| `latitudeOfFirstGridPointInDegrees` | 24,00 | Vĩ độ điểm đầu |
| `longitudeOfFirstGridPointInDegrees` | 102,00 | Kinh độ điểm đầu |
| `latitudeOfLastGridPointInDegrees` | 8,25 | Vĩ độ điểm cuối |
| `longitudeOfLastGridPointInDegrees` | 109,50 | Kinh độ điểm cuối |
| `iDirectionIncrementInDegrees` | 0,75 | Bước kinh độ |
| `jDirectionIncrementInDegrees` | 0,75 | Độ lớn bước vĩ độ |
| `iScansNegatively` | 0 | Kinh độ tăng khi quét theo hàng |
| `jScansPositively` | 0 | Vĩ độ giảm khi chuyển hàng |
| `jPointsAreConsecutive` | 0 | Các điểm liên tiếp chạy theo kinh độ |
| `alternativeRowScanning` | 0 | Không đảo chiều quét xen kẽ giữa các hàng |

Với đúng lưới đã kiểm tra này, chỉ số bắt đầu từ 0:

```text
latitude[row]    = 24.00 - 0.75 × row       (row = 0..21)
longitude[col]   = 102.00 + 0.75 × col     (col = 0..10)
flattened_index  = row × 11 + col
```

Ba điểm đầu: `(24.00, 102.00)`, `(24.00, 102.75)`, `(24.00, 103.50)`. Điểm cuối: `(8.25, 109.50)`. Đây là lưới chữ nhật bao quanh khu vực Việt Nam, có cả điểm ngoài lãnh thổ/ngoài đất liền; tên `_vietnam` không phải một lớp ranh giới quốc gia.

### 2.5. Ví dụ giá trị và kết quả kiểm tra

Tại **2003-01-01 00:00 UTC**, điểm **24°N, 102°E**, message đầu cho:

| Biến | Giá trị gốc | Cách diễn giải/chuyển đơn vị |
|---|---:|---|
| `pm2p5` | `3.9238443605427165e-08` kg/m³ | Khoảng `39,2384` µg/m³; nhân `10^9` |
| `t2m` | `279.4189453125` K | Khoảng `6,2689` °C; trừ `273,15` |
| `sp` | `83964.8125` Pa | `839,648125` hPa; chia `100` |
| `aod550` | `0.020398695021867752` | Không có đơn vị khối lượng |
| `u10` | `-0.1279296875` m/s | Thành phần gió hướng về phía tây |

Giá trị trên là **mẫu một thời điểm/một điểm**, không phải thống kê toàn bộ 2003–2025. Có thể suy ra tốc độ gió bằng `sqrt(u10² + v10²)` tại cùng tọa độ và thời điểm; đây là biến tính thêm, không có file tốc độ gió riêng trong thư mục.

Các kết quả kiểm tra cấu trúc:

- **14/14 file merged có SHA-256 bằng phép nối các file năm theo thứ tự.** Chọn một nhánh `yearly` hoặc `merged` khi nạp dữ liệu để tránh tính hai lần.
- Mỗi file merged thông thường có **67.208 message**. Riêng `u10_2003_2025_vietnam.grib` có **67.432 message**: 224 message dư, trùng byte hoàn toàn.
- Trùng lặp xuất phát từ `yearly/u10/u10_2016_vietnam.grib`: **3.152 message** so với **2.928 thời điểm duy nhất**. Các mốc bị lặp từ **2016-03-01 00:00 đến 2016-03-28 21:00 UTC**. Không phát hiện message trùng khóa nhưng khác nội dung trong phép kiểm tra này.
- Không phát hiện message sai dấu mở `GRIB`/kết thúc `7777` hoặc lưới thay đổi trong từng file. Chưa giải mã toàn bộ giá trị số của mọi message để kiểm tra miền giá trị hay thiếu dữ liệu toàn chuỗi.

## 3. WAQI — CSV lịch sử chất lượng không khí

### 3.1. Cấu trúc và ý nghĩa trường

Vị trí: [`data/landing/waqi/historical/`](../../data/landing/waqi/historical/). Một dòng tương ứng **một ngày của chuỗi địa điểm được đặt tên trong tên file**. CSV không chứa `station_id`, tên trạm, tọa độ, đơn vị, múi giờ hoặc phương pháp tổng hợp theo ngày.

Header phổ biến có khoảng trắng sau dấu phẩy:

```csv
date, pm25, pm10, o3, no2, so2, co
```

| Trường sau khi trim | Kiểu khi đọc | Ý nghĩa |
|---|---|---|
| `date` | date | Ngày quan trắc dạng `YYYY/M/D`, ví dụ `2025/10/1`; không có giờ/múi giờ |
| `pm25` | integer nullable | Chỉ số cho bụi PM2.5 theo cách diễn giải dữ liệu lịch sử WAQI bên dưới |
| `pm10` | integer nullable | Chỉ số cho bụi PM10 |
| `o3` | integer nullable | Chỉ số cho ozone O₃ |
| `no2` | integer nullable | Chỉ số cho nitrogen dioxide NO₂ |
| `so2` | integer nullable | Chỉ số cho sulphur dioxide SO₂ |
| `co` | integer nullable | Chỉ số cho carbon monoxide CO |
| `aqi` | integer nullable | Cột chỉ số AQI riêng, chỉ xuất hiện trong file UNIS Hanoi; cách hình thành cột này không được ghi trong CSV |

**Về đơn vị:** [WAQI Historical Database](https://aqicn.org/historical/) mô tả các cột chất ô nhiễm của dữ liệu lịch sử là **AQI riêng từng chất theo US EPA**, đã chuyển từ nồng độ. Vì vậy, cách diễn giải phù hợp với nguồn/thư mục/header này là chỉ số AQI không có đơn vị µg/m³. Tuy nhiên, các file cục bộ không có URL xuất hoặc manifest để xác minh từng lượt tải; cần giữ thông tin xuất xứ này là phần chưa đầy đủ. Không gán trực tiếp `pm25` của WAQI cùng đơn vị với `pm2p5` của CAMS.

Chưa xác định từ CSV rằng số liệu ngày là trung bình, trung vị hay cực đại, cũng như ranh giới ngày theo múi giờ nào. Không tự suy ra `aqi` hiện có bằng `max()` các cột ngày: quy tắc tổng hợp theo thời gian và các chất còn thiếu có thể ảnh hưởng kết quả.

### 3.2. Danh mục 17 file và phạm vi thực tế

Cột “ngày không có dòng” là số ngày lịch nằm giữa ngày nhỏ nhất/lớn nhất nhưng không có bản ghi; không phải số ô trống. “Chuẩn” = `date, pm25, pm10, o3, no2, so2, co`.

| Tên file trong `historical/` | Số dòng | Ngày nhỏ nhất | Ngày lớn nhất | Ngày không có dòng | Bộ cột |
|---|---:|---|---|---:|---|
| `bắc-ninh_binh dinh, vietnam-air-quality.csv` | 1.526 | 2020-06-20 | 2025-10-18 | 421 | Chuẩn |
| `bắc-ninh_châu khê, vietnam-air-quality.csv` | 720 | 2020-06-23 | 2025-08-20 | 1.165 | Chuẩn |
| `bắc-ninh_phong cốc, vietnam-air-quality.csv` | 1.192 | 2020-06-21 | 2025-08-21 | 696 | Chuẩn |
| `bắc-ninh_phù lãng, vietnam-air-quality.csv` | 1.196 | 2020-06-20 | 2023-12-30 | 93 | Chuẩn |
| `bắc-ninh_ubnd quế võ, vietnam-air-quality.csv` | 1.341 | 2020-06-20 | 2025-08-21 | 548 | Chuẩn |
| `bắc-ninh_ubnd đại đồng, vietnam-air-quality.csv` | 1.329 | 2020-06-20 | 2025-10-04 | 604 | Chuẩn |
| `da-nang, vietnam-air-quality.csv` | 3.846 | 2014-01-01 | 2026-09-12 | 792 | Chuẩn |
| `hanoi,-vietnam-air-quality.csv` | 3.655 | 2014-01-01 | 2026-09-12 | 983 | Chuẩn |
| `hà-nội_mầm non kim liên, vietnam-air-quality.csv` | 664 | 2020-06-20 | 2023-07-13 | 455 | `date, pm25, pm10, co` |
| `lào-cai_kcn taloong1, vietnam-air-quality.csv` | 960 | 2020-08-22 | 2023-06-16 | 69 | Chuẩn |
| `quảng-ninh_nam cầu trắng, vietnam-air-quality.csv` | 1.485 | 2020-06-20 | 2025-08-21 | 404 | Chuẩn |
| `quảng-ninh_phương nam , vietnam-air-quality.csv` | 172 | 2019-05-27 | 2021-10-31 | 717 | Chuẩn |
| `quảng-ninh_ubnd tp uông bí, vietnam-air-quality.csv` | 1.535 | 2019-05-27 | 2025-08-21 | 744 | Chuẩn |
| `quảng-ninh_yên mỹ, vietnam-air-quality.csv` | 1.377 | 2020-06-20 | 2025-08-21 | 512 | Chuẩn |
| `thừa-thiên huế_83 hùng vương, vietnam-air-quality.csv` | 2.080 | 2019-12-02 | 2026-09-12 | 397 | Chuẩn |
| `united-nations international school of hanoi, vietnam-air-quality.csv` | 3.485 | 2016-01-03 | 2026-09-12 | 421 | Chuẩn + `aqi` |
| `viet-tri, vietnam-air-quality.csv` | 3.162 | 2014-08-02 | 2026-09-12 | 1.263 | Chuẩn |

Tổng cộng **29.725 dòng**, phạm vi chung **2014-01-01 → 2026-09-12**. Không có ngày trùng trong từng file. Không file nào được sắp xếp hoàn toàn theo ngày tăng dần; cần parse và sort trước khi dùng làm chuỗi thời gian. Tên file như `hanoi` hoặc `da-nang` chưa chứng minh chuỗi đó thuộc một trạm vật lý duy nhất.

### 3.3. Ô thiếu và giá trị cần xem lại

Chỉ tính trên những file **có cột tương ứng**, tránh nhầm “không có cột” với “cột có ô trống”:

| Cột | Số file có cột | Số dòng có thể chứa giá trị | Có giá trị | Ô trống |
|---|---:|---:|---:|---:|
| `pm25` | 17 | 29.725 | 22.445 | 7.280 |
| `pm10` | 17 | 29.725 | 21.768 | 7.957 |
| `o3` | 16 | 29.061 | 17.645 | 11.416 |
| `no2` | 16 | 29.061 | 21.035 | 8.026 |
| `so2` | 16 | 29.061 | 19.414 | 9.647 |
| `co` | 17 | 29.725 | 19.628 | 10.097 |
| `aqi` | 1 | 3.485 | 2.413 | 1.072 |

Có **124.348 giá trị** và **55.495 ô trống**, tương đương khoảng **30,86%** trong 179.843 ô chỉ số hiện hữu. Có **187 dòng chỉ có ngày, tất cả chỉ số trống**: Đà Nẵng 10, Hà Nội 41, Phương Nam 11, Uông Bí 31, UNIS 76, Việt Trì 18.

Mọi giá trị không trống parse được thành số nguyên không âm. Tuy nhiên, có các giá trị cần đối chiếu nguồn:

- UNIS: `pm10=999` lặp **16 ngày**, từ **2024-04-06 đến 2024-04-21**. Chưa đủ bằng chứng để kết luận là mã thiếu hay số đo/chỉ số thật.
- Việt Trì: `pm25=828` vào **2018-05-07**. Giữ giá trị gốc và gắn cờ kiểm tra; không tự cắt về 500 hoặc thay bằng NULL.

Khi đọc, trim tên cột/giá trị, chuyển ô rỗng hoặc chỉ chứa khoảng trắng thành NULL. Không thay ô thiếu bằng 0. Khóa tạm cho dữ liệu rộng là `(tên file, date)`; sau chuyển dạng dài là `(tên file, date, tên chỉ số)`.

## 4. Climate TRACE — phát thải

Thư mục gốc: [`data/landing/climate_trace/climate_trace_vietnam/`](../../data/landing/climate_trace/climate_trace_vietnam/).

### 4.1. Ba file và mức độ chi tiết

| Đường dẫn tương đối từ thư mục trên | Số dòng | Số cột | Mức độ chi tiết |
|---|---:|---:|---|
| `annual_2015_2020/vietnam_all_gases_2015_2020.csv` | 1.440 | 8 | Quốc gia × năm × chất × cấp tổng hợp × ngành/phân ngành, 2015–2020 |
| `monthly_2021_2026_06/vietnam_all_gases_2021_2026_06.csv` | 15.840 | 10 | Cùng các chiều trên, theo **66 tháng**, 2021-01–2026-06 |
| `monthly_2021_2026_06/vietnam_all_gases_sources_2026.csv` | 44.538 | 11 | Nguồn phát thải × nhãn năm 2026 × chất; tên cột giá trị là `annual_emissions_quantity` |

Cả ba file chỉ chứa `country=VNM` và **3 chất**: `co2`, `pm2_5`, `so2`. Tên `all_gases` không có nghĩa các file hiện tại chứa toàn bộ chất mà nhà cung cấp hỗ trợ; `pm2_5` là bụi, dù được đặt dưới trường `gas`.

### 4.2. Trường của hai file tổng hợp quốc gia

| Trường | Có trong | Kiểu khi đọc | Ý nghĩa và ví dụ |
|---|---|---|---|
| `country` | Năm, tháng | string | Mã quốc gia, ở đây luôn `VNM` |
| `country_name` | Năm, tháng | string | Tên hiển thị, ở đây `Vietnam` |
| `aggregation` | Năm, tháng | enum/string | Cấp tổng hợp: `totals`, `sectors`, `subsectors` |
| `year` | Năm, tháng | integer | Năm của kỳ phát thải; không phải năm tải file |
| `data_month` | Tháng | string `YYYY-MM` / tháng | Kỳ tháng, ví dụ `2021-01` |
| `month` | Tháng | integer | Số tháng 1–12; khớp với `data_month` trong mọi dòng đã kiểm tra |
| `gas` | Năm, tháng | enum/string | `co2`: CO₂; `pm2_5`: bụi PM2.5; `so2`: SO₂ |
| `sector` | Năm, tháng | string nullable | Ngành phát thải; để trống ở dòng tổng quốc gia |
| `subsector` | Năm, tháng | string nullable | Phân ngành; chỉ có giá trị ở cấp `subsectors` |
| `emissionsQuantity` | Năm, tháng | số thực | Lượng phát thải trong kỳ năm hoặc tháng; đọc cùng `gas` và `aggregation` |

Thứ tự header thực tế:

```text
Năm:   country,country_name,aggregation,year,gas,sector,subsector,emissionsQuantity
Tháng: country,country_name,aggregation,data_month,year,month,gas,emissionsQuantity,sector,subsector
```

**Đơn vị:** [hướng dẫn schema Climate TRACE](https://media.climatetrace.org/about_the_data_latest_b6e7b8d419.pdf) quy định lượng phát thải theo **tấn mét của chất tương ứng**. Đây là cơ sở diễn giải cho các cột giá trị đã xuất; CSV cục bộ không có cột đơn vị hoặc mã/script xuất để xác nhận có biến đổi trước khi lưu hay không. Không mặc định `co2` là CO₂ tương đương (`co2e`), không diễn giải phát thải theo kỳ thành nồng độ không khí.

Ví dụ thực tế: dòng `VNM, Vietnam, totals, 2021-01, 2021, 1, co2` có `emissionsQuantity=32128773.22265221`; đó là giá trị tổng CO₂ của kỳ tháng theo cách tổ chức file.

Quy tắc cấp tổng hợp được xác nhận từ dữ liệu:

| `aggregation` | `sector` | `subsector` | Số dòng file năm | Số dòng file tháng |
|---|---|---|---:|---:|
| `totals` | Trống | Trống | 18 | 198 |
| `sectors` | Có | Trống | 180 | 1.980 |
| `subsectors` | Có | Có | 1.242 | 13.662 |

Không cộng gộp cả ba cấp với nhau vì chúng biểu diễn các mức tổng hợp chồng lấp. Khoảng trống ở `sector`/`subsector` theo bảng là **có chủ đích**, không phải lỗi thiếu dữ liệu.

Hai file tổng hợp có **10 ngành** và **69 phân ngành khác nhau** không kể giá trị trống. Ý nghĩa các mã ngành:

| Mã ngành | Ý nghĩa |
|---|---|
| `agriculture` | Nông nghiệp |
| `buildings` | Công trình/tòa nhà |
| `fluorinated-gases` | Nhóm khí chứa fluor |
| `forestry-and-land-use` | Lâm nghiệp và sử dụng đất |
| `fossil-fuel-operations` | Hoạt động nhiên liệu hóa thạch |
| `manufacturing` | Sản xuất công nghiệp |
| `mineral-extraction` | Khai thác khoáng sản |
| `power` | Năng lượng điện |
| `transportation` | Giao thông vận tải |
| `waste` | Chất thải |

`subsector` chi tiết hơn, ví dụ `electricity-generation` = phát điện, `road-transportation` = giao thông đường bộ, `rice-cultivation` = trồng lúa, `cement` = xi măng, `removals` = loại bỏ/hấp thụ carbon. Danh mục phân ngành là giá trị phân loại trong một cột, không phải các cột riêng.

Khóa ứng viên đã kiểm tra không bị trùng:

```text
Năm:   (country, aggregation, year, gas, sector, subsector)
Tháng: (country, aggregation, data_month, gas, sector, subsector)
```

Không có giá trị phát thải trống hoặc số không hữu hạn trong cả hai file. File năm có **541 giá trị 0 và 19 giá trị âm**; file tháng có **5.850 giá trị 0 và 147 giá trị âm**. Các giá trị âm thuộc CO₂, xuất hiện ở các phân ngành `removals`, `net-forest-land`, `net-shrubgrass`, `net-wetland` và cấp ngành liên quan. Dấu âm phù hợp với cách biểu diễn hấp thụ/cân bằng ròng, nhưng không phải một kiểm chứng khoa học độc lập; không áp dụng quy tắc “mọi phát thải phải ≥ 0” để tự xóa chúng.

### 4.3. Trường của file theo nguồn năm 2026

| Trường | Kiểu khi đọc | Ý nghĩa và giá trị quan sát |
|---|---|---|
| `source_id` | string | Mã nguồn phát thải, ví dụ `25454003`; không phải số thứ tự dòng |
| `country` | string | `VNM` |
| `year` | integer | Tất cả dòng mang nhãn `2026` |
| `gas` | string | `co2`, `pm2_5`, `so2` |
| `latitude` | số thực | Vĩ độ nguồn/điểm đại diện, đơn vị độ |
| `longitude` | số thực | Kinh độ nguồn/điểm đại diện, đơn vị độ |
| `sector` | string | Ngành của nguồn; có 9 ngành trong file này |
| `subsector` | string | Phân ngành của nguồn |
| `asset_type` | string nullable | Loại tài sản/công nghệ/hoạt động; ví dụ `coal`, `gas`, hoặc mô tả quy trình sản xuất. Có cả dấu phẩy và dấu `\|` trong giá trị; phải dùng CSV parser |
| `source_type` | enum/string | `point-source`: nguồn điểm; `gadm-aggregation`: nguồn được tổng hợp theo vùng hành chính GADM |
| `annual_emissions_quantity` | số thực | Lượng phát thải gắn nhãn năm/chất của nguồn; đơn vị diễn giải theo hướng dẫn Climate TRACE ở trên |

Theo [hướng dẫn Climate TRACE](https://media.climatetrace.org/about_the_data_latest_b6e7b8d419.pdf), tọa độ nguồn tổng hợp có thể là tâm của hình học vùng. Vì vậy, điểm của `gadm-aggregation` không được coi là vị trí một nhà máy cụ thể.

File nằm trong thư mục tên `monthly_2021_2026_06` nhưng **không có cột tháng**, chỉ có `year=2026` và `annual_emissions_quantity`. Chưa đủ metadata để kết luận giá trị là cả năm hoàn chỉnh, lũy kế đến tháng 6 hay một ước tính năm. Cần đối chiếu truy vấn/script xuất trước khi so sánh trực tiếp với tổng 6 tháng của file quốc gia.

Kiểm tra trực tiếp:

- **44.538 dòng**, **14.886 `source_id`** khác nhau. Mã nguồn lặp qua các chất là điều có thể dự kiến; khóa cần xét là `(source_id, year, gas)`.
- Có **12.154 dòng dư trùng hoàn toàn**, khoảng **27,29%** số dòng. Sau loại trùng còn **32.384 bản ghi**; không có nhóm cùng khóa nhưng giá trị khác nhau trong lần kiểm tra này.
- Có **1.087 nguồn `point-source`** và **13.799 nguồn `gadm-aggregation`**, tương ứng 3.261 và 41.277 dòng trước loại trùng.
- `asset_type` trống **41.679/44.538 dòng**; các cột khác không trống. Không suy đoán loại tài sản từ ô thiếu.
- Không thấy cùng `source_id` nhưng mâu thuẫn các thuộc tính quốc gia, tọa độ, ngành, phân ngành, loại nguồn và loại tài sản.
- Vĩ độ từ `8.6769` đến `23.24212646550012`; kinh độ từ `102.37578736269165` đến `109.406281`. Không có tọa độ ngoài miền hợp lệ toàn cầu; điều này không thay thế phép kiểm tra ranh giới Việt Nam.
- Không có `source_name`, mã hành chính, polygon hay cột kỳ bắt đầu/kết thúc. Không thể nối trực tiếp nguồn với xã/phường bằng một mã có sẵn.

## 5. Dữ liệu tham chiếu hành chính Việt Nam

Thư mục: [`data/landing/reference/vietnam_administrative_divisions/`](../../data/landing/reference/vietnam_administrative_divisions/). Metadata đi kèm ghi snapshot **2026-09-08**. Những mô tả về cấp hành chính dưới đây nói về **snapshot này**, không khẳng định đó là cấu trúc áp dụng cho mọi năm của dữ liệu khí tượng/phát thải.

### 5.1. Vai trò và cấu trúc từng file

| File | Cấu trúc gốc | Nội dung thực tế |
|---|---|---|
| `all-province.json` | Array các object | 34 tỉnh/thành, `level=1`; bản ghi đầy đủ |
| `all-ward.json` | Array các object | 3.321 xã/phường, `level=2`; bản ghi đầy đủ |
| `all-flat.json` | Object `{_attribution, data}` | `data` là array **34 tỉnh/thành**, bằng nội dung `all-province.json`; không bao gồm toàn bộ xã/phường |
| `all-flat.ndjson` | Một object JSON trên mỗi dòng | 34 dòng; bằng danh sách `all-flat.json.data` |
| `all-flat.csv` | Chú thích ở dòng đầu, sau đó header và dữ liệu | 34 dòng tỉnh/thành, 18 cột phẳng |
| `hierarchy.json` | Object `{_attribution, data}` | 34 object tỉnh/thành; mỗi object có array `ward`, tổng cộng 3.321 xã/phường |
| `schema.json` | JSON Schema | Quy tắc cấu trúc cho một bản ghi; không phải bảng quan trắc |

`all-flat.json` và `hierarchy.json` có `_attribution` để ghi nguồn/giấy phép; `data` mới là danh sách bản ghi. `all-province.json` và `all-ward.json` không có lớp bọc `data`. Không dùng chung một cách truy cập JSON cho cả bốn file.

### 5.2. Các trường của bản ghi đầy đủ

Ví dụ tỉnh: `id="01"`, `name.local="Hà Nội"`, `geo={"lat":"21","lon":"105.698"}`. Ví dụ phường: `id="00004"`, `name.local="Ba Đình"`, `parent.id="01"`.

| Đường dẫn trường | Kiểu JSON | Ý nghĩa / giá trị thực tế |
|---|---|---|
| `id` | string | Mã đơn vị hành chính; giữ số 0 đầu, ví dụ `01`, `00004` |
| `level` | integer | `1`: tỉnh/thành; `2`: xã/phường trong snapshot này |
| `level_name.local` | string | Nhãn cấp tiếng Việt: `Tỉnh/Thành phố`, `Xã/Phường` |
| `level_name.en` | string | Nhãn cấp tiếng Anh: `Province/City`, `Commune/Ward` |
| `name.local` | string | Tên tiếng Việt |
| `name.en` | string | Tên tiếng Anh/không dấu do nguồn cung cấp |
| `name.slug` | string | Chuỗi định danh thân thiện URL, ví dụ `ha-noi-01` |
| `code.id` | string | Mã hành chính trong object `code`; trùng `id` ở dữ liệu đang có |
| `code.iso` | string hoặc null | Chỗ dành cho mã ISO; hiện null trong toàn bộ 3.355 bản ghi đầy đủ |
| `parent` | object hoặc null | Đơn vị cha; null ở tỉnh/thành, object tham chiếu tỉnh ở xã/phường |
| `parent.id` | string | Mã tỉnh/thành cha |
| `parent.level` | integer | Cấp của đơn vị cha, bằng 1 ở xã/phường |
| `parent.name.local`, `parent.name.en`, `parent.name.slug` | string | Tên và slug của đơn vị cha |
| `ancestors` | array | Chuỗi đơn vị tổ tiên; `[]` ở tỉnh, một tham chiếu tỉnh ở xã/phường |
| `ancestors[].id`, `ancestors[].level`, `ancestors[].name.*` | string / integer / object | Cùng cấu trúc tham chiếu như `parent` |
| `children_count` | object | Số đơn vị con theo cấp; xã/phường hiện là `{}` |
| `children_count.ward` | integer | Số xã/phường trực thuộc tỉnh, ví dụ Hà Nội `126` |
| `zip_codes` | array string | Danh sách mã bưu chính nếu có; hiện mọi bản ghi là `[]` |
| `geo.lat` | **string** hoặc null theo schema | Vĩ độ, ví dụ `"21"`; cần parse thành số nếu tính toán |
| `geo.lon` | **string** hoặc null theo schema | Kinh độ, ví dụ `"105.698"`; cần parse thành số nếu tính toán |
| `metadata` | object | Metadata mở rộng; hiện `{}` ở toàn bộ bản ghi |
| `source` | object | Thông tin nguồn từng bản ghi; có dữ liệu ở tỉnh, `{}` ở toàn bộ xã/phường |
| `source.name` | string | Tên nhà cung cấp, `Open Admin Data` |
| `source.url` | string | Trang nguồn tương ứng tỉnh/thành |
| `source.api` | string | URL API do nguồn ghi kèm |

Theo [README được lưu cùng dữ liệu](../../data/landing/reference/vietnam_administrative_divisions/metadata/README.md), tọa độ dùng WGS84. File chỉ chứa tọa độ đại diện, **không có polygon ranh giới**; không dùng tọa độ này để xác định chính xác một trạm thuộc xã/phường nào.

### 5.3. Các cột của `all-flat.csv`

Phải bỏ dòng đầu bắt đầu bằng `# Data from Open Admin Data ...` trước khi đọc header. CSV này làm phẳng một phần trường JSON:

| Cột CSV | Kiểu khi đọc | Ý nghĩa / ánh xạ |
|---|---|---|
| `id` | string | Mã đơn vị, như JSON `id` |
| `level` | integer | Cấp hành chính; tất cả bằng 1 |
| `level_name.local` | string | Tên cấp tiếng Việt |
| `level_name.en` | string | Tên cấp tiếng Anh |
| `name.local` | string | Tên đơn vị tiếng Việt |
| `name.en` | string | Tên đơn vị tiếng Anh/không dấu |
| `name.slug` | string | Slug đơn vị |
| `code.id` | string | Mã hành chính |
| `code.iso` | string nullable | Mã ISO; cả 34 dòng trống |
| `parent.id` | string nullable | Mã cha; cả 34 dòng trống vì đây là cấp tỉnh |
| `parent.name.local` | string nullable | Tên cha tiếng Việt; trống |
| `parent.name.en` | string nullable | Tên cha tiếng Anh; trống |
| `children_count.province` | integer nullable | Số đơn vị con cấp tỉnh trong định dạng phẳng; cả 34 dòng trống |
| `children_count.ward` | integer | Số xã/phường trực thuộc |
| `zip_codes` | string nullable | Biểu diễn phẳng mã bưu chính; tất cả trống, chưa có mẫu để suy ra cách phân tách nhiều mã |
| `geo.lat` | số thực | Vĩ độ đại diện |
| `geo.lon` | số thực | Kinh độ đại diện |
| `source_url` | string | Tương ứng JSON `source.url` |

CSV không giữ đầy đủ các trường như `ancestors`, `metadata`, `source.api`. Dùng JSON đầy đủ nếu cần các trường này.

### 5.4. `hierarchy.json` và `schema.json`

`hierarchy.json` là cách biểu diễn cây rút gọn:

```text
_attribution                   Chuỗi ghi nguồn
data[]                         Danh sách tỉnh/thành
  id                           Mã tỉnh/thành
  name.{local,en,slug}          Tên tỉnh/thành
  code.{id,iso}                 Mã tỉnh/thành
  ward[]                       Danh sách xã/phường trực thuộc
    id                         Mã xã/phường
    name.{local,en,slug}        Tên xã/phường
    code.{id,iso}               Mã xã/phường
```

Quan hệ cha–con được thể hiện qua vị trí lồng nhau. Các node rút gọn không có `geo`, `parent`, `level` hoặc toàn bộ metadata của bản ghi đầy đủ.

`schema.json` có các trường cấu hình:

| Trường schema | Ý nghĩa |
|---|---|
| `$schema` | Phiên bản JSON Schema, draft 2020-12 |
| `title` | Tên schema: `Vietnam Administrative Division Record` |
| `type` | Kiểu gốc phải là `object` |
| `required` | Ba trường bắt buộc: `id`, `level`, `name` |
| `properties` | Định nghĩa kiểu/cấu trúc của từng trường bản ghi |

Trong `properties`, `level` có enum `[1, 2]`; `name` yêu cầu `local` và `en`; `geo.lat/lon` cho phép string hoặc null. Schema chưa khai báo `metadata` và `source` dù chúng có trong dữ liệu; đồng thời không cấm thuộc tính bổ sung. Do đó không xem danh sách `properties` là toàn bộ trường thực tế. Chưa chạy bộ xác thực JSON Schema đầy đủ; các kiểm tra trực tiếp nằm ở mục 5.6.

### 5.5. Các file metadata

`metadata/source.json` mô tả xuất xứ của snapshot, khác với object `source` trong từng bản ghi:

| Trường | Kiểu | Giá trị / ý nghĩa |
|---|---|---|
| `source_name` | string | `vietnam-administrative-divisions`: tên bộ dữ liệu |
| `source_url` | string URL | Repository Open Admin Data được ghi trong file |
| `snapshot_date` | string date | `2026-09-08`: ngày snapshot do metadata khai báo |
| `git_commit` | string | Hiện là `...`, chưa xác định commit nguồn |
| `retrieved_at` | string | Hiện là `...`, chưa xác định thời điểm tải |
| `ingestion_status` | string | `downloaded`: trạng thái ghi nhận đã tải |

`metadata/CITATION.cff` dùng cấu trúc YAML để cung cấp thông tin trích dẫn, không phải dữ liệu quan trắc:

| Trường | Ý nghĩa |
|---|---|
| `cff-version` | Phiên bản chuẩn CFF, `1.2.0` |
| `message` | Hướng dẫn trích dẫn |
| `type` | Loại tài nguyên, `dataset` |
| `authors[].name` | Tên tác giả/người đóng góp được khai báo |
| `title` | Tên bộ dữ liệu |
| `version` | Phiên bản dataset, `2026.09` |
| `date-released` | Ngày phát hành được khai báo, `2026-09-08` |
| `url`, `repository-code` | Liên kết dự án/repository |
| `license` | Mã giấy phép được khai báo, `CC-BY-4.0` |
| `keywords` | Danh sách từ khóa |
| `abstract` | Mô tả ngắn bộ dữ liệu |

`metadata/README.md` giải thích cấu trúc, cách đọc, nguồn và giấy phép; `metadata/LICENSE` chứa nội dung giấy phép. Hai file này không có hàng/cột quan trắc. Một số liên kết trong README thuộc cấu trúc repository nguồn, không đồng nghĩa các thư mục liên quan đã được tải vào `data/`.

### 5.6. Kiểm tra tính nhất quán

- Có đúng **34 tỉnh/thành và 3.321 xã/phường**, không trùng `id` trong từng danh mục.
- Mọi `parent.id` của xã/phường đều tìm được trong danh mục tỉnh; không có bản ghi mồ côi.
- `children_count.ward` của từng tỉnh khớp số xã/phường tham chiếu đến tỉnh đó.
- Mọi bản ghi đầy đủ có tọa độ không rỗng; đây là kiểm tra có dữ liệu, chưa xác nhận độ chính xác địa lý của từng điểm.
- `all-flat.json.data` bằng `all-province.json`; NDJSON biểu diễn cùng 34 bản ghi. Danh sách mã xã/phường trong cây `hierarchy` khớp `all-ward.json`.
- Không union các biểu diễn `all-flat.*`, `hierarchy`, `all-province`, `all-ward` như các nguồn quan sát độc lập vì sẽ tạo trùng lặp.
- Metadata snapshot chưa đủ truy vết do `git_commit` và `retrieved_at` còn `...`. Dữ liệu hành chính này không có lịch sử hiệu lực để tự ánh xạ tên địa phương cũ trong dữ liệu 2003–2025.

## 6. Những khác biệt cần giữ khi kết hợp các nguồn

| Nội dung | CAMS | WAQI | Climate TRACE | Hành chính |
|---|---|---|---|---|
| Một giá trị đại diện cho | Biến × thời điểm × điểm lưới | Chỉ số × ngày × chuỗi địa điểm | Chất × kỳ × quốc gia/ngành hoặc nguồn | Một đơn vị hành chính trong snapshot |
| Thời gian | Mỗi 3 giờ, UTC | Ngày, chưa rõ múi giờ/thống kê | Năm hoặc tháng; nguồn 2026 thiếu định nghĩa kỳ chi tiết | Snapshot 2026-09-08 |
| Không gian | Lưới 0,75° | Chỉ có nhãn địa điểm trong tên file | Quốc gia hoặc tọa độ nguồn/điểm đại diện vùng | Tọa độ đại diện và quan hệ cha–con |
| Ý nghĩa số PM2.5 | Nồng độ kg/m³ | Diễn giải là AQI theo tài liệu nguồn | Khối lượng phát thải trong kỳ, diễn giải là tấn | Không có đại lượng PM2.5 |
| Cách thiếu dữ liệu | Cần đọc bitmap/metadata khi giải mã | Ô trống; có file không có cột; có ngày không có dòng | Một số trường phân loại trống có chủ đích | null, array/object rỗng hoặc cột phẳng trống |

Các điểm cần xử lý trước khi tính toán:

| Phát hiện đã xác nhận | Ảnh hưởng | Cách xử lý đề xuất |
|---|---|---|
| CAMS có bản theo năm và bản merged giống nhau | Nạp cả hai nhánh làm tăng gấp đôi dữ liệu | Chọn một nhánh làm đầu vào |
| CAMS `u10` có 224 message dư | Làm lệch trọng số thời gian nếu tính trung bình trực tiếp | Loại bản trùng byte theo khóa biến/lưới/thời gian/level/step, giữ dấu vết file nguồn |
| Climate TRACE sources có 12.154 dòng dư | Tổng phát thải bị cộng trùng | Loại trùng hoàn toàn; dùng `(source_id, year, gas)` để kiểm tra |
| WAQI thiếu nhiều ô/ngày và có giá trị 999/828 | Chuỗi thời gian gián đoạn, có điểm cần kiểm tra | Giữ NULL, sort theo ngày, gắn cờ đối chiếu giá trị nghi vấn |
| Đơn vị/định nghĩa kỳ của CSV chưa nằm trong file | Dễ so sánh sai đại lượng hoặc sai kỳ | Bổ sung manifest xuất, đơn vị và quy tắc tổng hợp từ nguồn |
| WAQI không có tọa độ; hành chính không có polygon | Chưa đủ cơ sở nối không gian chính xác | Bổ sung metadata trạm và ranh giới nếu cần ghép địa lý |

## 7. Phương pháp kiểm tra và đọc lại

Phạm vi đã thực hiện:

1. Liệt kê mọi file và thư mục rỗng trong `data/`; không sửa dữ liệu nguồn.
2. Đọc toàn bộ 21 CSV bằng CSV parser, hỗ trợ UTF-8 BOM, trim khoảng trắng và bỏ dòng chú thích của CSV hành chính. Kiểm tra header, số dòng, ô trống, thời gian, giá trị số và các khóa nêu trong tài liệu.
3. Parse 6 JSON và toàn bộ 34 dòng NDJSON; kiểm tra cấu trúc, danh mục, quan hệ cha–con và các biểu diễn trùng nhau. Đọc README, LICENSE và CFF đi kèm.
4. Dùng [script kiểm kê sẵn có](../../scripts/profile_landing.py) quét header mọi message của 336 GRIB, giải mã metadata đầu/cuối mỗi file bằng ecCodes, kiểm tra trùng và SHA-256 của merged so với phép nối yearly.
5. Bổ sung kiểm tra tập timestamp của 14 merged trên lịch 3 giờ, giải mã 242 giá trị của message đầu mỗi merged để đọc mẫu và metadata đóng gói. **Không thực hiện kiểm định khoa học hoặc quét toàn bộ giá trị số GRIB.**

Có thể chạy lại phần kiểm kê chính sau khi môi trường Python có ecCodes:

```powershell
python scripts/profile_landing.py --output "$env:TEMP\tlcn-landing-profile.json"
```

Script trên kiểm kê 20 CSV nguồn, các GRIB và một phần danh mục hành chính. Nó chưa bao gồm toàn bộ kiểm tra bổ sung trong tài liệu này, như CSV hành chính, lịch 3 giờ, giá trị WAQI lớn hơn 500 hoặc tính nhất quán giữa các biểu diễn JSON.

Ví dụ đọc CSV đúng header và giữ mã dạng chuỗi bằng thư viện chuẩn:

```python
import csv
from pathlib import Path

path = Path("data/landing/reference/vietnam_administrative_divisions/all-flat.csv")
with path.open(encoding="utf-8-sig", newline="") as stream:
    reader = csv.DictReader(
        (line for line in stream if not line.startswith("#")),
        skipinitialspace=True,
    )
    rows = [
        {key.strip(): value.strip() or None for key, value in row.items()}
        for row in reader
    ]
# rows[0]["id"] vẫn là "01"; chỉ ép kiểu những cột đã biết ý nghĩa.
```

Mọi số lượng và phạm vi nêu trên là kết quả của snapshot cục bộ tại ngày kiểm tra, không phải cam kết rằng dữ liệu nguồn trực tuyến hoặc các lần tải tiếp theo giữ nguyên cấu trúc.
