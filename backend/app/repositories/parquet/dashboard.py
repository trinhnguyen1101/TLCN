"""Dashboard adapter reading the small monthly Parquet view, never raw GRIB."""
from datetime import datetime
import json
from math import isfinite
from pathlib import Path
import re
from threading import Lock

import pyarrow.parquet as pq

from app.repositories.base import DataSourceUnavailable
from app.services.map_scale import monthly_concentration_scale
from app.schemas.dashboard import DashboardData, DashboardTrendRecord, ProvinceSnapshot


class ParquetDashboardRepository:
    def __init__(self, path: Path):
        self.path = Path(path)
        self._generation = None
        self._cached = None
        self._lock = Lock()

    def get_dashboard(self) -> DashboardData:
        try:
            with self._lock:
                generation = (self.path / "CURRENT").read_text(encoding="ascii").strip()
                if not re.fullmatch(r"[a-f0-9]{32}", generation):
                    raise ValueError("Invalid generation pointer")
                if self._generation != generation:
                    data = self._read(self.path / "runs" / generation)
                    self._cached = data
                    self._generation = generation
                return self._cached.model_copy(deep=True)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise DataSourceUnavailable("Cannot read EAC4 Parquet generation") from exc

    def _read(self, folder):
        manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
        if manifest["schema_version"] != 1 or manifest["generation"] != folder.name:
            raise ValueError("Unsupported Parquet schema")
        province_codes = {p["code"] for p in manifest["provinces"]}
        if not province_codes or len(province_codes) != len(manifest["provinces"]):
            raise ValueError("Empty or duplicated provinces")
        records = {}
        seen = set()
        metric_metadata = {}
        for source in manifest["sources"]:
            metric = source["name"]
            if metric not in DashboardTrendRecord.model_fields or metric in {"province_code", "date"}:
                raise ValueError("Invalid metric")
            alias = DashboardTrendRecord.model_fields[metric].alias
            if alias in metric_metadata:
                raise ValueError("Invalid or duplicated metric")
            metric_metadata[alias] = {"unit": source["unit"], "quantity": source["quantity"]}
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
        latest = max((r.date for r in trends if r.pm25 is not None and r.pm10 is not None), default=None)
        latest_rows = {r.province_code: r for r in trends if r.date == latest}
        snapshots = []
        for province in manifest["provinces"]:
            record = latest_rows.get(province["code"])
            snapshots.append(ProvinceSnapshot(
                province_code=province["code"], province_name=province["name"],
                pm25=record.pm25 if record else None, pm10=record.pm10 if record else None,
                pm1=record.pm1 if record else None,
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
                "note": "Dữ liệu mẫu tạm thời, chưa qua pipeline xử lý và kiểm định chính thức. "
                        f"Tái phân tích CAMS EAC4, trung bình tháng theo diện tích trên ranh giới {manifest['province_count']} tỉnh hiện có. "
                        "Các chỉ số *_column là tổng cột khí quyển (mg/m²). "
                        "Không có dữ liệu phát thải theo ngành; không suy AQI từ trung bình tháng.",
            },
        )
