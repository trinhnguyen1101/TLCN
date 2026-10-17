"""Read bounded native observations and the monthly overview, never raw GRIB."""
from datetime import datetime, timezone
from collections import OrderedDict
from concurrent.futures import Future
import json
from math import isfinite
from pathlib import Path
import re
from threading import Lock

import pyarrow.parquet as pq
import pyarrow as pa
import pyarrow.compute as pc
from pyarrow import ArrowException

from app.repositories.base import DataSourceUnavailable
from app.services.map_scale import monthly_concentration_scale
from app.schemas.dashboard import DashboardData, DashboardTrendRecord, ProvinceSnapshot
from app.services.temporal import DashboardQuery, InvalidDashboardQuery, utc_bound

SNAPSHOT_METRICS = (
    "pm1", "pm25", "pm10", "no2", "so2", "co", "o3",
    "no2_column", "so2_column", "co_column", "o3_column",
)


def latest_observation(trends):
    return max((row.date for row in trends
                if any(getattr(row, metric) is not None for metric in SNAPSHOT_METRICS)), default=None)


class ParquetDashboardRepository:
    def __init__(self, path: Path):
        self.path = Path(path)
        self._generation = None
        self._cached = None
        self._lock = Lock()
        self._queries = OrderedDict()
        self._query_rows = 0
        self._pending = {}
        self._manifest = None
        self._monthly_loaded = False
        self._max_query_rows = 80_000
        self._max_query_entries = 16

    def get_dashboard(self, query: DashboardQuery | None = None) -> DashboardData:
        # Validate user bounds separately from data-source errors.
        if query and query.start and query.end:
            query.bounds(query.end)
        try:
            with self._lock:
                generation = (self.path / "CURRENT").read_text(encoding="ascii").strip()
                if not re.fullmatch(r"[a-f0-9]{32}", generation):
                    raise ValueError("Invalid generation pointer")
                if self._generation != generation:
                    monthly = query is None or query.resolution == "monthly"
                    data = self._read(self.path / "runs" / generation, include_monthly=monthly)
                    self._manifest = json.loads((self.path / "runs" / generation / "manifest.json").read_text(encoding="utf-8"))
                    self._cached = data
                    self._generation = generation
                    self._monthly_loaded = monthly
                    self._queries.clear()
                    self._query_rows = 0
                elif not self._monthly_loaded and (query is None or query.resolution == "monthly"):
                    self._cached = self._read(self.path / "runs" / generation)
                    self._monthly_loaded = True
                cached = self._cached
                manifest = self._manifest
            if query:
                return self._query_dashboard(cached, manifest, generation, query)
            return self._copy_response(cached)
        except (OSError, ValueError, KeyError, TypeError, ArrowException) as exc:
            raise DataSourceUnavailable("Cannot read EAC4 Parquet generation") from exc

    @staticmethod
    def _copy_response(data):
        # Record fields are immutable scalars, dates and strings. A shallow model
        # copy isolates field assignments without recursively copying every value.
        return data.model_copy(update={
            "province_snapshots": [row.model_copy() for row in data.province_snapshots],
            "emission_records": [row.model_copy() for row in data.emission_records],
            "emission_sectors": list(data.emission_sectors),
            "dashboard_trend_records": [row.model_copy() for row in data.dashboard_trend_records],
            "metadata": data.metadata.model_copy(deep=True),
        })

    def _query_dashboard(self, cached, manifest, generation, query):
        folder = self.path / "runs" / generation
        try:
            if query.resolution == "monthly":
                start = utc_bound(query.start) if query.start else utc_bound(cached.metadata.start)
                end = utc_bound(query.end, end=True) if query.end else utc_bound(cached.metadata.end)
                if start > end:
                    raise ValueError("start must be before or equal to end")
            else:
                start, end = query.bounds(cached.metadata.observation_end or cached.metadata.end)
        except ValueError as exc:
            raise InvalidDashboardQuery(str(exc)) from exc

        # File identities keep local repairs/corruption visible even if CURRENT
        # stays the same. Missing/added partitions also change this key.
        signature = []
        if query.resolution != "monthly":
            for source in manifest["sources"]:
                for year in range(start.year, end.year + 1):
                    for file in sorted((folder / "observations" / source["name"] / str(year)).glob("*.parquet")):
                        stat = file.stat()
                        signature.append((str(file), stat.st_size, stat.st_mtime_ns))
        key = (generation, query.resolution, start, end, tuple(signature))
        with self._lock:
            result = self._queries.get(key)
            if result is not None:
                self._queries.move_to_end(key)
            pending = self._pending.get(key)
            owner = result is None and pending is None
            if owner:
                pending = Future()
                self._pending[key] = pending
        if result is not None:
            return self._copy_response(result)
        if not owner:
            return self._copy_response(pending.result())
        try:
            data = cached.model_copy(update={
                "province_snapshots": [row.model_copy() for row in cached.province_snapshots],
                "dashboard_trend_records": [],
                "metadata": cached.metadata.model_copy(deep=True),
            })
            if query.resolution == "monthly":
                data.dashboard_trend_records = [row for row in cached.dashboard_trend_records
                    if start.date().replace(day=1) <= row.date <= end.date()]
            else:
                data.dashboard_trend_records = self._observations(folder, manifest, start, end, query.resolution, data.metadata.observation_start)
            self._snapshot(data)
            data.metadata.temporal_aggregation = {"3h": "3_hourly", "daily": "daily_mean", "monthly": "monthly_mean"}[query.resolution]
            data.metadata.query_start, data.metadata.query_end = start, end
            data.metadata.note = (
                "Dữ liệu mẫu tạm thời, chưa qua pipeline xử lý và kiểm định chính thức. "
                "CAMS EAC4 theo diện tích từng vùng báo cáo; quan sát gốc cách nhau 3 giờ UTC. "
                "Đất liền và quần đảo tính riêng. Các chỉ số *_column là tổng cột (mg/m²). "
                "Không suy AQI hay ngày vượt ngưỡng từ dữ liệu này."
            )
            with self._lock:
                count = len(data.dashboard_trend_records)
                if generation == self._generation and count <= self._max_query_rows:
                    self._queries[key] = data
                    self._query_rows += count
                    while len(self._queries) > self._max_query_entries or self._query_rows > self._max_query_rows:
                        _, evicted = self._queries.popitem(last=False)
                        self._query_rows -= len(evicted.dashboard_trend_records)
            pending.set_result(data)
            return self._copy_response(data)
        except BaseException as exc:
            pending.set_exception(exc)
            raise
        finally:
            with self._lock:
                self._pending.pop(key, None)

    @staticmethod
    def _snapshot(data):
        trends = data.dashboard_trend_records
        # One shared timestamp across regions; missing rows stay null.
        latest = latest_observation(trends)
        rows = {r.province_code: r for r in trends if r.date == latest}
        for province in data.province_snapshots:
            row = rows.get(province.province_code)
            for metric in SNAPSHOT_METRICS:
                setattr(province, metric, getattr(row, metric) if row else None)
        data.metadata.snapshot_date = latest
        for metric in ("pm1", "pm25", "pm10"):
            if metric in data.metadata.metrics:
                data.metadata.metrics[metric].map_scale = monthly_concentration_scale(
                    [(r.date, getattr(r, metric)) for r in trends])

    @staticmethod
    def _observations(folder, manifest, start, end, resolution, observation_start):
        records = {}
        codes = pa.array([p["code"] for p in manifest["provinces"]])
        for source in manifest["sources"]:
            metric = source["name"]
            tables = []
            for year in range(start.year, end.year + 1):
                partition = folder / "observations" / metric / str(year)
                if not partition.exists():
                    # A compact sample declares its native period explicitly.
                    native_start = utc_bound(observation_start or source["start"])
                    native_end = utc_bound(manifest.get("observation_end", source["end"]))
                    if max(start, native_start, datetime(year, 1, 1, tzinfo=timezone.utc)) <= min(end, native_end, datetime(year, 12, 31, 23, 59, 59, tzinfo=timezone.utc)):
                        raise ValueError(f"Missing observations for {metric}/{year}; rebuild EAC4 sample")
                    continue
                files = sorted(partition.glob("*.parquet"))
                if not files:
                    raise ValueError("Empty observation partition")
                for file in files:
                    table = pq.read_table(file, columns=["timestamp", "province_code", "metric", "value", "unit", "valid_area_fraction", "quality_flag"],
                                          filters=[("timestamp", ">=", start), ("timestamp", "<=", end)])
                    if table.num_rows:
                        ParquetDashboardRepository._validate_observations(table, metric, source["unit"], codes)
                        tables.append(table)
            if not tables:
                continue
            table = pa.concat_tables(tables)
            # Check across files and years before aggregating; duplicate samples
            # must never inflate the daily coverage or average.
            if table.group_by(["province_code", "timestamp"]).aggregate([]).num_rows != table.num_rows:
                raise ValueError("Duplicated observation identity")
            valid = pc.and_(pc.greater_equal(table["valid_area_fraction"], manifest["minimum_coverage"]),
                            pc.equal(table["quality_flag"], "ok"))
            values = pc.if_else(valid, table["value"], None)
            if resolution == "daily":
                daily = pa.table({"province_code": table["province_code"],
                                  # UTC calendar dates need no per-row timezone lookup.
                                  "date": pc.cast(pc.cast(table["timestamp"], pa.timestamp(table["timestamp"].type.unit)), pa.date32()),
                                  "value": values})
                grouped = daily.group_by(["province_code", "date"]).aggregate([("value", "sum"), ("value", "count")])
                for row in grouped.to_pylist():
                    key = (row["province_code"], row["date"])
                    record = records.setdefault(key, dict(province_code=key[0], date=key[1], pm25=None, pm10=None, o3=None, no2=None, so2=None, co=None))
                    record[metric] = row["value_sum"] / row["value_count"] if row["value_count"] >= 6 else None
            else:
                selected = pa.table({"province_code": table["province_code"], "date": table["timestamp"], "value": values})
                for row in selected.to_pylist():
                    key = (row["province_code"], row["date"])
                    record = records.setdefault(key, dict(province_code=key[0], date=key[1], pm25=None, pm10=None, o3=None, no2=None, so2=None, co=None))
                    record[metric] = row["value"]
        return [DashboardTrendRecord(**row) for _, row in sorted(records.items(), key=lambda item: (item[0][1], item[0][0]))]

    @staticmethod
    def _validate_observations(table, metric, unit, codes):
        """Validate columns in Arrow without constructing a Python object per sample."""
        timestamp, coverage, values = table["timestamp"], table["valid_area_fraction"], table["value"]
        if not pa.types.is_timestamp(timestamp.type) or timestamp.type.tz != "UTC":
            raise ValueError("Invalid 3-hour UTC timestamp")
        utc_timestamp = pc.cast(timestamp, pa.timestamp(timestamp.type.unit))
        for column in (coverage, values):
            if not (pa.types.is_floating(column.type) or pa.types.is_integer(column.type)):
                raise ValueError("Invalid observation numeric type")
        checks = [
            pc.equal(utc_timestamp, pc.floor_temporal(utc_timestamp, multiple=3, unit="hour")),
            pc.is_in(table["province_code"], value_set=codes),
            pc.equal(table["metric"], metric),
            pc.equal(table["unit"], unit),
            pc.is_finite(coverage),
            # Equal-area intersection sums have tiny projection roundoff.
            pc.greater_equal(coverage, -1e-7), pc.less_equal(coverage, 1 + 1e-7),
            pc.is_in(table["quality_flag"], value_set=pa.array(["ok", "insufficient_coverage"])),
            pc.or_(pc.is_null(values), pc.fill_null(pc.is_finite(values), False)),
        ]
        if not all(pc.all(pc.fill_null(check, False)).as_py() for check in checks):
            raise ValueError("Invalid observation identity, timestamp, unit, coverage or value")

    def _read(self, folder, include_monthly=True):
        manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
        if manifest["schema_version"] != 1 or manifest["generation"] != folder.name:
            raise ValueError("Unsupported Parquet schema")
        province_codes = {p["code"] for p in manifest["provinces"]}
        if not province_codes or len(province_codes) != len(manifest["provinces"]):
            raise ValueError("Empty or duplicated provinces")
        # A clone can carry only the bundled native years; a local ETL can carry
        # the full source history. Advertise the years physically present.
        native_years = [int(p.name) for p in (folder / "observations").glob("*/*") if p.is_dir() and p.name.isdigit()]
        native_start = manifest.get("observation_start", min(s["start"] for s in manifest["sources"]))
        if native_years:
            native_start = max(native_start, f"{min(native_years)}-01-01T00:00:00+00:00")
        records = {}
        seen = set()
        metric_metadata = {}
        available_years = set()
        for source in manifest["sources"]:
            metric = source["name"]
            if metric not in DashboardTrendRecord.model_fields or metric in {"province_code", "date"}:
                raise ValueError("Invalid metric")
            alias = DashboardTrendRecord.model_fields[metric].alias
            if alias in metric_metadata:
                raise ValueError("Invalid or duplicated metric")
            metric_metadata[alias] = {"unit": source["unit"], "quantity": source["quantity"]}
            if not include_monthly:
                # Native requests only need source metadata, not every value in
                # 23 years of monthly history. Read one compact Arrow column to
                # retain the exact year choices, then lazily load monthly values.
                timestamps = pq.read_table(folder / "monthly" / f"{metric}.parquet", columns=["timestamp"])["timestamp"]
                if not pa.types.is_timestamp(timestamps.type) or timestamps.null_count:
                    raise ValueError("Invalid monthly timestamp")
                available_years.update(pc.unique(pc.year(timestamps)).to_pylist())
                continue
            for row in pq.read_table(folder / "monthly" / f"{metric}.parquet").to_pylist():
                if row["province_code"] not in province_codes or not isinstance(row["timestamp"], datetime):
                    raise ValueError("Invalid monthly province/timestamp")
                coverage = row["temporal_coverage_fraction"]
                if not isinstance(coverage, (int, float)) or not isfinite(coverage) or not 0 <= coverage <= 1:
                    raise ValueError("Invalid monthly coverage")
                if row["value"] is not None and not isfinite(row["value"]):
                    raise ValueError("Invalid monthly value")
                key = (row["province_code"], row["timestamp"].date())
                identity = (*key, metric)
                if identity in seen or row["metric"] != metric or row["unit"] != source["unit"]:
                    raise ValueError("Invalid monthly data identity/unit")
                seen.add(identity)
                record = records.setdefault(key, dict(province_code=key[0], date=key[1],
                                                      pm25=None, pm10=None, o3=None, no2=None, so2=None, co=None))
                # Months with less than 75% valid 3-hourly samples remain unavailable.
                record[metric] = row["value"] if coverage >= 0.75 else None
        trends = [DashboardTrendRecord(**row) for _, row in sorted(records.items())]
        for metric in ("pm1", "pm25", "pm10"):
            if metric in metric_metadata:
                metric_metadata[metric]["map_scale"] = monthly_concentration_scale(
                    [(record.date, getattr(record, metric)) for record in trends]
                )
        latest = latest_observation(trends)
        latest_rows = {r.province_code: r for r in trends if r.date == latest}
        snapshots = []
        for province in manifest["provinces"]:
            record = latest_rows.get(province["code"])
            snapshots.append(ProvinceSnapshot(
                province_code=province["code"], province_name=province["name"],
                **{metric: getattr(record, metric) if record else None for metric in SNAPSHOT_METRICS},
                aqi=None, status=None,
            ))
        return DashboardData(
            province_snapshots=snapshots, emission_records=[], emission_sectors=[],
            dashboard_trend_records=trends,
            metadata={
                "source": "CAMS EAC4 sample", "generation": manifest["generation"],
                "start": min(s["start"] for s in manifest["sources"]),
                "end": max(s["end"] for s in manifest["sources"]),
                "snapshot_date": latest, "metrics": metric_metadata,
                "temporal_aggregation": "monthly_mean", "timezone": "UTC",
                "minimum_spatial_coverage": manifest["minimum_coverage"],
                "minimum_monthly_coverage": 0.75,
                "available_years": sorted({r.date.year for r in trends} if include_monthly else available_years, reverse=True),
                "observation_start": native_start,
                "observation_end": manifest.get("observation_end", max(s["end"] for s in manifest["sources"])),
                "note": "Dữ liệu mẫu tạm thời, chưa qua pipeline xử lý và kiểm định chính thức. "
                        f"Tái phân tích CAMS EAC4, trung bình tháng theo diện tích trên ranh giới {manifest['province_count']} vùng báo cáo; đất liền và quần đảo được tính riêng. "
                        "Các chỉ số *_column là tổng cột khí quyển (mg/m²). "
                        "Không có dữ liệu phát thải theo ngành; không suy AQI từ trung bình tháng.",
            },
        )
