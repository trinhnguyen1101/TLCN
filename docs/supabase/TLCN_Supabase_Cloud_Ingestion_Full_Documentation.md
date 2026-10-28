# Supabase Cloud Ingestion — tài liệu triển khai tổng hợp

[Mục lục tài liệu](../README.md) / **Supabase**

**Dự án:** TLCN — hệ thống dữ liệu chất lượng không khí Việt Nam  
**Phiên bản tài liệu:** 2026-10-26  
**Phạm vi:** Supabase Cloud operational / near-real-time ingestion, hai nguồn WAQI và API Ninjas; điểm kết nối với local Lakehouse.

> **Nguồn và phạm vi xác nhận:** Tài liệu này kết hợp thiết kế gốc `supabase-operational-design.md`, hai file Edge Function TypeScript đã tạo trong cuộc trao đổi, các câu lệnh SQL/thiết lập được hướng dẫn và kết quả kiểm thử người dùng cung cấp. Không có quyền đọc trực tiếp trạng thái hiện tại của project Supabase. Vì vậy, nội dung được đánh dấu **đã xác nhận bằng kết quả kiểm thử** khác với **SQL/cấu hình đề xuất cần đối chiếu**. Không đưa secret thật vào tài liệu.

## A. Tổng quan kiến trúc

```text
WAQI Station Feed API           API Ninjas Air Quality API
        |                                  |
        +------------ Supabase Cron ------+
                    /                 \
            collect-waqi         collect-api-ninjas
                    \                 /
                  Supabase Cloud
                    |         |
          private Storage   PostgreSQL (operational)
          raw-api bucket    5 tables + latest views
                    |         |
              daily sync   Web App dashboard
                    |
              MinIO Bronze -> Spark ETL -> Iceberg Silver -> Gold
```

Hệ thống hoạt động theo **scheduled micro-batch mỗi giờ**, không phải streaming liên tục. Toàn bộ collector chạy trên Supabase Cloud; máy local không cần bật để thu thập. Chỉ Daily Sync sang MinIO và ETL local phụ thuộc thiết bị hoặc máy chủ chạy Lakehouse.

### A.1. Quy ước thời gian

- `scheduled_hour_utc`: đầu giờ UTC logic của lần thu thập, cùng giá trị cho mọi target trong run.
- `collected_at_utc`: thời điểm thực tế collector nhận phản hồi API.
- `waqi_time`: thời điểm quan trắc do WAQI cung cấp (có thể cũ hơn nhiều giờ).
- Retry giờ cũ **không thể tái tạo quan trắc lịch sử** nếu API chỉ trả dữ liệu hiện tại.
- Cron WAQI: `0 * * * *` (phút 00 hằng giờ); API Ninjas: `5 * * * *` (phút 05 hằng giờ). Cron vận hành theo UTC, phút 00/05 trùng phút tương ứng theo giờ Việt Nam.

### A.2. Các thành phần

| Thành phần | Vai trò |
|---|---|
| `collection_runs` | Run ID, nguồn, giờ logic, attempt, counters, trạng thái, manifest |
| `waqi_stations` | Master data WAQI theo `source_uid` (text, UID âm hợp lệ) |
| `waqi_snapshots` | Mỗi lần thu thập mỗi trạm, lưu observation và lineage |
| `api_ninjas_locations` | 34 city-proxy points đại diện địa phương |
| `api_ninjas_snapshots` | AQI và concentrations theo location và run |
| `latest_waqi_by_station` | Snapshot mới nhất hợp lệ theo station phục vụ Web App |
| `latest_api_ninjas_by_province` | Snapshot mới nhất hợp lệ theo location phục vụ Web App |
| Storage `raw-api` | Private immutable provider response `.raw.json` + `manifest.json` |
| RPC `claim_collection_run` | Cấp attempt nguyên tử, skip succeeded/running |
| Cron + Vault | Trigger mỗi giờ và xác thực secret trong backend |

## B. Thiết lập SQL trên project hiện tại

### B.1. Schema gốc

**Các bảng và views phải được tạo theo phần SQL trong Phụ lục 1**. Trình tự: `collection_runs` → `waqi_stations` → `waqi_snapshots` → `api_ninjas_locations` → `api_ninjas_snapshots` → indexes → latest views → RLS. Phụ lục giữ nguyên toàn văn tài liệu thiết kế gốc, gồm các câu lệnh `CREATE TABLE`, indexes và views.

### B.2. Những cột bổ sung trong `collection_runs`

```sql
ALTER TABLE public.collection_runs
    ADD COLUMN IF NOT EXISTS manifest_object_path text,
    ADD COLUMN IF NOT EXISTS manifest_sha256 char(64);
```

Hai cột này được hai Edge Functions đính kèm sau khi manifest lưu thành công ở Storage. Nếu một run bị terminate trước finalize, chúng có thể vẫn là `NULL`.

### B.3. Trạng thái `timed_out` (migration nếu chưa có)

```sql
ALTER TABLE public.collection_runs
    DROP CONSTRAINT IF EXISTS collection_runs_status_check;

ALTER TABLE public.collection_runs
    ADD CONSTRAINT collection_runs_status_check
    CHECK (status IN ('running','succeeded','partial','failed','timed_out'));
```

> Chỉ chạy migration này khi muốn áp dụng watchdog. Cần rà soát constraint hiện có trước khi thay thế, tránh vô tình bỏ các trạng thái đã bổ sung độc lập.

### B.4. RPC atomic claim — chữ ký 3 tham số đúng với Edge Functions

**Đối chiếu:** Hai Edge Functions hiện gọi `rpc('claim_collection_run', { p_source, p_scheduled_hour_utc, p_expected_records })`. Nếu project đang có overload bốn tham số, có thể dùng bản đó với tham số default, nhưng nên quản lý một chữ ký chính để tránh nhầm. Ví dụ triển khai dưới đây hỗ trợ ba tham số. Không tự động timeout `running` trong RPC; watchdog độc lập xử lý.

```sql
CREATE OR REPLACE FUNCTION public.claim_collection_run(
    p_source text,
    p_scheduled_hour_utc timestamptz,
    p_expected_records integer
)
RETURNS TABLE (
    claimed_run_id uuid,
    claimed_attempt smallint,
    claimed boolean,
    reason text
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_latest public.collection_runs%ROWTYPE;
    v_next integer;
    v_id uuid;
BEGIN
    IF p_source NOT IN ('waqi','api_ninjas') THEN
        RAISE EXCEPTION 'Invalid source';
    END IF;
    IF p_scheduled_hour_utc IS NULL
       OR p_scheduled_hour_utc <> pg_catalog.date_trunc('hour', p_scheduled_hour_utc)
       OR p_scheduled_hour_utc > now()
       OR p_scheduled_hour_utc < now() - interval '7 days'
    THEN
        RAISE EXCEPTION 'Invalid scheduled hour';
    END IF;
    IF p_expected_records IS NULL OR p_expected_records <= 0 THEN
        RAISE EXCEPTION 'Invalid expected records';
    END IF;

    PERFORM pg_catalog.pg_advisory_xact_lock(
        pg_catalog.hashtext(p_source),
        pg_catalog.hashtext(p_scheduled_hour_utc::text)
    );

    IF EXISTS (
        SELECT 1 FROM public.collection_runs
        WHERE source=p_source AND scheduled_hour_utc=p_scheduled_hour_utc
          AND status='succeeded'
    ) THEN
        SELECT * INTO v_latest FROM public.collection_runs
        WHERE source=p_source AND scheduled_hour_utc=p_scheduled_hour_utc
          AND status='succeeded'
        ORDER BY attempt_number DESC LIMIT 1;
        RETURN QUERY SELECT v_latest.run_id, v_latest.attempt_number,
            FALSE, 'already_succeeded'::text;
        RETURN;
    END IF;

    SELECT * INTO v_latest
    FROM public.collection_runs
    WHERE source=p_source AND scheduled_hour_utc=p_scheduled_hour_utc
    ORDER BY attempt_number DESC LIMIT 1 FOR UPDATE;

    IF found AND v_latest.status='running' THEN
        RETURN QUERY SELECT v_latest.run_id, v_latest.attempt_number,
            FALSE, 'already_running'::text;
        RETURN;
    END IF;

    v_next := coalesce(v_latest.attempt_number, 0)+1;
    IF v_next > 32767 THEN
        RAISE EXCEPTION 'Attempt limit exceeded';
    END IF;

    INSERT INTO public.collection_runs(source,scheduled_hour_utc,attempt_number,expected_records,status)
    VALUES (p_source,p_scheduled_hour_utc,v_next,p_expected_records,'running')
    RETURNING run_id INTO v_id;
    RETURN QUERY SELECT v_id, v_next::smallint, TRUE, 'created'::text;
END;
$$;

REVOKE ALL ON FUNCTION public.claim_collection_run(text,timestamptz,integer)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.claim_collection_run(text,timestamptz,integer)
    TO service_role;
NOTIFY pgrst, 'reload schema';
```

> **Giới hạn:** Advisory lock chỉ bảo đảm claim nguyên tử tại transaction. Chưa có fencing token để chặn tiến trình cũ tiếp tục ghi sau khi watchdog đánh dấu timeout. Đây không phải exactly-once end-to-end.

### B.5. Watchdog — tùy chọn, cần bật Cron riêng

```sql
CREATE OR REPLACE FUNCTION public.expire_stale_collection_runs()
RETURNS integer
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE v_count integer;
BEGIN
    UPDATE public.collection_runs
    SET status='timed_out', finished_at_utc=now(),
        error_message='Collection run exceeded 10 minutes'
    WHERE status='running'
      AND started_at_utc < now()-interval '10 minutes';
    GET DIAGNOSTICS v_count = ROW_COUNT;
    RETURN v_count;
END;
$$;
REVOKE ALL ON FUNCTION public.expire_stale_collection_runs()
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.expire_stale_collection_runs()
    TO service_role;
```

Chưa có bằng chứng watchdog đã được schedule trong project. Nếu muốn chạy tự động, cấu hình Cron job gọi `expire_stale_collection_runs` bằng database role được phép, sau khi kiểm tra giới hạn runtime và khả năng worker cũ còn chạy.

### B.6. RLS và grants

Bảng đã bật RLS theo tài liệu thiết kế. Để `security_invoker=true` hoạt động, cần chính sách `SELECT` tương thích với vai trò thực sự đọc dashboard. Không triển khai ngay `USING (true)` cho `anon` khi chưa quyết định dữ liệu nào được phép công bố. Browser **không được** dùng `sb_secret_...`, không có quyền ghi collection tables; collectors dùng `ctx.supabaseAdmin` phía server. Quyền đọc Supabase Storage `raw-api` không mở public.

## C. Danh mục đầu vào cần seed

- `api_ninjas_locations`: 34 hàng city proxy, gồm `location_key`, `province_name`, `query_city`, latitude/longitude. **Không insert AQI lịch sử vào danh mục**.
- `waqi_stations`: 31 trạm, gồm `source_uid`, tên trạm, tọa độ, timezone. UID có thể âm, lưu `text`.
- Dữ liệu danh mục đã được người dùng nhập và kiểm tra thành công trong các lượt test; bản SQL seed tái lập ở Phụ lục 2. Địa danh station có thể dùng tên hành chính lịch sử; không tự sửa tên đo gốc.

## D. Storage / object lineage

**Bucket:** `raw-api` (private). Không bật public access. Object write dùng `upsert: false`.

```text
raw-api/
  waqi/YYYY/MM/DD/HH/<run-id>/<source-uid>.raw.json
  waqi/YYYY/MM/DD/HH/<run-id>/manifest.json
  api_ninjas/YYYY/MM/DD/HH/<run-id>/<location-key>.raw.json
  api_ninjas/YYYY/MM/DD/HH/<run-id>/manifest.json
```

Raw file chứa nguyên response body của provider; manifest chứa source, run ID, giờ logic, attempt, từng target, HTTP status, thời điểm request/response, path, checksum, outcome và lỗi. `manifest_sha256` trong `collection_runs` là SHA-256 của bytes manifest. Cần kiểm tra manifest tồn tại trên Storage và đối soát số objects trước khi sync sang Bronze.

## E. Cách deploy hai Edge Functions qua Dashboard

1. Vào **Edge Functions → Deploy a new function → Via Editor** (hoặc mở function đã có), chọn `collect-waqi` hay `collect-api-ninjas`.
2. Dán **toàn văn TypeScript ở Phụ lục 3 và 4** vào `index.ts`, rồi Deploy.
3. Vào **Edge Functions → Secrets**: cấu hình `WAQI_API_TOKEN`, `API_NINJAS_KEY` (không dán vào code).
4. Trong function Settings, tắt **Verify JWT with legacy secret** nếu handler dùng `withSupabase({ auth: 'secret' })`. Việc tắt legacy check không bỏ bảo vệ handler.
5. Test với `POST`, body `{}`, `Content-Type: application/json`, header `apikey: sb_secret_...` (key được handler chấp nhận). Không gửi key trong ảnh/log/GitHub.

Hai collectors đều: đọc targets đang active, claim collection run, gọi API bằng bounded worker pool 4 workers, giữ raw response, parse/validate, insert snapshots, tạo manifest và finalize run. Tổng time budget trong source: WAQI 105s, API Ninjas 110s; timeout gọi provider 12s. Những con số này **không bảo đảm** luôn dưới giới hạn gói Supabase hoặc quota nguồn.

## F. Vault và Cron trên Supabase Cloud

**Phân biệt:** `Project Settings → API Keys → Secret keys` dùng để tạo API Key; `Vault` là nơi lưu giá trị key mà SQL Cron đọc được. Tên API key `collector_secret_key` không tự tạo Vault secret cùng tên.

- Lưu **giá trị của Supabase Secret Key được chấp nhận bởi auth mode `secret`** vào Vault dưới tên `collector_secret_key`.
- `WAQI_API_TOKEN` và `API_NINJAS_KEY` là provider API keys, chỉ nằm trong Edge Function Secrets.
- Với config đã sử dụng, WAQI chạy `0 * * * *`, API Ninjas chạy `5 * * * *`.
- Request do Cron gửi bằng `net.http_post`, header `apikey` lấy từ `vault.decrypted_secrets`, không hardcode key trong SQL.

```sql
SELECT cron.schedule(
 'collect-waqi-hourly', '0 * * * *',
 $job$
 SELECT net.http_post(
   url := 'https://ohluxijrrlcqgbcnaflq.supabase.co/functions/v1/collect-waqi',
   headers := jsonb_build_object(
     'Content-Type','application/json',
     'apikey',(SELECT decrypted_secret FROM vault.decrypted_secrets WHERE name='collector_secret_key')
   ),
   body := '{}'::jsonb,
   timeout_milliseconds := 120000
 );
 $job$
);

SELECT cron.schedule(
 'collect-api-ninjas-hourly', '5 * * * *',
 $job$
 SELECT net.http_post(
   url := 'https://ohluxijrrlcqgbcnaflq.supabase.co/functions/v1/collect-api-ninjas',
   headers := jsonb_build_object(
     'Content-Type','application/json',
     'apikey',(SELECT decrypted_secret FROM vault.decrypted_secrets WHERE name='collector_secret_key')
   ),
   body := '{}'::jsonb,
   timeout_milliseconds := 120000
 );
 $job$
);
```

Lưu ý: cron.schedule với tên đang tồn tại cập nhật job cùng tên trong pg_cron. `pg_net` gửi HTTP bất đồng bộ, do đó job SQL `succeeded` không chứng minh function xử lý thành công. Nội dung `net._http_response` có thể bị dọn tự động.

### F.1. Kiểm tra cron, HTTP và dữ liệu

```sql
-- Lịch đang hoạt động
SELECT jobid, jobname, schedule, active
FROM cron.job
WHERE jobname IN ('collect-waqi-hourly','collect-api-ninjas-hourly');

-- Phản hồi từ pg_net (tạm thời)
SELECT id, status_code, content, error_msg, created
FROM net._http_response ORDER BY created DESC LIMIT 20;

-- Lịch sử run vận hành
SELECT run_id,source,scheduled_hour_utc,attempt_number,status,
       expected_records,successful_records,failed_records,
       manifest_object_path,manifest_sha256,started_at_utc,finished_at_utc
FROM public.collection_runs
ORDER BY started_at_utc DESC LIMIT 30;

-- Tổng snapshot từng giờ và nguồn
SELECT 'waqi' AS source,snapshot_hour_utc,COUNT(*) total_records
FROM public.waqi_snapshots GROUP BY snapshot_hour_utc
UNION ALL
SELECT 'api_ninjas' AS source,snapshot_hour_utc,COUNT(*) total_records
FROM public.api_ninjas_snapshots GROUP BY snapshot_hour_utc
ORDER BY snapshot_hour_utc DESC;
```

Nếu gặp `401 INVALID_API_KEY`, kiểm tra key gửi trong `apikey` có phải giá trị `sb_secret_...` đúng của project và được handler chấp nhận. Nếu `401 MISSING_CREDENTIALS`, kiểm tra Vault secret có tồn tại và SQL Cron đang lấy nó. Nếu HTTP `200` nhưng snapshots không tăng, xem response `skipped`, status run, manifest và lỗi validation.

## G. Kết quả kiểm thử đã ghi nhận (không phải dữ liệu hiện tại)

| Nguồn | Giờ logic UTC | Kết quả run | Số thành công/thất bại | Bằng chứng |
|---|---|---|---|---|
| WAQI | 2026-10-23 03:00 | partial | 30 / 1 | Response run và view latest |
| WAQI | 2026-10-25 04:00 | partial | 29 / 2 | SQL collection_runs và snapshots |
| API Ninjas | 2026-10-23 12:00 | succeeded | 34 / 0 | SQL collection_runs |
| API Ninjas | 2026-10-25 04:00 | succeeded | 34 / 0 | SQL run và 34 snapshots `valid` |

WAQI đã ghi `invalid` cho hai trạm ở run 2026-10-25 04:00 UTC: UID `13446` (Cẩm Phả, có PM2.5/PM10 nhưng không có overall AQI) và UID `8641` (Đại sứ quán Mỹ Hà Nội, overall AQI/PM2.5/PM10 NULL). Raw object path của cả hai được ghi trong database. Đây là vấn đề chất lượng dữ liệu provider, không chứng minh collector ngừng hoạt động.

**Quan trọng:** Các run bắt đầu lúc 04:27 hoặc 04:29 UTC đã từng được test ngoài phút 00/05. Chúng xác nhận function hoạt động, **không riêng lẻ chứng minh Cron chạy tự động ổn định**. Cần đối chiếu `cron.job`, HTTP invocation, và các run ở nhiều giờ sau.

## H. Dashboard, chất lượng dữ liệu, và độ trễ

`latest_*` views dùng để lấy mỗi trạm/location một snapshot gần nhất. Cần hiển thị `waqi_time` bên cạnh `collected_at_utc` để tránh gắn nhãn real-time sai. Với biểu đồ lịch sử, query bảng snapshots (không dùng latest view). `validation_status` là chất lượng snapshot; `collection_runs.status` là kết quả chạy toàn run — hai trạng thái khác nhau.

```sql
-- WAQI observation delay (giờ)
SELECT station_name,overall_aqi,waqi_time,collected_at_utc,
       round(extract(epoch FROM (collected_at_utc-waqi_time))/3600.0,2)
           AS observation_delay_hours,
       collection_status
FROM public.latest_waqi_by_station
ORDER BY observation_delay_hours DESC NULLS LAST;

-- Validation WAQI theo run
SELECT collection_run_id,validation_status,count(*)
FROM public.waqi_snapshots
GROUP BY collection_run_id,validation_status
ORDER BY collection_run_id;

-- API Ninjas coverage theo giờ
SELECT snapshot_hour_utc,count(*) AS records,
       count(DISTINCT location_id) AS locations,
       count(*) FILTER(WHERE validation_status='valid') AS valid_records
FROM public.api_ninjas_snapshots
GROUP BY snapshot_hour_utc ORDER BY snapshot_hour_utc DESC;
```

AQI của city proxy **không phải AQI bình quân không gian toàn tỉnh**. Dữ liệu WAQI IAQI cũng không được mặc định diễn giải là nồng độ µg/m³; đơn vị và ý nghĩa phải giữ đúng metadata từ provider.

## I. Đồng bộ hàng ngày về local Lakehouse — thiết kế, chưa xác nhận đã triển khai

Daily sync nên do Airflow/local job thực hiện: lấy các run `succeeded/partial`, liệt kê manifest và raw objects của từng run, xác thực SHA-256, copy vào batch bất biến MinIO Bronze, ghi `_file_metadata`, manifest và `_SUCCESS` cuối cùng, rồi mới update checkpoint. Khi local tắt, Supabase vẫn thu thập; lần sync sau dựa checkpoint để tải bù **các raw files đã tồn tại** (không thể bù các giờ source chưa được gọi).

Cấu trúc đề xuất:

```text
Supabase Storage raw-api
    -> Daily incremental sync + checksum + checkpoint
MinIO Bronze: bronze/waqi/live/... và bronze/api_ninjas/province_air_quality/...
    -> Spark Silver (WAQI dedupe theo observation time; API Ninjas theo location + logical hour)
    -> Iceberg Gold (analytical fact/dimension)
```

Không dùng duy nhất `synced_to_bronze` boolean; manifest/window/run/checksum và `_SUCCESS` mới là căn cứ commit. Không xóa raw orphan tự động khi snapshot insert thất bại.

## J. Rủi ro và phần chưa xác nhận hoàn thiện

1. **Fencing:** atomic claim và watchdog chưa bảo đảm exactly-once giữa process cũ và process mới.
2. **Run ở trạng thái running:** nếu Edge Function bị terminate, cần watchdog thực sự được schedule, có cảnh báo.
3. **Partial vs invalid:** 31 WAQI snapshots có thể được insert nhưng `successful_records=29`, vì hai invalid counted failed; cần xác định semantics thống nhất khi lập dashboard.
4. **HTTP errors & manifest:** manifest chứa outcome, nhưng cần reconciliation cho Storage upload thành công rồi DB insert thất bại, manifest chưa ghi, hoặc SQL finalize lỗi.
5. **Phân quyền:** tài liệu thiết kế chưa có một bộ `CREATE POLICY` cụ thể đã xác nhận cho frontend; cần khóa browser thành read-only, không public raw bucket.
6. **Tài nguyên và quota:** bounded concurrency 4 vẫn phải theo dõi Edge time budget và quota/rate limit WAQI/API Ninjas.
7. **Cron vận hành:** một lần test thủ công thành công không đủ kết luận lịch chạy ổn định; cần thống kê run mỗi giờ trong ít nhất vài chu kỳ và có alert khi bỏ lỡ.
8. **Source code:** source TypeScript được lấy từ artifact có trong cuộc trò chuyện; nếu bạn đã chỉnh sửa trực tiếp trên Dashboard sau đó, cần diff với phiên bản deploy thực tế.

---

# PHỤ LỤC 1 — Toàn văn thiết kế cơ sở (schema, views, RLS, Storage, Bronze)

Tài liệu gốc được giữ nguyên dưới đây để bảo toàn SQL, các constraint và giải thích ban đầu. Phần B–J phía trên nêu các thay đổi/bổ sung trong quá trình triển khai.

# Thiết kế Supabase cho dữ liệu chất lượng không khí

## 1. Phạm vi và vai trò

Supabase và local lakehouse đảm nhiệm hai vai trò khác nhau:

- **Supabase (operational layer):** chạy collector mỗi giờ, lưu raw API
  response, quản lý lịch sử collection run và cung cấp dữ liệu gần thời gian
  thực cho Web App.
- **Local lakehouse (analytical layer):** nhận raw data định kỳ, lưu lịch sử
  dài hạn và xử lý qua Bronze → Silver → Gold.

Luồng dữ liệu đề xuất:

```text
WAQI / API Ninjas
        ↓ mỗi giờ
Supabase Cron → Edge Function
        ├── Supabase Storage: immutable raw JSON
        └── PostgreSQL: validated operational snapshots
                         ↓ Web App

Supabase Storage
        ↓ daily incremental sync + checksum + checkpoint
MinIO Bronze
        ↓ Spark ETL
Silver → Gold
```

Supabase PostgreSQL không cần mô phỏng mô hình Bronze–Silver–Gold. Các bảng
PostgreSQL nên tối ưu cho việc thu thập, kiểm soát trạng thái và dashboard.

## 2. Các bảng PostgreSQL đề xuất

Thiết kế gồm năm bảng chính:

```text
collection_runs
├── waqi_stations
├── waqi_snapshots
├── api_ninjas_locations
└── api_ninjas_snapshots
```

Hai view phục vụ dashboard:

```text
latest_waqi_by_station
latest_api_ninjas_by_province
```

### 2.1 `collection_runs`

Mỗi lần collector chạy cho một nguồn tạo một run riêng. Retry tạo attempt mới
nhưng giữ nguyên `source` và `scheduled_hour_utc`.

```sql
create table public.collection_runs (
    run_id uuid primary key default gen_random_uuid(),

    source text not null
        check (source in ('waqi', 'api_ninjas')),

    scheduled_hour_utc timestamptz not null,
    attempt_number smallint not null default 1
        check (attempt_number > 0),

    started_at_utc timestamptz not null default now(),
    finished_at_utc timestamptz,

    status text not null default 'running'
        check (status in ('running', 'succeeded', 'partial', 'failed')),

    expected_records integer,
    successful_records integer not null default 0,
    failed_records integer not null default 0,
    error_message text,

    unique (source, scheduled_hour_utc, attempt_number)
);

create index collection_runs_source_hour_idx
    on public.collection_runs (source, scheduled_hour_utc desc);
```

Ba timestamp có ý nghĩa khác nhau:

| Timestamp | Ý nghĩa |
| --- | --- |
| `scheduled_hour_utc` | Giờ logic mà collector được lên lịch chạy |
| `collected_at_utc` | Thời điểm hệ thống thực sự nhận API response |
| `waqi_time` | Thời điểm trạm WAQI thực sự quan trắc |

Ví dụ:

```text
scheduled_hour_utc = 2026-10-21 13:00:00+00
collected_at_utc   = 2026-10-21 13:05:00+00
waqi_time          = 2026-10-21 11:00:00+00
```

Dashboard không được dùng `collected_at_utc` để mô tả dữ liệu WAQI là quan
trắc mới nhất. Nên hiển thị cả thời điểm quan trắc và độ trễ dữ liệu.

### 2.2 `waqi_stations`

```sql
create table public.waqi_stations (
    station_id uuid primary key default gen_random_uuid(),
    source_uid text not null unique,

    station_name text not null,
    latitude double precision,
    longitude double precision,
    source_timezone text,

    is_active boolean not null default true,
    first_seen_at_utc timestamptz not null default now(),
    last_seen_at_utc timestamptz not null default now(),

    constraint waqi_station_latitude_check
        check (latitude is null or latitude between -90 and 90),

    constraint waqi_station_longitude_check
        check (longitude is null or longitude between -180 and 180)
);
```

`source_uid` dùng kiểu `text` vì WAQI có thể cung cấp ID âm hoặc thay đổi cách
biểu diễn ID trong tương lai.

### 2.3 `waqi_snapshots`

Supabase giữ mỗi lần thu thập, kể cả khi nhiều lần thu thập nhận cùng một
`waqi_time`. Việc deduplicate observation theo `waqi_time` diễn ra ở Silver.

```sql
create table public.waqi_snapshots (
    snapshot_id bigint generated always as identity primary key,

    collection_run_id uuid not null
        references public.collection_runs(run_id),

    station_id uuid not null
        references public.waqi_stations(station_id),

    snapshot_hour_utc timestamptz not null,
    waqi_time timestamptz,
    waqi_timezone text,
    collected_at_utc timestamptz not null,

    overall_aqi integer,
    dominant_pollutant text,

    pm25 double precision,
    pm10 double precision,
    o3 double precision,
    no2 double precision,
    so2 double precision,
    co double precision,

    temperature double precision,
    humidity double precision,
    pressure double precision,
    wind_speed double precision,
    wind_direction double precision,

    raw_object_path text not null,
    payload_sha256 char(64) not null,

    validation_status text not null default 'valid'
        check (validation_status in ('valid', 'partial', 'invalid')),

    validation_errors jsonb,
    created_at_utc timestamptz not null default now(),

    unique (collection_run_id, station_id)
);

create index waqi_snapshots_station_collected_idx
    on public.waqi_snapshots (station_id, collected_at_utc desc);

create index waqi_snapshots_waqi_time_idx
    on public.waqi_snapshots (station_id, waqi_time desc);

create index waqi_latest_idx
    on public.waqi_snapshots (
        station_id,
        snapshot_hour_utc desc,
        collected_at_utc desc,
        snapshot_id desc
    )
    where validation_status <> 'invalid';
```

`snapshot_hour_utc` phải lấy từ
`collection_runs.scheduled_hour_utc`, không truncate riêng
`collected_at_utc` của từng trạm. Nhờ đó, một run bắt đầu lúc 13:59 và kết thúc
lúc 14:01 vẫn thuộc cùng một snapshot logic.

### 2.4 `api_ninjas_locations`

Một location là tọa độ của `query_city` được sử dụng làm đại diện cho tỉnh.
Đây không phải giá trị trung bình không gian trên toàn tỉnh.

```sql
create table public.api_ninjas_locations (
    location_id uuid primary key default gen_random_uuid(),

    location_key text not null unique,
    province_name text not null,
    province_code text,
    query_city text not null,
    country_name text not null default 'Vietnam',

    latitude double precision not null
        check (latitude between -90 and 90),

    longitude double precision not null
        check (longitude between -180 and 180),

    spatial_representation text not null default 'city_proxy'
        check (spatial_representation = 'city_proxy'),

    is_active boolean not null default true,
    created_at_utc timestamptz not null default now(),
    updated_at_utc timestamptz not null default now()
);
```

`location_key` là khóa ổn định do hệ thống cấu hình, ví dụ `ha-noi` hoặc
`tp-ho-chi-minh`. Không dùng tên hiển thị làm primary key.

### 2.5 `api_ninjas_snapshots`

```sql
create table public.api_ninjas_snapshots (
    snapshot_id bigint generated always as identity primary key,

    collection_run_id uuid not null
        references public.collection_runs(run_id),

    location_id uuid not null
        references public.api_ninjas_locations(location_id),

    snapshot_hour_utc timestamptz not null,
    collected_at_utc timestamptz not null,

    overall_aqi integer,

    co_concentration double precision,
    co_aqi integer,
    no2_concentration double precision,
    no2_aqi integer,
    o3_concentration double precision,
    o3_aqi integer,
    so2_concentration double precision,
    so2_aqi integer,
    pm25_concentration double precision,
    pm25_aqi integer,
    pm10_concentration double precision,
    pm10_aqi integer,

    raw_object_path text not null,
    payload_sha256 char(64) not null,

    validation_status text not null default 'valid'
        check (validation_status in ('valid', 'partial', 'invalid')),

    validation_errors jsonb,
    created_at_utc timestamptz not null default now(),

    unique (collection_run_id, location_id),

    check (co_concentration is null or co_concentration >= 0),
    check (no2_concentration is null or no2_concentration >= 0),
    check (o3_concentration is null or o3_concentration >= 0),
    check (so2_concentration is null or so2_concentration >= 0),
    check (pm25_concentration is null or pm25_concentration >= 0),
    check (pm10_concentration is null or pm10_concentration >= 0)
);

create index api_ninjas_latest_idx
    on public.api_ninjas_snapshots (
        location_id,
        snapshot_hour_utc desc,
        collected_at_utc desc,
        snapshot_id desc
    )
    where validation_status <> 'invalid';
```

`snapshot_hour_utc` cũng phải được sao chép từ
`collection_runs.scheduled_hour_utc`.

## 3. View phục vụ dashboard

View phải loại bỏ run `running` và `failed`, ưu tiên giờ lịch chạy, attempt mới
nhất, thời điểm thu thập và cuối cùng là `snapshot_id` để kết quả luôn xác định.

### 3.1 WAQI mới nhất theo trạm

```sql
create view public.latest_waqi_by_station
with (security_invoker = true)
as
select distinct on (o.station_id)
    o.snapshot_id,
    o.station_id,
    s.source_uid,
    s.station_name,
    s.latitude,
    s.longitude,
    o.snapshot_hour_utc,
    o.waqi_time,
    o.collected_at_utc,
    o.overall_aqi,
    o.dominant_pollutant,
    o.pm25,
    o.pm10,
    o.o3,
    o.no2,
    o.so2,
    o.co,
    r.status as collection_status
from public.waqi_snapshots o
join public.waqi_stations s
  on s.station_id = o.station_id
join public.collection_runs r
  on r.run_id = o.collection_run_id
where r.status in ('succeeded', 'partial')
  and o.validation_status <> 'invalid'
order by
    o.station_id,
    r.scheduled_hour_utc desc,
    r.attempt_number desc,
    o.collected_at_utc desc,
    o.snapshot_id desc;
```

Nếu dashboard cần observation mới nhất thay vì collection snapshot mới nhất,
tạo thêm `latest_waqi_observed` và ưu tiên:

```sql
order by
    o.station_id,
    o.waqi_time desc nulls last,
    o.collected_at_utc desc,
    o.snapshot_id desc;
```

### 3.2 API Ninjas mới nhất theo tỉnh

```sql
create view public.latest_api_ninjas_by_province
with (security_invoker = true)
as
select distinct on (o.location_id)
    o.snapshot_id,
    o.location_id,
    l.location_key,
    l.province_name,
    l.query_city,
    l.latitude,
    l.longitude,
    o.snapshot_hour_utc,
    o.collected_at_utc,
    o.overall_aqi,
    o.co_concentration,
    o.co_aqi,
    o.no2_concentration,
    o.no2_aqi,
    o.o3_concentration,
    o.o3_aqi,
    o.so2_concentration,
    o.so2_aqi,
    o.pm25_concentration,
    o.pm25_aqi,
    o.pm10_concentration,
    o.pm10_aqi,
    r.status as collection_status
from public.api_ninjas_snapshots o
join public.api_ninjas_locations l
  on l.location_id = o.location_id
join public.collection_runs r
  on r.run_id = o.collection_run_id
where r.status in ('succeeded', 'partial')
  and o.validation_status <> 'invalid'
order by
    o.location_id,
    r.scheduled_hour_utc desc,
    r.attempt_number desc,
    o.collected_at_utc desc,
    o.snapshot_id desc;
```

### 3.3 Quy tắc dùng run `partial`

- Trang chi tiết một trạm/tỉnh có thể sử dụng record hợp lệ thuộc run
  `partial`.
- Bản đồ so sánh toàn quốc nên ưu tiên run `succeeded`.
- Nếu bản đồ sử dụng run `partial`, UI phải hiển thị coverage, ví dụ `29/34
  tỉnh`, và không được im lặng trộn dữ liệu từ nhiều giờ mà không thông báo.

## 4. Row Level Security

Các bảng trong exposed schema phải bật RLS:

```sql
alter table public.collection_runs enable row level security;
alter table public.waqi_stations enable row level security;
alter table public.waqi_snapshots enable row level security;
alter table public.api_ninjas_locations enable row level security;
alter table public.api_ninjas_snapshots enable row level security;
```

Nguyên tắc phân quyền:

- Web App chỉ được `SELECT` dữ liệu dashboard được phép công bố.
- Browser không được `INSERT`, `UPDATE` hoặc `DELETE` collection history.
- Edge Function dùng secret credential phía server để ghi dữ liệu.
- Secret credential không xuất hiện trong frontend hoặc source control.
- View dùng `security_invoker = true` nếu cần áp dụng RLS của bảng nguồn.
- Chỉ cấp đúng `GRANT` cần thiết; RLS không thay thế cho table grants.

Tài liệu tham khảo:

- [Supabase Row Level Security](https://supabase.com/docs/guides/database/postgres/row-level-security)
- [Supabase Views](https://supabase.com/docs/guides/database/views)
- [Supabase API keys](https://supabase.com/docs/guides/getting-started/api-keys)

## 5. Supabase Storage

Raw bucket phải là private và raw objects phải bất biến:

```text
raw-api/
├── waqi/
│   └── 2026/10/21/13/<run-id>/<station-uid>.json
└── api_ninjas/
    └── 2026/10/21/13/<run-id>/<location-key>.json
```

Retry sử dụng `run-id` mới và không ghi đè object cũ. PostgreSQL chỉ lưu
`raw_object_path` và checksum tương ứng.

Không sửa trực tiếp các bảng trong schema `storage`; upload, download, move và
delete object phải thực hiện qua Storage API.

Tài liệu tham khảo:

- [Supabase Storage buckets](https://supabase.com/docs/guides/storage/buckets/fundamentals)
- [Supabase Storage access control](https://supabase.com/docs/guides/storage/security/access-control)
- [Supabase Storage schema](https://supabase.com/docs/guides/storage/schema/design)

## 6. Daily Sync xuống Bronze

Daily Sync lấy immutable raw objects từ Supabase Storage, không lấy
PostgreSQL processed snapshots làm nguồn gốc duy nhất.

Trình tự:

1. Chọn các `collection_runs` có trạng thái `succeeded` hoặc `partial` trong
   cửa sổ chưa đồng bộ.
2. Liệt kê raw objects thuộc từng run.
3. Tải raw objects vào staging.
4. Kiểm tra kích thước và SHA-256.
5. Ghi một MinIO Bronze batch bất biến.
6. Ghi `_file_metadata`.
7. Ghi `_ingestion_manifest/_SUCCESS` sau cùng.
8. Chỉ cập nhật checkpoint sau khi Bronze `_SUCCESS` tồn tại.

Checkpoint tối thiểu:

```text
source
window_start_utc
window_end_utc
last_completed_run_id
last_scheduled_hour_utc
bronze_batch_id
object_count
input_fingerprint
completed_at_utc
```

Không dùng duy nhất cột boolean `synced_to_bronze`. Checkpoint theo cửa sổ,
run, batch ID và fingerprint cho phép retry an toàn, phát hiện thiếu object và
tránh tạo duplicate logic.

Có thể lưu checkpoint ở local lakehouse. Nếu cần quan sát trạng thái sync từ
Supabase, có thể bổ sung bảng tùy chọn:

```sql
create table public.lakehouse_sync_runs (
    sync_id uuid primary key default gen_random_uuid(),
    source text not null,
    window_start_utc timestamptz not null,
    window_end_utc timestamptz not null,
    bronze_batch_id text not null,
    object_count integer,
    input_fingerprint char(64),
    status text not null
        check (status in ('running', 'succeeded', 'failed')),
    started_at_utc timestamptz not null default now(),
    completed_at_utc timestamptz,
    error_message text
);
```

## 7. Ánh xạ sang Lakehouse

| Supabase | Bronze/Silver |
| --- | --- |
| Storage `raw-api/waqi/...` | `bronze/waqi/live/...` |
| Storage `raw-api/api_ninjas/...` | `bronze/api_ninjas/province_air_quality/...` |
| `collection_runs.run_id` | Metadata nguồn và `source_collection_run_id` |
| `scheduled_hour_utc` | `snapshot_hour_utc` của API Ninjas |
| `waqi_time` | `waqi_hourly_observation.observation_time_utc` |
| `collected_at_utc` | Thời điểm collector nhận response |
| `raw_object_path`, SHA-256 | Bronze file lineage |

WAQI Silver deduplicate theo thời điểm quan trắc của nguồn. API Ninjas Silver
giữ một city-proxy snapshot cho mỗi `location_id` và `snapshot_hour_utc`.

## 8. Quyết định thiết kế

1. Supabase giữ collection snapshots; Silver giữ logical observations.
2. `scheduled_hour_utc`, `collected_at_utc` và `waqi_time` không được trộn lẫn.
3. Giờ snapshot lấy từ collection run, không truncate độc lập từng response.
4. Dashboard không đọc run `running` hoặc `failed`.
5. Run `partial` phải có chính sách hiển thị coverage rõ ràng.
6. Latest views phải có thứ tự deterministic.
7. Raw Storage là private, immutable và là nguồn cho Bronze.
8. Daily Sync chỉ hoàn tất checkpoint sau Bronze `_SUCCESS`.
9. Edge Function là writer; browser là read-only consumer.
10. Gold mới là nơi xây dựng fact/dimension phục vụ phân tích hợp nhất nguồn.


---


# PHỤ LỤC 2 — SQL seed danh mục 34 tỉnh/thành và 31 trạm WAQI

Hai câu lệnh dưới đây có thể chạy lại vì dùng `ON CONFLICT`. Chỉ nhập metadata danh mục, không nhập AQI lịch sử vào bảng danh mục.

## 2.1. API Ninjas — 34 city proxy locations

```sql
INSERT INTO public.api_ninjas_locations
(location_key,province_name,query_city,country_name,latitude,longitude,spatial_representation,is_active)
VALUES
  ('ha-noi','Hà Nội','Hanoi','Vietnam',21.0285,105.8542,'city_proxy',true),
  ('cao-bang','Cao Bằng','Cao Bang','Vietnam',22.6666,106.2639,'city_proxy',true),
  ('tuyen-quang','Tuyên Quang','Tuyen Quang','Vietnam',21.8236,105.2181,'city_proxy',true),
  ('dien-bien','Điện Biên','Dien Bien Phu','Vietnam',21.386,103.023,'city_proxy',true),
  ('lai-chau','Lai Châu','Lai Chau','Vietnam',22.3964,103.4582,'city_proxy',true),
  ('son-la','Sơn La','Son La','Vietnam',21.327,103.914,'city_proxy',true),
  ('lao-cai','Lào Cai','Lao Cai','Vietnam',22.4856,103.9707,'city_proxy',true),
  ('thai-nguyen','Thái Nguyên','Thai Nguyen','Vietnam',21.5942,105.8482,'city_proxy',true),
  ('lang-son','Lạng Sơn','Lang Son','Vietnam',21.847,106.757,'city_proxy',true),
  ('quang-ninh','Quảng Ninh','Ha Long','Vietnam',20.9517,107.0734,'city_proxy',true),
  ('bac-ninh','Bắc Ninh','Bac Ninh','Vietnam',21.1861,106.0763,'city_proxy',true),
  ('phu-tho','Phú Thọ','Viet Tri','Vietnam',21.3228,105.402,'city_proxy',true),
  ('hai-phong','Hải Phòng','Hai Phong','Vietnam',20.8449,106.6881,'city_proxy',true),
  ('hung-yen','Hưng Yên','Hung Yen','Vietnam',20.6464,106.0511,'city_proxy',true),
  ('ninh-binh','Ninh Bình','Ninh Binh','Vietnam',20.2506,105.9745,'city_proxy',true),
  ('thanh-hoa','Thanh Hóa','Thanh Hoa','Vietnam',19.8067,105.7852,'city_proxy',true),
  ('nghe-an','Nghệ An','Vinh','Vietnam',18.6796,105.6813,'city_proxy',true),
  ('ha-tinh','Hà Tĩnh','Ha Tinh','Vietnam',18.3559,105.8877,'city_proxy',true),
  ('quang-tri','Quảng Trị','Dong Ha','Vietnam',16.8163,107.1003,'city_proxy',true),
  ('hue','Huế','Hue','Vietnam',16.4637,107.5909,'city_proxy',true),
  ('da-nang','Đà Nẵng','Da Nang','Vietnam',16.0544,108.2022,'city_proxy',true),
  ('quang-ngai','Quảng Ngãi','Quang Ngai','Vietnam',15.1214,108.8044,'city_proxy',true),
  ('gia-lai','Gia Lai','Quy Nhon','Vietnam',13.782,109.2197,'city_proxy',true),
  ('khanh-hoa','Khánh Hòa','Nha Trang','Vietnam',12.2388,109.1967,'city_proxy',true),
  ('dak-lak','Đắk Lắk','Buon Ma Thuot','Vietnam',12.6662,108.0382,'city_proxy',true),
  ('lam-dong','Lâm Đồng','Da Lat','Vietnam',11.9404,108.4583,'city_proxy',true),
  ('dong-nai','Đồng Nai','Bien Hoa','Vietnam',10.9574,106.8427,'city_proxy',true),
  ('tp-ho-chi-minh','TP. Hồ Chí Minh','Ho Chi Minh City','Vietnam',10.8231,106.6297,'city_proxy',true),
  ('tay-ninh','Tây Ninh','Tay Ninh','Vietnam',11.31,106.0983,'city_proxy',true),
  ('dong-thap','Đồng Tháp','My Tho','Vietnam',10.36,106.36,'city_proxy',true),
  ('vinh-long','Vĩnh Long','Vinh Long','Vietnam',10.2537,105.9722,'city_proxy',true),
  ('an-giang','An Giang','Rach Gia','Vietnam',10.0125,105.0809,'city_proxy',true),
  ('can-tho','Cần Thơ','Can Tho','Vietnam',10.0452,105.7469,'city_proxy',true),
  ('ca-mau','Cà Mau','Ca Mau','Vietnam',9.1768,105.1524,'city_proxy',true)
ON CONFLICT (location_key) DO UPDATE SET
province_name=EXCLUDED.province_name,
query_city=EXCLUDED.query_city,
country_name=EXCLUDED.country_name,
latitude=EXCLUDED.latitude,
longitude=EXCLUDED.longitude,
spatial_representation=EXCLUDED.spatial_representation,
is_active=EXCLUDED.is_active,
updated_at_utc=now();
```

## 2.2. WAQI — 31 stations

```sql
INSERT INTO public.waqi_stations
(source_uid,station_name,latitude,longitude,source_timezone,is_active)
VALUES
  ('-2186455','Trần Hưng Đạo',11.326741,106.103086,'+07:00',true),
  ('-1791037','Tay Ho Ward',21.07,105.824,'+07:00',true),
  ('-573400','Mo Lao, Ha Dong',20.97775,105.783222,'+07:00',true),
  ('-477553','Vũng Tàu: Đ. Huyền Trân Công Chúa - Phường 8 - TP Vũng Tàu',10.4955,107.2745,'+07:00',true),
  ('-477292','Hà Nội: Công viên Nhân Chính - Khuất Duy Tiến (KK)',21.0031,105.7947,'+07:00',true),
  ('-476842','Thái Bình: Cầu Thái Bình - Đ. Trần Thái Tông - P. Bồ Xuyên - TP Thái Bình (KK)',20.4578,106.3439,'+07:00',true),
  ('-476452','Lâm Đồng: Vườn hoa - đối diện THCS Lam Sơn - Phường 6 - TP Đà Lạt (KK)',11.9527,108.4298,'+07:00',true),
  ('-476341','Hà Nội: ĐHBK cổng Parabol đường Giải Phóng (KK)',21.0052,105.8418,'+07:00',true),
  ('-476317','Quảng Ngãi: UBND P. Nguyễn Nghiêm - TP Quảng Ngãi (KK)',15.121,108.8041,'+07:00',true),
  ('-476308','Quảng Nam: Tiếp giáp Đ. Hùng Vương - KDC Đ. Hồ Xuân Hương (KK)',15.5621,108.4867,'+07:00',true),
  ('-476293','Bắc Giang: Khu liên cơ quan tỉnh Bắc Giang - P. Ngô Quyền - TP. Bắc Giang (KK)',21.301503,106.22603,'+07:00',true),
  ('-476272','Long An: UBND Tp Tân An - 76 Hùng Vương - P.2 (KK)',10.5391,106.4045,'+07:00',true),
  ('-476188','Hà Nam: Công Viên Nam Cao - P.Quang Trung - TP. Phủ Lý (KK)',20.536,105.9165,'+07:00',true),
  ('-476182','HCM: Khu Liên cơ quan Bộ Tài Nguyên và Môi Trường - số 20 Đ. Lý Chính Thắng (KK)',10.7823,106.6834,'+07:00',true),
  ('-476167','HCM: Đ. Lê Hữu Kiều - P. Bình Trưng Tây - Quận 2 (Ngã ba Lê Hữu Kiểu và Trương Văn Bang) (KK)',10.7832,106.7528,'+07:00',true),
  ('-476158','Hưng Yên: số 437 Nguyễn Văn Linh - Tp Hưng Yên (KK)',20.6618,106.0585,'+07:00',true),
  ('-476155','Đà Nẵng: Khuôn viên trường ĐH sư phạm Đà Nẵng (KK)',16.0622,108.1594,'+07:00',true),
  ('-476137','Bình Dương: số 593 Đại lộ Bình Dương, P. Hiệp Thành (KK)',10.9923,106.6577,'+07:00',true),
  ('-112819','Phố Nguyễn Duy Trinh',20.964,105.83,'+07:00',true),
  ('-102721','đường Ngô Quang Thắm',10.658,106.724,'+07:00',true),
  ('1583','Hanoi, Vietnam (Hà Nội)',21.0491,105.8831,'+07:00',true),
  ('1584','Da Nang, Vietnam (TP Đà Nẵng)',16.074,108.217,'+07:00',true),
  ('5506','Viet Tri, Vietnam (Tp Việt Trì)',21.33847,105.3673,'+07:00',true),
  ('8641','Hanoi US Embassy, Vietnam (Đại sứ quán Mỹ, Hà Nội)',21.0215063,105.8188748,'+07:00',true),
  ('8688','United Nations International School of Hanoi, Vietnam (Trường Quốc tế Liên Hợp Quốc Hà Nội)',21.0811211,105.8180306,'+07:00',true),
  ('12488','Thừa Thiên Huế/83 Hùng Vương, Vietnam',16.46226,107.596351,'+07:00',true),
  ('13026','Hà Nội/Chi cục BVMT, Vietnam',21.01525,105.80013,'+07:00',true),
  ('13251','Hà Nội/UBND P. Minh Khai, Bắc Từ Liêm, Vietnam',21.04975,105.74187,'+07:00',true),
  ('13444','Quảng Ninh/K11 - Minh Thành, Vietnam',21.006153,106.859097,'+07:00',true),
  ('13446','Quảng Ninh/Trung tâm văn hóa thể thao Cẩm Phả, Vietnam',21.009332,107.27356,'+07:00',true),
  ('14925','Hà Tĩnh/Trạm Kỳ Phương, Vietnam',18.0145193,106.3990682,'+07:00',true)
ON CONFLICT (source_uid) DO UPDATE SET
station_name=EXCLUDED.station_name,
latitude=EXCLUDED.latitude,
longitude=EXCLUDED.longitude,
source_timezone=EXCLUDED.source_timezone,
is_active=EXCLUDED.is_active,
last_seen_at_utc=now();
```

## 2.3. Kiểm tra seed

```sql
SELECT COUNT(*) AS active_locations FROM public.api_ninjas_locations WHERE is_active;
SELECT COUNT(*) AS active_stations FROM public.waqi_stations WHERE is_active;
```

---

# PHỤ LỤC 3 — Mã Edge Function `collect-waqi` (nguyên văn bản TypeScript)

Dán nguyên block này vào `index.ts` trên Supabase Edge Functions Editor. Nếu production trên Dashboard đã có bản khác, ưu tiên xuất bản deployed và đối chiếu trước khi thay thế.

```typescript
import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { withSupabase } from "jsr:@supabase/server@^1";

const BUCKET = "raw-api";
const SOURCE = "waqi";
const CONCURRENCY = 4;
const API_TIMEOUT_MS = 12000;
const RUN_BUDGET_MS = 105000;
const UID_RE = /^-?\d+$/;

type Station = { station_id: string; source_uid: string };
type AnyRecord = Record<string, unknown>;
type Validation = "valid" | "partial" | "invalid";
type ManifestRecord = Record<string, unknown>;

const record = (x: unknown): AnyRecord | null =>
  x !== null && typeof x === "object" && !Array.isArray(x) ? x as AnyRecord : null;

function scheduledHour(value: unknown): string {
  if (value === undefined || value === null) {
    const d = new Date(); d.setUTCMinutes(0, 0, 0); return d.toISOString();
  }
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}T\d{2}:00:00(?:\.000)?Z$/.test(value)) {
    throw new Error("scheduled_hour_utc must be an exact UTC hour");
  }
  const d = new Date(value);
  if (Number.isNaN(d.getTime()) || d.toISOString() !== value.replace(/Z$/, value.includes(".") ? "Z" : ".000Z")) {
    throw new Error("Invalid scheduled_hour_utc");
  }
  const delta = Date.now() - d.getTime();
  if (delta < 0 || delta > 7 * 86400000) throw new Error("scheduled_hour_utc outside allowed range");
  return d.toISOString();
}

function prefixFor(hour: string, runId: string) {
  const d = new Date(hour);
  const p = [d.getUTCFullYear(), String(d.getUTCMonth()+1).padStart(2,"0"),
    String(d.getUTCDate()).padStart(2,"0"), String(d.getUTCHours()).padStart(2,"0")];
  return `waqi/${p.join("/")}/${runId}`;
}

async function sha256(bytes: Uint8Array) {
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest), b => b.toString(16).padStart(2, "0")).join("");
}

function parseAqi(v: unknown): number | null {
  if (typeof v === "number") return Number.isSafeInteger(v) && v >= 0 ? v : null;
  if (typeof v === "string" && /^\d+$/.test(v.trim())) {
    const n = Number(v.trim()); return Number.isSafeInteger(n) ? n : null;
  }
  return null;
}

function validateWaqi(payload: unknown, requestedUid: string) {
  const errors: Record<string,string> = {};
  const root = record(payload);
  const data = record(root?.data);
  if (root?.status !== "ok" || !data) {
    return { status: "invalid" as Validation, errors: { payload: "waqi_error_or_invalid_data" }, values: null, stationUpdate: null, returnedIdx: null };
  }
  const aqi = parseAqi(data.aqi);
  if (aqi === null) errors.overall_aqi = "missing_or_invalid";
  const t = record(data.time);
  let observation: string | null = null;
  if (typeof t?.iso === "string") {
    const ms = Date.parse(t.iso);
    if (Number.isFinite(ms)) observation = new Date(ms).toISOString();
  }
  if (observation === null) errors.waqi_time = "missing_or_invalid";
  const iaqi = record(data.iaqi);
  const measure = (srcKey: string, destKey: string, min: number, max: number, required = false): number | null => {
    const item = record(iaqi?.[srcKey]);
    const v = item?.v;
    if (v === undefined || v === null) {
      if (required) errors[destKey] = "missing";
      return null;
    }
    if (typeof v !== "number" || !Number.isFinite(v)) { errors[destKey] = "not_a_number"; return null; }
    if (v < min || v > max) { errors[destKey] = "out_of_range"; return null; }
    return v;
  };
  const returnedIdx = parseAqi(data.idx);
  if (returnedIdx !== null && String(returnedIdx) !== requestedUid) {
    errors.source_uid = `requested_${requestedUid}_returned_${returnedIdx}`;
  }
  const city = record(data.city);
  const coords = Array.isArray(city?.geo) ? city.geo : null;
  let lat: number | null = null, lon: number | null = null;
  if (coords && coords.length >= 2 && typeof coords[0] === "number" && typeof coords[1] === "number" &&
      Number.isFinite(coords[0]) && Number.isFinite(coords[1]) && Math.abs(coords[0]) <= 90 && Math.abs(coords[1]) <= 180) {
    lat = coords[0]; lon = coords[1];
  } else if (coords) errors.city_geo = "invalid_coordinates";

  const values = {
    overall_aqi: aqi,
    waqi_time: observation,
    waqi_timezone: typeof t?.tz === "string" ? t.tz : null,
    dominant_pollutant: typeof data.dominentpol === "string" ? data.dominentpol : null,
    pm25: measure("pm25","pm25",0,10000),
    pm10: measure("pm10","pm10",0,10000),
    o3: measure("o3","o3",0,10000),
    no2: measure("no2","no2",0,10000),
    so2: measure("so2","so2",0,10000),
    co: measure("co","co",0,10000),
    temperature: measure("t","temperature",-100,80),
    humidity: measure("h","humidity",0,100),
    pressure: measure("p","pressure",0.000001,2000),
    wind_speed: measure("w","wind_speed",0,1000),
    wind_direction: measure("wd","wind_direction",0,360),
  };
  const status: Validation = aqi === null || observation === null ? "invalid" :
    Object.keys(errors).length > 0 ? "partial" : "valid";
  const stationUpdate: AnyRecord = { last_seen_at_utc: new Date().toISOString() };
  if (typeof city?.name === "string" && city.name.trim()) stationUpdate.station_name = city.name;
  if (lat !== null && lon !== null) { stationUpdate.latitude = lat; stationUpdate.longitude = lon; }
  if (typeof t?.tz === "string" && t.tz.trim()) stationUpdate.source_timezone = t.tz;
  return { status, errors, values, stationUpdate, returnedIdx };
}

export default {
  fetch: withSupabase({ auth: "secret" }, async (req, ctx) => {
    const db = ctx.supabaseAdmin;
    const token = Deno.env.get("WAQI_API_TOKEN");
    if (!token) return Response.json({ error: "Missing WAQI_API_TOKEN" }, { status: 500 });
    let hour: string;
    try {
      const body = await req.json().catch(() => ({}));
      hour = scheduledHour(record(body)?.scheduled_hour_utc);
    } catch (e) { return Response.json({ error: String(e) }, { status: 400 }); }

    const { data: stations, error: targetError } = await db.from("waqi_stations")
      .select("station_id,source_uid").eq("is_active",true).order("source_uid");
    if (targetError) return Response.json({ error: targetError.message }, { status: 500 });
    if (!stations?.length) return Response.json({ error: "No active stations" }, { status: 400 });

    const { data: claims, error: claimError } = await db.rpc("claim_collection_run", {
      p_source: SOURCE, p_scheduled_hour_utc: hour, p_expected_records: stations.length,
    });
    if (claimError || !claims?.length) return Response.json({ error: claimError?.message ?? "Claim failed" }, { status: 500 });
    const claim = claims[0];
    if (!claim.claimed) return Response.json({ skipped: true, reason: claim.reason, run_id: claim.claimed_run_id });
    const runId = claim.claimed_run_id as string;
    const prefix = prefixFor(hour,runId);
    const deadline = Date.now() + RUN_BUDGET_MS;
    const records: ManifestRecord[] = [];
    let cursor = 0, successful = 0, failed = 0;

    async function processStation(station: Station) {
      const entry: ManifestRecord = {
        station_id: station.station_id, requested_source_uid: station.source_uid,
        requested_at_utc: new Date().toISOString(), outcome: "pending",
      };
      try {
        if (!UID_RE.test(station.source_uid)) throw new Error("Invalid source_uid for path/API");
        const url = new URL(`https://api.waqi.info/feed/@${station.source_uid}/`);
        url.searchParams.set("token", token);
        const resp = await fetch(url, { signal: AbortSignal.timeout(API_TIMEOUT_MS) });
        const rawText = await resp.text();
        const receivedAt = new Date().toISOString();
        const bytes = new TextEncoder().encode(rawText);
        const rawHash = await sha256(bytes);
        const path = `${prefix}/${station.source_uid}.raw.json`;
        entry.http_status = resp.status;
        entry.collected_at_utc = receivedAt;
        entry.raw_object_path = path;
        entry.payload_sha256 = rawHash;
        const { error: uploadError } = await db.storage.from(BUCKET).upload(path, bytes, {
          contentType: "application/json", upsert: false,
        });
        if (uploadError) throw uploadError;
        entry.raw_stored = true;
        if (!resp.ok) throw new Error(`WAQI HTTP ${resp.status}`);
        let payload: unknown;
        try { payload = JSON.parse(rawText); }
        catch { throw new Error("Malformed JSON"); }
        const result = validateWaqi(payload, station.source_uid);
        entry.returned_idx = result.returnedIdx;
        entry.validation_status = result.status;
        entry.validation_errors = result.errors;
        if (!result.values) throw new Error("WAQI response was not status=ok with data");
        const { error: snapshotError } = await db.from("waqi_snapshots").insert({
          collection_run_id: runId, station_id: station.station_id,
          snapshot_hour_utc: hour, collected_at_utc: receivedAt,
          ...result.values,
          raw_object_path: path, payload_sha256: rawHash,
          validation_status: result.status,
          validation_errors: Object.keys(result.errors).length ? result.errors : null,
        });
        if (snapshotError) throw snapshotError;
        entry.snapshot_stored = true;
        if (result.stationUpdate) {
          const { error: updateError } = await db.from("waqi_stations")
            .update(result.stationUpdate).eq("station_id", station.station_id);
          if (updateError) {
            entry.metadata_warning = updateError.message;
            console.warn("Station metadata update failed", station.source_uid, updateError.message);
          }
        }
        entry.outcome = result.status;
        if (result.status === "invalid") failed++; else successful++;
      } catch (e) {
        entry.outcome = "failed";
        entry.error = String(e);
        failed++;
        console.error("Station error", station.source_uid, String(e));
      } finally { records.push(entry); }
    }

    async function worker() {
      while (true) {
        if (Date.now() + API_TIMEOUT_MS + 3000 >= deadline) return;
        const idx = cursor++;
        if (idx >= stations.length) return;
        await processStation(stations[idx] as Station);
      }
    }

    try {
      await Promise.all(Array.from({ length: Math.min(CONCURRENCY, stations.length) }, () => worker()));
      const seen = new Set(records.map((r) => r.station_id));
      for (const station of stations as Station[]) {
        if (!seen.has(station.station_id)) {
          failed++;
          records.push({ station_id: station.station_id, requested_source_uid: station.source_uid,
            outcome: "not_attempted", error: "Time budget exhausted" });
        }
      }
      const status = failed === 0 ? "succeeded" : successful === 0 ? "failed" : "partial";
      const manifest = {
        schema_version: 1, source: SOURCE, collection_run_id: runId,
        scheduled_hour_utc: hour, attempt_number: claim.claimed_attempt,
        expected_records: stations.length, successful_records: successful, failed_records: failed,
        status, completed_at_utc: new Date().toISOString(),
        records: records.sort((a,b) => String(a.requested_source_uid).localeCompare(String(b.requested_source_uid))),
      };
      const manifestPath = `${prefix}/manifest.json`;
      const manifestBytes = new TextEncoder().encode(JSON.stringify(manifest));
      const manifestHash = await sha256(manifestBytes);
      const { error: manifestError } = await db.storage.from(BUCKET).upload(manifestPath, manifestBytes, {
        contentType: "application/json", upsert: false,
      });
      if (manifestError) throw manifestError;
      const { data: finalized, error: finishError } = await db.from("collection_runs")
        .update({ status, successful_records: successful, failed_records: failed,
          manifest_object_path: manifestPath, manifest_sha256: manifestHash,
          finished_at_utc: new Date().toISOString(),
          error_message: failed ? `${failed} targets failed or incomplete` : null })
        .eq("run_id", runId).eq("status", "running").select("run_id");
      if (finishError) throw finishError;
      if (!finalized?.length) throw new Error("Run was no longer running; finalization rejected");
      return Response.json({ run_id: runId, scheduled_hour_utc: hour, status,
        successful_records: successful, failed_records: failed,
        manifest_path: manifestPath, manifest_sha256: manifestHash });
    } catch (e) {
      console.error("Fatal collect-waqi failure", String(e));
      const { error: finishError } = await db.from("collection_runs").update({
        status: "failed", finished_at_utc: new Date().toISOString(),
        successful_records: successful, failed_records: failed,
        error_message: String(e).slice(0, 10000),
      }).eq("run_id", runId).eq("status", "running");
      if (finishError) console.error("Failed to finalize failed run", finishError.message);
      return Response.json({ run_id: runId, error: String(e) }, { status: 500 });
    }
  }),
};
```

# PHỤ LỤC 4 — Mã Edge Function `collect-api-ninjas` (nguyên văn bản TypeScript)

```typescript
import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { withSupabase } from "jsr:@supabase/server@^1";

const SOURCE = "api_ninjas";
const BUCKET = "raw-api";
const API_URL = "https://api.api-ninjas.com/v1/airquality";
const WORKERS = 4;
const HTTP_TIMEOUT_MS = 12_000;
const RUN_BUDGET_MS = 110_000;

type Location = {
  location_id: string;
  location_key: string;
  province_name: string;
  query_city: string;
  latitude: number;
  longitude: number;
};
type Dict = Record<string, unknown>;
type ValidationStatus = "valid" | "partial" | "invalid";
type ManifestRecord = {
  location_id: string;
  location_key: string;
  province_name: string;
  query_city: string;
  latitude: number;
  longitude: number;
  requested_at_utc?: string;
  collected_at_utc?: string;
  http_status?: number;
  raw_object_path?: string;
  payload_sha256?: string;
  validation_status?: ValidationStatus;
  validation_errors?: Record<string, string>;
  outcome: string;
  error?: string;
};

const POLLUTANTS = [
  ["CO", "co"], ["NO2", "no2"], ["O3", "o3"],
  ["SO2", "so2"], ["PM2.5", "pm25"], ["PM10", "pm10"],
] as const;

function hourFromRequest(value: unknown): string {
  if (value === undefined || value === null) {
    const d = new Date();
    d.setUTCMinutes(0, 0, 0);
    return d.toISOString();
  }
  if (typeof value !== "string" ||
      !/^\d{4}-\d{2}-\d{2}T\d{2}:00:00(?:\.000)?Z$/.test(value)) {
    throw new Error("scheduled_hour_utc must be at an exact UTC hour");
  }
  const d = new Date(value);
  if (!Number.isFinite(d.getTime()) ||
      (d.toISOString() !== value && d.toISOString() !== value.replace("Z", ".000Z"))) {
    throw new Error("Invalid scheduled_hour_utc");
  }
  if (d.getTime() > Date.now() || Date.now() - d.getTime() > 7 * 86400000) {
    throw new Error("scheduled_hour_utc must be in the past 7 days");
  }
  return d.toISOString();
}

function prefixFor(hour: string, runId: string): string {
  const d = new Date(hour);
  const mm = String(d.getUTCMonth() + 1).padStart(2, "0");
  const dd = String(d.getUTCDate()).padStart(2, "0");
  const hh = String(d.getUTCHours()).padStart(2, "0");
  return `api_ninjas/${d.getUTCFullYear()}/${mm}/${dd}/${hh}/${runId}`;
}

function asObject(value: unknown): Dict | null {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? value as Dict : null;
}

function validate(payload: unknown) {
  const values: Record<string, number | null> = {};
  const errors: Record<string, string> = {};
  const obj = asObject(payload);
  const readNumber = (value: unknown, field: string, integer: boolean): number | null => {
    if (value === undefined || value === null) { errors[field] = "missing"; return null; }
    if (typeof value !== "number" || !Number.isFinite(value)) {
      errors[field] = "not_a_number"; return null;
    }
    if (integer && !Number.isInteger(value)) { errors[field] = "not_an_integer"; return null; }
    if (value < 0) { errors[field] = "negative"; return null; }
    return value;
  };
  values.overall_aqi = readNumber(obj?.overall_aqi, "overall_aqi", true);
  for (const [apiName, dbName] of POLLUTANTS) {
    const item = asObject(obj?.[apiName]);
    values[`${dbName}_concentration`] = readNumber(item?.concentration, `${dbName}_concentration`, false);
    values[`${dbName}_aqi`] = readNumber(item?.aqi, `${dbName}_aqi`, true);
  }
  const status: ValidationStatus = values.overall_aqi === null
    ? "invalid" : Object.keys(errors).length ? "partial" : "valid";
  return { values, errors, status };
}

async function sha256(data: Uint8Array): Promise<string> {
  const hash = await crypto.subtle.digest("SHA-256", data);
  return Array.from(new Uint8Array(hash)).map(x => x.toString(16).padStart(2, "0")).join("");
}

export default {
  fetch: withSupabase({ auth: "secret" }, async (req, ctx) => {
    if (req.method !== "POST") return Response.json({ error: "POST required" }, { status: 405 });
    const db = ctx.supabaseAdmin;
    const apiKey = Deno.env.get("API_NINJAS_KEY");
    if (!apiKey) return Response.json({ error: "Missing API_NINJAS_KEY" }, { status: 500 });

    let hour: string;
    try {
      const body = await req.json().catch(() => ({}));
      hour = hourFromRequest(asObject(body)?.scheduled_hour_utc);
    } catch (e) {
      return Response.json({ error: String(e) }, { status: 400 });
    }

    const { data: locations, error: listError } = await db
      .from("api_ninjas_locations")
      .select("location_id,location_key,province_name,query_city,latitude,longitude")
      .eq("is_active", true).order("location_key");
    if (listError || !locations?.length) {
      return Response.json({ error: listError?.message ?? "No active locations" }, { status: 500 });
    }

    const { data: claims, error: claimError } = await db.rpc("claim_collection_run", {
      p_source: SOURCE, p_scheduled_hour_utc: hour, p_expected_records: locations.length,
    });
    if (claimError || !claims?.length) {
      return Response.json({ error: claimError?.message ?? "Cannot claim run" }, { status: 500 });
    }
    const claim = claims[0];
    if (!claim.claimed) {
      return Response.json({ skipped: true, reason: claim.reason, run_id: claim.claimed_run_id });
    }

    const runId: string = claim.claimed_run_id;
    const prefix = prefixFor(hour, runId);
    const deadline = Date.now() + RUN_BUDGET_MS;
    const records: ManifestRecord[] = [];
    let nextIndex = 0;
    let successful = 0;
    let failed = 0;

    async function processLocation(loc: Location): Promise<void> {
      const record: ManifestRecord = {
        location_id: loc.location_id, location_key: loc.location_key,
        province_name: loc.province_name, query_city: loc.query_city,
        latitude: loc.latitude, longitude: loc.longitude, outcome: "failed",
      };
      records.push(record);
      try {
        if (!/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(loc.location_key)) {
          throw new Error("Unsafe location_key");
        }
        const rawPath = `${prefix}/${loc.location_key}.raw.json`;
        const url = new URL(API_URL);
        url.searchParams.set("lat", String(loc.latitude));
        url.searchParams.set("lon", String(loc.longitude));
        record.requested_at_utc = new Date().toISOString();
        const response = await fetch(url, {
          headers: { "X-Api-Key": apiKey },
          signal: AbortSignal.timeout(Math.min(HTTP_TIMEOUT_MS, Math.max(1000, deadline - Date.now()))),
        });
        // Capture provider body even for HTTP failures and malformed JSON.
        const rawText = await response.text();
        record.collected_at_utc = new Date().toISOString();
        record.http_status = response.status;
        const bytes = new TextEncoder().encode(rawText);
        const hash = await sha256(bytes);
        const { error: storageError } = await db.storage.from(BUCKET).upload(rawPath, bytes, {
          contentType: "application/json", upsert: false,
        });
        if (storageError) throw new Error(`Storage: ${storageError.message}`);
        record.raw_object_path = rawPath;
        record.payload_sha256 = hash;
        if (!response.ok) throw new Error(`API Ninjas HTTP ${response.status}`);
        let payload: unknown;
        try { payload = JSON.parse(rawText); }
        catch { throw new Error("Malformed JSON response"); }
        const result = validate(payload);
        record.validation_status = result.status;
        record.validation_errors = result.errors;

        const { error: insertError } = await db.from("api_ninjas_snapshots").insert({
          collection_run_id: runId,
          location_id: loc.location_id,
          snapshot_hour_utc: hour,
          collected_at_utc: record.collected_at_utc,
          ...result.values,
          raw_object_path: rawPath,
          payload_sha256: hash,
          validation_status: result.status,
          validation_errors: Object.keys(result.errors).length ? result.errors : null,
        });
        if (insertError) throw new Error(`Snapshot: ${insertError.message}`);
        record.outcome = result.status;
        if (result.status === "invalid") failed++;
        else successful++;
      } catch (error) {
        if (record.outcome === "failed") failed++;
        record.error = String(error);
        console.error(`${loc.location_key}: ${String(error)}`);
      }
    }

    async function worker() {
      while (true) {
        if (Date.now() + HTTP_TIMEOUT_MS + 3000 >= deadline) return;
        const index = nextIndex++;
        if (index >= locations.length) return;
        await processLocation(locations[index] as Location);
      }
    }

    try {
      await Promise.all(Array.from({ length: Math.min(WORKERS, locations.length) }, () => worker()));
      const completed = new Set(records.map(r => r.location_id));
      for (const loc of locations as Location[]) {
        if (!completed.has(loc.location_id)) {
          failed++;
          records.push({
            location_id: loc.location_id, location_key: loc.location_key,
            province_name: loc.province_name, query_city: loc.query_city,
            latitude: loc.latitude, longitude: loc.longitude,
            outcome: "not_attempted", error: "Run time budget reached",
          });
        }
      }
      const status = failed === 0 ? "succeeded" : successful === 0 ? "failed" : "partial";
      const manifest = {
        schema_version: 1, source: SOURCE, collection_run_id: runId,
        scheduled_hour_utc: hour, attempt_number: claim.claimed_attempt,
        created_at_utc: new Date().toISOString(), status,
        expected_records: locations.length, successful_records: successful, failed_records: failed,
        records: records.sort((a, b) => a.location_key.localeCompare(b.location_key)),
      };
      const manifestPath = `${prefix}/manifest.json`;
      const manifestBytes = new TextEncoder().encode(JSON.stringify(manifest, null, 2));
      const manifestHash = await sha256(manifestBytes);
      const { error: manifestError } = await db.storage.from(BUCKET).upload(manifestPath, manifestBytes, {
        contentType: "application/json", upsert: false,
      });
      if (manifestError) throw new Error(`Manifest: ${manifestError.message}`);
      const { data: finalized, error: finalizeError } = await db.from("collection_runs").update({
        status, successful_records: successful, failed_records: failed,
        finished_at_utc: new Date().toISOString(),
        manifest_object_path: manifestPath, manifest_sha256: manifestHash,
        error_message: failed ? `${failed} location(s) failed or invalid` : null,
      }).eq("run_id", runId).eq("status", "running").select("run_id");
      if (finalizeError || finalized?.length !== 1) {
        throw new Error(`Finalize failed: ${finalizeError?.message ?? "run no longer running"}`);
      }
      return Response.json({
        run_id: runId, source: SOURCE, scheduled_hour_utc: hour, status,
        expected_records: locations.length, successful_records: successful, failed_records: failed,
        manifest_path: manifestPath, manifest_sha256: manifestHash,
      });
    } catch (error) {
      console.error(`Run ${runId}: ${String(error)}`);
      await db.from("collection_runs").update({
        status: "failed", finished_at_utc: new Date().toISOString(),
        successful_records: successful, failed_records: failed,
        error_message: String(error).slice(0, 10000),
      }).eq("run_id", runId).eq("status", "running");
      return Response.json({ run_id: runId, error: String(error) }, { status: 500 });
    }
  }),
};
```

## Tài liệu tham khảo

- https://supabase.com/docs/guides/functions
- https://supabase.com/docs/guides/functions/limits
- https://supabase.com/docs/guides/functions/secrets
- https://supabase.com/docs/guides/cron
- https://supabase.com/docs/guides/database/vault
- https://supabase.com/docs/guides/database/postgres/row-level-security
- https://supabase.com/docs/guides/storage
- https://aqicn.org/json-api/doc/
- https://api-ninjas.com/api/airquality
