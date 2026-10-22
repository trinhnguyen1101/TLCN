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
