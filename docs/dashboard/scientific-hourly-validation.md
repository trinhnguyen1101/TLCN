# Phương pháp và kết quả kiểm chứng dashboard

> Cập nhật phân cấp: dashboard hiện dùng 34 tỉnh/thành; Hoàng Sa thuộc Đà Nẵng,
> Trường Sa thuộc Khánh Hòa. Các con số **36 vùng** bên dưới thuộc lần kiểm chứng
> generation cũ, không phải số tỉnh hành chính. Xem [phân cấp và chuyển dữ liệu](data-processing.md#phân-cấp-hành-chính-34-tỉnhthành).
> [Biên bản kiểm chứng 34 tỉnh/thành](../../reports/dashboard/province-hierarchy.md)
> có kết quả API, GRIB và trình duyệt sau thay đổi này.

[← Tài liệu dashboard](README.md) · [Chạy web FE–BE](run-dashboard.md) · [Tạo Parquet](data-processing.md)

Trang này giải thích ý nghĩa số liệu và tóm tắt **lần kiểm chứng ngày 30/10/2026**.
Các kết quả bên dưới là biên bản tại thời điểm đó, không tự cập nhật khi code hay
dữ liệu thay đổi. Muốn chạy lại kiểm chứng, dùng [hướng dẫn xử lý dữ liệu](data-processing.md#5-kiểm-thử-cho-người-phát-triển).
Bản gốc chi tiết bằng tiếng Anh được giữ trong [kho lưu trữ](archive/scientific-hourly-validation-2026-10-30.md).

## 1. Cần hiểu gì trước khi đọc dashboard?

- Đây là ước tính mô hình CAMS EAC4 theo vùng báo cáo, không phải số đo trạm.
- Phân tích gốc có bước ba giờ; dữ liệu hiển thị một giờ là kết quả nội suy.
  Nhiều slot hơn không có nghĩa là có thêm quan sát vật lý độc lập.
- CO dùng mg/m³. PM1, PM2.5, PM10, NO₂, SO₂ và O₃ dùng µg/m³.
- Khí tổng cột dùng mg/m², tách riêng khỏi nồng độ gần mặt đất. AOD không có đơn vị khối lượng.
- AQI giữ NULL vì không có giá trị hợp lệ do nguồn cung cấp cho pipeline này.

## 2. Đã kiểm tra những tệp nào?

Kiểm kê toàn bộ message trong 20 tệp bằng ecCodes cho kết quả:

| Thuộc tính | Kết quả |
| --- | --- |
| Kỳ thực tế | 01/01/2003 00:00 → 31/12/2025 21:00 UTC |
| Số mốc giờ mỗi biến | 201.622 |
| Timestamp trùng / giờ thiếu ở giữa kỳ | 0 / 0 |
| Giá trị ô lưới thiếu | 0 ở cả 20 tệp |
| Lưới | 23 × 25 tâm ô; bước 0,75°; 6–24° B, 102–118,5° Đ |
| Khí, T_model, q_model | Hybrid level 60, có 122 hệ số PV |
| Sản phẩm trong metadata đã kiểm tra | `class=mc`, `expver=eac4`, `stream=oper`, phân tích tức thời |

Không tạo thêm hai giờ 22:00 và 23:00 sau thời điểm kết thúc nguồn.
Tệp PM2.5 thực tế tên `pm2p5...`; ETL nhận diện bằng `paramId=210073`, không dựa vào tên tệp.

| Tệp thực tế | paramId | Đơn vị nguồn | Tầng | Nhóm | Đơn vị hiển thị / hỗ trợ | Chuyển đổi | Kết quả |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `aod550_2003_2025_vietnam.grib` | 210207 | `~` | surface 0 | AOD nâng cao | 1 | Giữ nguyên | Đã kiểm tra |
| `co_2003_2025_vietnam.grib` | 210123 | `kg kg**-1` | hybrid 60 | Khí tầng mô hình gần mặt đất | mg/m³ | MMR × mật độ khí ẩm × 10⁶ | Đã kiểm tra |
| `co_column_2003_2025_vietnam.grib` | 210127 | `kg m**-2` | surface 0 | Tổng cột nâng cao | mg/m² | ×10⁶; không phải nồng độ bề mặt | Đã kiểm tra |
| `d2m_2003_2025_vietnam.grib` | 168 | `K` | surface 0 | Khí tượng | °C | K − 273.15 | Đã kiểm tra |
| `mslp_2003_2025_vietnam.grib` | 151 | `Pa` | surface 0 | Khí tượng | hPa | ×0.01; không dùng làm áp suất tầng | Đã kiểm tra |
| `no2_2003_2025_vietnam.grib` | 210121 | `kg kg**-1` | hybrid 60 | Khí tầng mô hình gần mặt đất | µg/m³ | MMR × mật độ khí ẩm × 10⁹ | Đã kiểm tra |
| `no2_column_2003_2025_vietnam.grib` | 210125 | `kg m**-2` | surface 0 | Tổng cột nâng cao | mg/m² | ×10⁶; không phải nồng độ bề mặt | Đã kiểm tra |
| `o3_2003_2025_vietnam.grib` | 210203 | `kg kg**-1` | hybrid 60 | Khí tầng mô hình gần mặt đất | µg/m³ | MMR × mật độ khí ẩm × 10⁹ | Đã kiểm tra |
| `o3_column_2003_2025_vietnam.grib` | 210206 | `kg m**-2` | surface 0 | Tổng cột nâng cao | mg/m² | ×10⁶; không phải nồng độ bề mặt | Đã kiểm tra |
| `pm10_2003_2025_vietnam.grib` | 210074 | `kg m**-3` | surface 0 | PM bề mặt | µg/m³ | ×10⁹; không nhân mật độ | Đã kiểm tra |
| `pm1_2003_2025_vietnam.grib` | 210072 | `kg m**-3` | surface 0 | PM bề mặt | µg/m³ | ×10⁹; không nhân mật độ | Đã kiểm tra |
| `pm2p5_2003_2025_vietnam.grib` | 210073 | `kg m**-3` | surface 0 | PM bề mặt | µg/m³ | ×10⁹; không nhân mật độ | Đã kiểm tra |
| `q_model_2003_2025_vietnam.grib` | 133 | `kg kg**-1` | hybrid 60 | Đầu vào mật độ | kg/kg | Giữ độ ẩm riêng | Đã kiểm tra |
| `so2_2003_2025_vietnam.grib` | 210122 | `kg kg**-1` | hybrid 60 | Khí tầng mô hình gần mặt đất | µg/m³ | MMR × mật độ khí ẩm × 10⁹ | Đã kiểm tra |
| `so2_column_2003_2025_vietnam.grib` | 210126 | `kg m**-2` | surface 0 | Tổng cột nâng cao | mg/m² | ×10⁶; không phải nồng độ bề mặt | Đã kiểm tra |
| `sp_2003_2025_vietnam.grib` | 134 | `Pa` | surface 0 | Khí tượng / mật độ | hPa / raw Pa | ×0.01 hiển thị; Pa gốc cho áp suất tầng | Đã kiểm tra |
| `t2m_2003_2025_vietnam.grib` | 167 | `K` | surface 0 | Khí tượng | °C | K − 273.15 | Đã kiểm tra |
| `t_model_2003_2025_vietnam.grib` | 130 | `K` | hybrid 60 | Đầu vào mật độ | K | Giữ T tầng mô hình | Đã kiểm tra |
| `u10_2003_2025_vietnam.grib` | 165 | `m s**-1` | surface 0 | Khí tượng | m/s | Giữ nguyên dấu | Đã kiểm tra |
| `v10_2003_2025_vietnam.grib` | 166 | `m s**-1` | surface 0 | Khí tượng | m/s | Giữ nguyên dấu | Đã kiểm tra |

T_model và q_model là hai đầu vào nội bộ cho mật độ; 18 biến còn lại trở thành
chỉ số phục vụ API. Không có tệp CO₂ và không có phép suy CO₂ từ CO.
Tên, edition, geometry, thời gian, PV, hash và giá trị cực trị đầy đủ nằm trong
[grib-inventory.json](../../reports/dashboard/science/grib-inventory.json).

### Các khác biệt đã được giải quyết

- GRIB1 của các trường bề mặt và GRIB2 của các trường model-level có hash section
  khác nhau, nhưng tọa độ lat/lon theo đúng thứ tự khớp hoàn toàn. Không cần regrid.
- Giai đoạn 2013–2016 có cách mã hóa PV khác: chênh tối đa 0,001953125 Pa ở A và
  2,9802322387695312e−8 ở B. Hai biên của tầng 60 giống hệt nhau giữa hai cách mã hóa.
  Khí/T/q phải dùng PV khớp tại cùng timestamp; cấu hình ERA5 L137 bị từ chối.
- Mẫu kiểm tra ở cả 20 biến giữ nguyên byte của các trường gốc 00:00/03:00.
  Trường 01:00 khớp PCHIP cho chất ô nhiễm hoặc nội suy tuyến tính cho khí tượng
  trong sai số đóng gói GRIB. Xem [bằng chứng nội suy](../../reports/dashboard/interpolation-provenance.json).

## 3. Khí được đổi đơn vị như thế nào?

### Áp suất đúng tầng

PV chứa A[0…60] rồi B[0…60]. Với tầng đầy đủ k, dùng hai biên k−1 và k:

```text
p_trên = A[k−1] + B[k−1] × sp
p_dưới = A[k]   + B[k]   × sp
p_model = (p_trên + p_dưới) / 2
```

A có đơn vị Pa; B không thứ nguyên. Hệ số lấy trực tiếp từ GRIB và đối chiếu với
[bảng L60 của ECMWF](https://confluence.ecmwf.int/spaces/UDOC/pages/108117131/L60+model+level+definitions).
Quy ước trung điểm tầng được mô tả trong
[tài liệu model level](https://confluence.ecmwf.int/plugins/viewsource/viewpagesrc.action?pageId=85405371).

Tại tầng 60: A59=A60=0, B59=0,9976301193237305 và B60=1.
Ví dụ sp=101325 Pa cho p_model=101204,9359202385 Pa; không được thay p_model bằng sp.
Cũng không dùng MSLP làm áp suất tầng, hoặc T2M thay nhiệt độ tầng mô hình.

### Mật độ khí ẩm và cơ sở khối lượng

Với T_model tính bằng Kelvin và q là độ ẩm riêng kg/kg:

```text
R_mix = (1−q) × 287.05 + q × 461.5
rho_moist = p_model / (R_mix × T_model)
```

Các trường khí IFS được lưu dưới dạng specific ratio so với khối lượng không
khí tổng/ẩm; pipeline chọn cơ sở này và ghi `mmrMassBasis=moist_air`.
[Tài liệu ECMWF 849, mục 2.6](https://www.ecmwf.int/sites/default/files/elibrary/2019/19114-dry-mass-versus-total-mass-conservation-ifs.pdf)
phân biệt định nghĩa lưu trữ với hành vi vận chuyển gần mixing ratio khí khô.
Pipeline không âm thầm áp cách diễn giải khí khô của hướng dẫn EGG4 cho các khí EAC4 này.
Cấu hình EAC4 và danh tính tham số được đối chiếu theo
[hướng dẫn EAC4](https://confluence.ecmwf.int/spaces/CKB/pages/83395896/CAMS+Reanalysis+data+documentation).

q là khối lượng hơi nước trên khối lượng không khí ẩm,
[theo định nghĩa tham số 133](https://codes.ecmwf.int/grib/param-db/?id=133).
Công thức dùng hỗn hợp khí lý tưởng gồm khí khô và hơi nước, bỏ qua nước ngưng tụ.

### Thứ tự tính

```text
MMR, T_model, q_model, sp cùng ô lưới / thời điểm / tầng
        → áp suất hybrid → mật độ → nồng độ từng ô
        → kiểm tra hợp lệ → trung bình diện tích theo vùng → Parquet
```

```text
NO₂ / SO₂ / O₃: µg/m³ = MMR × rho_moist × 10⁹
CO:              mg/m³ = MMR × rho_moist × 10⁶
PM:              µg/m³ = nguồn kg/m³ × 10⁹
Tổng cột:        mg/m² = nguồn kg/m² × 10⁶
```

Không dùng `mean(MMR) × mean(rho)` thay `mean(MMR × rho)`.
PM đã là khối lượng/thể tích nên không nhân mật độ thêm lần nữa.
Nếu một nguồn được xác nhận theo khí khô, công thức tương ứng dùng
`rho_dry=(1−q)×rho_moist`; phép tính này được kiểm thử riêng, không dùng cho
bốn khí có cơ sở khối lượng ẩm trong generation này.

## 4. Dữ liệu thiếu và kiểm tra hợp lệ

- p_model > 0, nằm đúng giữa hai biên tầng và phù hợp với sp.
- T_model > 0 K; q hữu hạn và 0 ≤ q < 1; mật độ hữu hạn, dương.
- Thiếu hoặc sai đầu vào thì nồng độ là NULL, có lý do trong `quality_reason`.
- Không có fallback sang mật độ cố định, trường khí tượng khác hay giá trị giờ trước.
- Giá trị gió âm được giữ nguyên. Không cắt giá trị thực theo một ngưỡng tùy ý.
- Phép tổng hợp giữ trọng số diện tích EPSG:6933 và 36 vùng báo cáo. Cần ít nhất
  95% diện tích hợp lệ; ngày cần 18/24 slot, tháng cần 75% slot kỳ vọng.

## 5. Các giá trị chuẩn số học

Với p_model=95000 Pa, T_model=300 K, q=0,01:

| Đại lượng | Kết quả tham chiếu độc lập |
| --- | ---: |
| R_mix | 288,7945 J/(kg·K) |
| Mật độ khí ẩm | 1,0965121103991477 kg/m³ |
| MMR=10⁻⁷, cơ sở khí ẩm | 109,65121103991477 µg/m³ |
| Cùng MMR, hiển thị CO | 0,10965121103991477 mg/m³ |
| Cùng MMR, cơ sở khí khô | 108,55469892951563 µg/m³ |
| PM2.5=2,5×10⁻⁸ kg/m³ | 25 µg/m³ |

Đây là dữ liệu tổng hợp để kiểm tra phép tính, không phải quan sát EAC4.
Công thức nhiệt độ ảo được kiểm tra tương đương đại số với công thức hỗn hợp,
trong cùng giả thiết khí lý tưởng.

## 6. Kết quả triển khai được ghi nhận

| Hạng mục | Kết quả lần kiểm chứng 30/10/2026 |
| --- | --- |
| Generation | `5febe7dde83c41fdac2e3ba5a5532844` |
| Dữ liệu phục vụ | 130.651.056 dòng; 18 chỉ số, 36 vùng; thêm hai biến nội bộ cho mật độ |
| Khí suy ra | Mỗi khí có 7.258.392 dòng vùng–giờ hợp lệ |
| Backend | 49 kiểm thử đạt; còn một cảnh báo deprecation Starlette/httpx |
| Frontend | Bốn tệp kiểm thử đạt; lint và build đạt |
| Trình duyệt | Hai route × ba chiều rộng 1440/768/390 px; không lỗi console hoặc tràn ngang |
| Khoảng trống cuối thẻ bản đồ Admin | 1 px viền ở cả ba kích thước |
| Thời gian repository mặc định | 474,48 ms lần đầu; 21,71 ms khi dùng cache, một lần đo cục bộ, chưa tính HTTP/browser |

Đối chiếu GRIB độc lập khớp bốn khí trên 36 vùng tại sáu mốc, bao gồm hai biên
đổi mã hóa PV năm 2013 và 2017. Hai API trả đủ 24 giờ cho ngày hoàn chỉnh
30/12/2025. Trung bình ngày/tháng tháng 12/2025 của cả bảy chất khớp phép tính lại
từ dữ liệu giờ. Hash của cả 20 tệp nguồn và ranh giới vẫn khớp sau xử lý.

| Bằng chứng | Nội dung |
| --- | --- |
| [integration.json](../../reports/dashboard/science/integration.json) | API, tham chiếu ô lưới, tổng hợp thời gian và hiệu năng |
| [final-integrity.json](../../reports/dashboard/science/final-integrity.json) | Hash và chất lượng đầu ra khí |
| [backend-tests.txt](../../reports/dashboard/science/backend-tests.txt) | Kết quả bộ test backend |
| [frontend-tests.txt](../../reports/dashboard/science/frontend-tests.txt) | Kết quả test frontend |
| [frontend-lint.txt](../../reports/dashboard/science/frontend-lint.txt) / [frontend-build.txt](../../reports/dashboard/science/frontend-build.txt) | Lint và build |
| [browser-results.json](../../reports/dashboard/science/browser-results.json) | Bộ lọc, đơn vị, CSV, layout và kích thước bản đồ |

Ảnh: [User desktop](../../reports/dashboard/science/user-1440.png),
[Admin desktop](../../reports/dashboard/science/admin-1440.png),
[User mobile](../../reports/dashboard/science/user-390.png),
[Admin mobile](../../reports/dashboard/science/admin-390.png).

## 7. Dọn dữ liệu và giới hạn còn lại

Sau khi kiểm chứng, đã xóa 705 đường dẫn lỗi thời thuộc ba generation cũ và
`backend/app/etl/sample.py`. Các API và kiểm tra trình duyệt vẫn đạt sau khi xóa.
[Biên bản xóa](../../reports/dashboard/science/deleted-files.json) ghi từng đường dẫn,
kích thước, hash và lý do. GRIB gốc, tệp địa lý, fixture và Lakehouse không bị sửa/xóa.

322 partition không đổi được xác minh tái sử dụng bằng hard link trước khi dọn;
[bằng chứng trước cleanup](../../reports/dashboard/science/integration-before-cleanup.json)
được giữ lại. Xóa đường dẫn cũ không xóa liên kết dữ liệu trong generation mới.
Mã generation cha trong metadata chỉ phục vụ truy vết, không phải dependency runtime.

Các giới hạn cần giữ nguyên khi diễn giải số liệu:

1. Nội suy theo giờ không biến dữ liệu mô hình thành quan sát trạm độc lập.
2. Bộ biến được cung cấp không đủ để định lượng hiệu chỉnh nước ngưng tụ bị bỏ qua.
3. Nồng độ và thang màu mô tả không xác nhận mức sức khỏe hoặc AQI.
4. Partition lớn là tệp tạo cục bộ; bản clone mới cần ETL trước khi đọc đủ dữ liệu.

Chi tiết thay đổi code và hồ sơ triển khai đầy đủ nằm trong
[bản lưu kỹ thuật](archive/scientific-hourly-validation-2026-10-30.md).
