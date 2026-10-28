# Tài liệu dự án Vietnam Air Quality Lakehouse

Tài liệu được nhóm theo công việc và thành phần hệ thống. Các lệnh trong hướng
dẫn vận hành vẫn chạy từ **thư mục gốc repository**, nơi có `docker-compose.yml`.

## Tìm nhanh

| Bạn muốn… | Đọc tài liệu |
| --- | --- |
| Chạy Landing → Bronze → Silver → Gold thủ công | [Hướng dẫn chạy pipeline](operations/RUN.md) |
| Hiểu hai luồng Landing batch và Supabase daily | [Airflow orchestration cho Lakehouse](airflow/daily-supabase-pipeline.md) |
| Hiểu dữ liệu được chuẩn hóa ở Silver | [Mô tả lớp Silver](lakehouse/SILVER.md) |
| Hiểu hourly facts, AQI, marts và historical serving | [Mô tả lớp Gold](lakehouse/GOLD.md) |
| Chạy FastAPI và User/Admin dashboard | [Thiết lập web dashboard](dashboard/setup-web-dashboard.md) |
| Tìm hiểu thu thập dữ liệu qua Supabase | [Cloud ingestion](supabase/TLCN_Supabase_Cloud_Ingestion_Full_Documentation.md) |
| Tra dữ liệu nguồn, fields và units | [Từ điển dữ liệu nguồn](data/data-dictionary.md) |

## Cấu trúc thư mục

```text
docs/
├── README.md                         # Mục lục tài liệu
├── airflow/                          # Orchestration và lịch pipeline
│   └── daily-supabase-pipeline.md
├── operations/                       # Chạy và kiểm tra pipeline
│   └── RUN.md
├── lakehouse/                        # Các lớp dữ liệu và thiết kế Lakehouse
│   ├── landing-to-bronze.md
│   ├── SILVER.md
│   └── GOLD.md
├── supabase/                         # Thu thập và dữ liệu operational
│   ├── supabase-operational-design.md
│   ├── supabase-to-lakehouse-plan.md
│   └── TLCN_Supabase_Cloud_Ingestion_Full_Documentation.md
├── dashboard/                        # Backend/frontend và dashboard setup
│   └── setup-web-dashboard.md
└── data/                             # Danh mục và semantics dữ liệu nguồn
    └── data-dictionary.md
```

## Lakehouse và pipeline

- [Airflow orchestration cho Lakehouse](airflow/daily-supabase-pipeline.md): hai
  DAG Landing batch/Supabase daily, task graph, retry, quality gate và Spark submission.
- [Landing → Bronze](lakehouse/landing-to-bronze.md): raw files, manifest,
  checksum và cách kiểm tra dữ liệu trên MinIO.
- [Silver](lakehouse/SILVER.md): chuẩn hóa theo từng nguồn, grain, units, clocks,
  QC, lineage và điều kiện để dữ liệu được Gold tiếp nhận.
- [Gold](lakehouse/GOLD.md): hourly storage, spatial aggregation, VN_AQI,
  analytical marts, publication, historical queries và dashboard contracts.
- [Gold schema v2 lưu trữ](../lakehouse/gold/SCHEMA-v2-ARCHIVE.md): thiết kế schema
  ban đầu; phân biệt với implementation hiện tại trong Gold SCHEMA.
- [Script rà soát nguồn Gold](../scripts/review_gold_sources.py) ghi output vào
  `docs/lakehouse/gold-source-review.json`. Artifact này hiện không có trong
  checkout; chỉ dùng `--reuse-cloud` khi đã có output của một lần rà soát trước.
- [RUN](operations/RUN.md): các lệnh thực hành, gồm CAMS pilot, backfill theo
  chunk, fixture hourly, native sources và kiểm tra API.

## Supabase và dashboard

- [Supabase operational design](supabase/supabase-operational-design.md): thiết
  kế collection runs, snapshots, storage, quyền truy cập và operational views.
- [Supabase → Lakehouse plan](supabase/supabase-to-lakehouse-plan.md): contracts
  và kế hoạch đồng bộ qua Bronze/Silver.
- [Cloud ingestion documentation](supabase/TLCN_Supabase_Cloud_Ingestion_Full_Documentation.md):
  tài liệu triển khai tổng hợp, SQL, Edge Functions, Cron và phụ lục; đọc cùng
  trạng thái xác nhận được ghi trong từng phần.
- [Dashboard setup](dashboard/setup-web-dashboard.md): cài môi trường và chạy
  backend/frontend. Cấu hình Gold mode cụ thể có trong [RUN](operations/RUN.md).

## Schema, vận hành và bằng chứng kiểm thử

Các tài liệu sát implementation tiếp tục nằm cạnh code/schema hoặc reports:

| Nội dung | Vị trí |
| --- | --- |
| Silver schema/source contracts | [lakehouse/silver/README.md](../lakehouse/silver/README.md), [silver.sql](../lakehouse/silver/silver.sql) |
| Silver jobs và physical conversions | [spark/jobs/silver/README.md](../spark/jobs/silver/README.md) |
| Gold physical schema | [SCHEMA.md](../lakehouse/gold/SCHEMA.md), [gold.sql](../lakehouse/gold/gold.sql) |
| Gold backfill/recovery/rollback | [RUNBOOK.md](../lakehouse/gold/RUNBOOK.md) |
| Gold validation/readiness | [VALIDATION.md](../reports/gold/VALIDATION.md) |
| Gold performance measurements | [Performance report](../reports/gold/performance/README.md) |

Ưu tiên code/schema và evidence mới nhất khi tài liệu kế hoạch hoặc inventory
cũ khác hiện trạng. Từ điển dữ liệu và source-review JSON là ảnh chụp có thời
điểm, không phải inventory tự cập nhật.

Tài liệu mới nên đặt vào nhóm phù hợp và thêm liên kết tại mục lục này. Liên kết
giữa tài liệu dùng đường dẫn tương đối; lệnh shell và đường dẫn code trong ví dụ
vẫn tính từ repository root, trừ khi tài liệu ghi rõ cách khác.
