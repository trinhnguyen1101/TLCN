> Archived MVP evidence. The current acceptance report is [VALIDATION.md](VALIDATION.md).

# Gold implementation validation — 28/10/2026

**Kết luận:** MVP hourly storage + pure VN_AQI engine + materialized marts + Trino/FastAPI
đã chạy trên stack thật. CAMS là real-data validation pilot; AQI 1h/1d hợp lệ chỉ được nghiệm thu
bằng isolated hourly fixtures. Chưa nghiệm thu archive production hoặc AQI quan trắc production.

## 1. Audit đầu vào và runtime

- Compose healthy: MinIO, Nessie 0.104.5, Spark 3.5.4/Iceberg1.7.1, Trino476, Airflow2.10.5.
  Spark image Java11/Python3.8, worker2 cores/2GiB; pilot local[1], driver2GiB.
  Host khoảng15GiB RAM. Không cài thêm dependency ETL.
- Silver có succeeded attempts cho hành chính, WAQI historical và Climate TRACE.
  CAMS standard **3 time/grid rows**, từ 2003-01-01 00:00 tới06:00UTC;
  source_version `EAC4-validation-cams-validation-30fffe54da92`. Không có EAC4 production được xác nhận.
- Một grid25×23=575points, increments0.75°. Sáu concentration fields chuẩnug/m3;
  PM model_surface, CO/NO2/O3/SO2 model_level60. Không sử dụng các column quantities/weather làm AQI.
- 34 root provinces; Hoàng Sa20333→48, Trường Sa22736→56 đã xác nhận bằng Silver.
  Geography policy/mapping được version trong `contracts/reporting-geography-v1.json`.
- Live WAQI tables đã có DDL nhưng chưa có succeeded live run; các bảng `province_air_quality_*`
  của job Ninjas hiện tại chưa hiện diện trong catalog được audit;
  không suy readiness từ snapshots Supabase hoặc từ schema tài liệu.
- Evidence đầy đủ: [runtime-audit.json](runtime-audit.json). Kiểm tra chỉ đọc, không đụng credentials trong output.

## 2. Kết quả theo phase

| Phase | Files chính được tạo/sửa | Tables/data đã chạy | Kết quả/giới hạn |
| --- | --- | --- | --- |
| 0 Audit/design | `lakehouse/gold/{README,SCHEMA,RUNBOOK}.md`, bổ sung trạng thái vào Gold Plan v2, contracts/references | Đọc Silver qua Trino; kiểm tra dataset/run/hierarchy/units | Chốt hourly; tách validation/production, native/model/provider; ghi các delta với v2 |
| 1 Foundation | `gold.sql`, `dimensions.py`, `spatial.py`, `adapters.py`, `runtime.py`, Compose Gold mounts | `gold_pilot`:34series,612concentration facts; dim/spatial cache thật | Sparse facts tại3 timestamps,36admin/component rows=34roots+2children; không36tỉnh |
| 2 AQI | `aqi/{engine,reference}.py`, `calculate_aqi.py`, tests/fixtures | CAMS:816hourly overall rows NULL,4896components,34daily overall NULL/238components. Hourly fixture:48AQIgiờ/2AQIngày hợp lệ | Eligibility chặn instantaneous3h. Method/raw/BP/window/count/lineage lưu được; không0khi unavailable |
| 3 Marts/serving | `marts.py`, backend Gold repos/schemas/routes/factory, frontend hourly/QC/colors/AQI selectors | Pilot hourly4896rows; daily/monthly/quality mỗi204rows. Map34tỉnh; compatibility User/Admin và native emissions API | Spark/Trino/ASGI pass; Chrome live qua Vite→FastAPI→Trino→Iceberg pass. Chưa materialize concentration color scales |
| 4 Operations | `run.py`, `incremental.py`, `activate_release.py`, `scripts/run_gold.py`, pipeline integration script | Replay, corrections, deletion, QC rejection, failed stage, registered-before-pointer recovery, rollback, Jan/Feb fixture | Pass trên stack; host runner một writer. Airflow transport, distributed writers, retention và composite multi-chunk reads chưa triển khai |
| 5 Native sources | `native_sources.py`,4DDL native tables, native emissions endpoint | WAQI179843; emissions aggregate17280; source observations32384; national totals mart216 | Unit NULL/unverified giữ nguyên; source type/GADM unallocated. Chưa có emissions tonnes hoặc province allocation được chứng nhận |

DDL có26table definitions cho từng namespace được bootstrap. Bảng không có published release không tự trở
thành nguồn serving. `gold` channel air_quality chưa publish; native_sources có dữ liệu thật. Namespace
`gold_test*` chứa fixture, không production. Native branch không chặn concentration/AQI.

## 3. AQI, temporal và analytical checks

`backend/.venv/bin/python -m unittest discover -s spark/jobs/gold/tests -v`: **16 tests pass**.
Bao gồm toàn bộ breakpoints/top policy, half-up, invalid/negative/nonfinite/zero, method checksum,
NowCast normal/missing/zero và w=0.5, fixed time slots, PM bắt buộc, ties, category colors,
3hinstant/1hinstant/provider_snapshot ineligible,24/24daily gates, O3rolling8h qua nửa đêm,
VN midnight/leap day, invalidation qua tháng và spatial intersection denominator.

PDF tham chiếu lưu với SHA-256
`968c4cbb9bf5cf03e4a9bf30850afd8695d130f767324ac57ca02e2d54a48c26`.
Method `vn-aqi-1459-2019-project-v1`; source/method review trong
[reference metadata](../../lakehouse/gold/references/reference.json).
Ví dụ PDF NowCast≈20.3, daily AQI110 và O3max8h≈74.4 được đối chiếu.
**Sai lệch tài liệu được ghi rõ:** NO2=118.7 cho59.35→59 theo half-up nhưng PDF ví dụ in60;
engine theo công thức, không sửa dữ liệu để khớp lỗi số học. Rounding và daily completeness là policy dự án.

`test_gold_pipeline.py` đã thực thi trên Spark/Iceberg/Trino:

1. Fixture48hourly means+11halo hours, sáu pollutants, area_estimate; tất cả48hourly/2daily AQI=50.
2. Replay giữ release và mọi snapshot mapping, không sinh thêm rows/rewrite outputs.
3. SửaPM25 tại23hlocal từ25→100; xóa một input PM25 ngày kế tiếp. Daily AQI thành56/10,
   valid_hours PM25=24/23. Record bị rút lại không còn trong facts mới.
4. SO2 có value dương nhưng QCinvalid: Gold valueNULL, giữ reason; daily valid_hours giảm23,
   không đưa giá trị QC bị từ chối vào concentration statistics hoặc AQI.
5. Fail trước registry giữ pointer cũ; fail sau registry trước pointer cũng giữ pointer cũ.
   Retry phục hồi pointer từ immutable registry; đọc release cũ vẫn đúng snapshot cũ.
6. Explicit rollback khôi phục kết quả cũ; restore fixtures tạo release baseline hợp lệ.
7. Fixture Jan31→Feb2 qua UTC/local date và month partitions:48slots,2dailyAQI, hai monthly aggregates,
   valid_hours mỗi ngày24, không mất dữ liệu ở boundary.

Markers, run times và release IDs: [pipeline-checks.json](pipeline-checks.json).
Logs `.log` nằm local (gitignored); JSON giữ các marker cần kiểm tra.

## 4. Serving, frontend và performance

- Gold API contract tests: **6pass**. SQL identifiers/literals, pin manifest, query bounds,503/no sample fallback,
  hourly không được âm thầm đi qua legacy Parquet.
- Frontend model suite: **19pass**. Hourly đủ slot, AQI không average qua tỉnh/kỳ,
  daily concentration weighting dùng actual sample counts. Frontend builds mặc định và `--mode gold` pass.
- [Serving checks](serving-checks.json): hourly/daily/monthly, map34, source quality,
  admin summary, compatibility dashboard User/Admin; native emission query giữ unitNULL/unverified.
  Latency pilot ghi trong JSON theo từng request, khoảng0.07–0.97s trên máy hiện tại; không phải SLA.
- [Live browser checks](ui-checks-live.json): Chrome→Vite proxy→FastAPI→Trino→Iceberg,
  map34, picker24giờ, khôngJSerrors; browser requests User/Admin đều dùng `resolution=hourly`. [User](user-pilot-live.png), [Admin](admin-pilot-live.png),
  [24-hour picker](hourly-picker-live.png). External network tiles bị chặn trong smoke check;
  province geometry/basemap nội bộ vẫn render. Không dựa screenshot làm bằng chứng tính đúng AQI.
- Concentration map chưa có materialized color scale: chú giải công khai trạng thái chưa phân lớp,
  giá trị thật có trong tooltip/table; không dùng breakpointAQI làm concentration categories.
- [Process metrics](pilot-process-metrics.json): pilot khoảng33–37s, maximum childRSS khoảng1.60GiB ở lượt cuối (các pilot1.6–1.7GiB),
  driver heap2GiB. Đây là Linux child maxRSS, không phải tổng peak memory toàn Docker stack.
- File count/bytes theo published release nằm trong `runtime-audit.json.storage`.
  Pilot fact chỉ khoảng16KB/1file, hourly mart khoảng32KB/2files do vượt boundary tháng UTC;
  small files là hệ quả scope rất nhỏ. Chưa suy SLA/tuning/full-archive cost từ pilot này.
- Host backfill runner đã chạy replay scope pilot thành công, khoảng8s; chunk mặc định7ngày,
  giới hạn1–31ngày mỗi release. Không chạy full archive.

## 5. Các phần chưa nghiệm thu và lỗi regression có sẵn

- Chưa có nguồn Silver hourly mean thật hoặc full EAC4 production archive; computed AQI production chưa có.
- Chưa có station/proxy Gold adapters, Ninjas unit migration, collection telemetry từ Silver,
  GADM crosswalk/province emissions, normalized/certified emission units, concentration map scales,
  Airflow submit transport hoặc API compose nhiều releases lịch sử.
- Snapshot retention/garbage collection/distributed locking chưa triển khai; không expire snapshot đang được giữ.
- Toàn bộ backend regression đã được thử: suite analytics cũ lỗi thiếufixture `client` (2errors)
  và thiếu `DashboardService.get_analytics` (1failure); phần service/routes đó tồn tại nguyên trạng trước task.
  Lần chạy rộng ban đầu9pass/1fail/2errors; sau đó Gold contract suite tăng lên6pass độc lập.
  Không tuyên bố toàn repository test suite xanh. Không mở rộng task để viết lại analytics legacy.
- Không switch mặc định dashboard sang pilot/fixture. Gold outage trả503; sample chỉ còn ở cấu hình legacy rõ ràng.

Để tái lập hoặc tiếp tục: [Gold README](../../lakehouse/gold/README.md),
[physical schema/deltas](../../lakehouse/gold/SCHEMA.md), [runbook](../../lakehouse/gold/RUNBOOK.md).
