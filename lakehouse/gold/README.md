# Gold layer

Lớp Gold chưa được triển khai. Kế hoạch dựa trên code Bronze/Silver, dữ liệu Landing và các yêu cầu GET chỉ đọc tới Supabase ngày 27/10/2026:

- [Kế hoạch xây dựng Gold](../../docs/gold-implementation-plan.md)
- [Bằng chứng inventory](../../docs/gold-source-review.json)

Đích kiến trúc: Iceberg `nessie.gold` trên MinIO, dùng chung Nessie catalog với Silver; Trino đọc qua `iceberg.gold`; FastAPI phục vụ published releases. Fact giữ riêng grain CAMS, WAQI, API Ninjas city proxy và Climate TRACE, dùng dimensions chung.

Ưu tiên đầu tiên: readiness của Silver, Gold contracts và pilot CAMS nhỏ trước full backfill. Các bảng/job/DAG được liệt kê trong kế hoạch là phần sẽ xây dựng, chưa phải các thành phần đang hoạt động.
