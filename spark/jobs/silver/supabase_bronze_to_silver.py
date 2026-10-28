"""Normalize one completed Supabase WAQI/API Ninjas Bronze batch into Iceberg."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import tempfile
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import PurePosixPath

from common import (
    TABLE_PREFIX, DataQualityError, bootstrap_schema, create_spark, finish_run,
    load_bronze_batch, merge_dataframe, metadata_rows, register_dataset,
    sha256_json, start_run, utc_now, write_quality_issues,
)

PIPELINE_VERSION = "1.0.0"
DATASETS = {"waqi": "live", "api_ninjas": "province_air_quality"}
POLLUTANTS = {"co": "CO", "no2": "NO2", "o3": "O3", "so2": "SO2", "pm25": "PM2.5", "pm10": "PM10"}
WAQI_FIELDS = {"pm25": ("pm25", "pollutant_aqi", "AQI"),
               "pm10": ("pm10", "pollutant_aqi", "AQI"),
               "o3": ("o3", "pollutant_aqi", "AQI"),
               "no2": ("no2", "pollutant_aqi", "AQI"),
               "so2": ("so2", "pollutant_aqi", "AQI"),
               "co": ("co", "pollutant_aqi", "AQI"),
               "t": ("temperature", "temperature", None),
               "h": ("humidity", "relative_humidity", None),
               "p": ("pressure", "pressure", None),
               "w": ("wind_speed", "wind_speed", None),
               "wd": ("wind_direction", "wind_direction", None)}
SHA = re.compile(r"^[0-9a-f]{64}$")
PROVINCE_BOUNDARY_TOLERANCE_METERS = 250.0


def timestamp(value):
    result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise DataQualityError("Source timestamp has no UTC offset")
    return result.astimezone(timezone.utc)


def number(value, *, integer=False, minimum=0, maximum=None):
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise DataQualityError("Invalid numeric source value")
    try:
        result = float(value)
    except ValueError as exc:
        raise DataQualityError("Invalid numeric source value") from exc
    if not math.isfinite(result) or result < minimum or (maximum is not None and result > maximum):
        raise DataQualityError("Source value outside allowed range")
    if integer:
        if not result.is_integer() or result > 2147483647:
            raise DataQualityError("AQI must fit SQL INT without rounding")
        return int(result)
    return result


def read_file(spark, object_path, expected_hash, expected_size, *, parse_json=True):
    if not SHA.fullmatch(str(expected_hash)):
        raise DataQualityError("Invalid Bronze SHA-256")
    source = spark._jvm.org.apache.hadoop.fs.Path(object_path)
    fs = source.getFileSystem(spark.sparkContext._jsc.hadoopConfiguration())
    with tempfile.TemporaryDirectory(prefix="supabase-silver-") as work:
        target = spark._jvm.org.apache.hadoop.fs.Path(work + "/input.json")
        fs.copyToLocalFile(False, source, target, True)
        with open(work + "/input.json", "rb") as handle:
            payload = handle.read()
    if len(payload) != expected_size or hashlib.sha256(payload).hexdigest() != expected_hash:
        raise DataQualityError("Bronze object bytes disagree with _file_metadata")
    return json.loads(payload) if parse_json else payload


def source_records(spark, batch):
    """Join every raw object to its verified provider manifest."""
    files = metadata_rows(batch, ["json"])
    by_path = {row.source_file: row for row in files}
    manifests = [row for row in files if PurePosixPath(row.source_file).name == "manifest.json"]
    seen = set()
    result = []
    issues = []
    input_targets = 0
    for meta in manifests:
        manifest = read_file(spark, meta.bronze_object, meta.file_sha256, meta.file_size)
        parts = PurePosixPath(meta.source_file).parts
        if len(parts) != 6 or parts[5] != "manifest.json" or not re.fullmatch(r"[0-9a-f-]{36}", parts[4]):
            raise DataQualityError("Invalid provider manifest path")
        hour = timestamp(manifest["scheduled_hour_utc"])
        if (manifest.get("schema_version") != 1 or manifest.get("source") != batch.source
                or manifest.get("collection_run_id") != parts[4]
                or parts[:4] != (hour.strftime("%Y"), hour.strftime("%m"), hour.strftime("%d"), hour.strftime("%H"))
                or manifest.get("status") not in {"succeeded", "partial"}):
            raise DataQualityError("Provider manifest identity/status mismatch")
        records = manifest.get("records")
        if not isinstance(records, list) or len(records) != manifest.get("expected_records"):
            raise DataQualityError("Provider manifest record count mismatch")
        input_targets += len(records)
        for entry in records:
            if entry.get("outcome") in {"valid", "partial"} and entry.get("validation_status") != entry["outcome"]:
                raise DataQualityError("Manifest outcome and validation status disagree")
            path = entry.get("raw_object_path")
            if batch.source == "waqi" and path and entry.get("raw_stored") is not True:
                if entry.get("outcome") in {"valid", "partial"}:
                    raise DataQualityError("Successful WAQI target has no stored raw object")
                issues.append({"rule_id": "supabase_target_without_raw", "severity": "warning",
                               "issue_type": "unavailable_source_snapshot",
                               "source_record_locator": str(entry.get("requested_source_uid") or entry.get("location_key")),
                               "description": "Collector target did not persist a raw response"})
                continue
            if not path:
                if entry.get("outcome") in {"valid", "partial"}:
                    raise DataQualityError("Successful target has no raw object")
                issues.append({"rule_id": "supabase_target_without_raw", "severity": "warning",
                               "issue_type": "unavailable_source_snapshot",
                               "source_record_locator": str(entry.get("requested_source_uid") or entry.get("location_key")),
                               "description": "Collector target has no raw response"})
                continue
            if not path.startswith(batch.source + "/"):
                raise DataQualityError("Raw object source mismatch")
            relative = path.split("/", 1)[1]
            if PurePosixPath(relative).parent != PurePosixPath(meta.source_file).parent:
                raise DataQualityError("Raw object is outside provider manifest directory")
            raw_meta = by_path.get(relative)
            if raw_meta is None or relative in seen or raw_meta.file_sha256 != entry.get("payload_sha256"):
                raise DataQualityError("Manifest raw object missing, repeated or hash mismatch")
            seen.add(relative)
            raw = read_file(spark, raw_meta.bronze_object, raw_meta.file_sha256, raw_meta.file_size,
                            parse_json=entry.get("outcome") in {"valid", "partial"})
            if entry.get("outcome") in {"valid", "partial"}:
                record = dict(entry)
                record["_manifest_source_file"] = meta.source_file
                record["_manifest_sha256"] = meta.file_sha256
                result.append((hour, manifest["collection_run_id"], record, raw, raw_meta))
            else:
                issues.append({"rule_id": "supabase_provider_invalid", "severity": "warning",
                               "issue_type": "invalid_source_snapshot", "source_file": relative,
                               "description": "Provider snapshot excluded: " + str(entry.get("outcome")),
                               "raw_record_json": json.dumps(entry.get("validation_errors") or {}, ensure_ascii=False)})
            if entry.get("outcome") == "partial":
                issues.append({"rule_id": "supabase_provider_partial", "severity": "warning",
                               "issue_type": "partial_source_snapshot", "source_file": relative,
                               "description": "Provider snapshot has invalid or missing optional fields",
                               "raw_record_json": json.dumps(entry.get("validation_errors") or {}, ensure_ascii=False)})
    if seen != set(by_path) - {m.source_file for m in manifests}:
        raise DataQualityError("Unreferenced raw file in Bronze batch")
    if not manifests:
        raise DataQualityError("Bronze batch has no provider manifest")
    return result, issues, input_targets


def variable_rows(source):
    if source == "waqi":
        specs = [(native, kind, unit) for native, kind, unit in WAQI_FIELDS.values()]
    else:
        specs = [(name, kind, "AQI" if kind == "pollutant_aqi" else None)
                 for name in POLLUTANTS for kind in ("pollutant_aqi", "concentration")]
    now = utc_now()
    return [{"variable_id": sha256_json("silver-variable-v1", source, name, kind),
             "source_system": source, "source_variable": name + ("_aqi" if source == "api_ninjas" and kind == "pollutant_aqi" else "_concentration" if source == "api_ninjas" else ""),
             "canonical_name": name, "variable_type": "air_quality" if kind in {"pollutant_aqi", "concentration"} else "weather",
             "measurement_kind": kind, "native_unit": unit, "standard_unit": unit,
             "param_id": None, "short_name": name,
             "description": "Provider value; concentration unit unconfirmed" if kind == "concentration" else "Provider supplied value",
             "created_at": now} for name, kind, unit in specs]


def frame(spark, table, rows):
    schema = spark.table(TABLE_PREFIX + "." + table).schema
    return spark.createDataFrame([tuple(row.get(field.name) for field in schema.fields) for row in rows], schema)


def distinct(rows, key, compare, kind):
    """Select stable first occurrence only when logical measurements agree."""
    selected = {}
    duplicates = 0
    for row in rows:
        identity = tuple(row[k] for k in key)
        values = tuple(row[k] for k in compare)
        if identity in selected:
            if tuple(selected[identity][k] for k in compare) != values:
                raise DataQualityError(f"{kind}: conflicting logical key {identity}")
            duplicates += 1
        else:
            selected[identity] = row
    return list(selected.values()), duplicates


def merge_checked(spark, table, rows, key, compare, run, *, update=False):
    if not rows:
        return 0
    rows, duplicates = distinct(rows, key, compare, table)
    if table in {"waqi_station", "waqi_station_source", "waqi_station_variable"}:
        previous = {tuple(r[k] for k in key): r.asDict() for r in
                    spark.table(TABLE_PREFIX + "." + table).collect()}
        for row in rows:
            old = previous.get(tuple(row[k] for k in key))
            if old is None:
                continue
            date_fields = (("first_seen_date", "last_seen_date")
                           if table != "waqi_station_variable" else
                           ("first_observation_date", "last_observation_date"))
            first, last = date_fields
            row[first] = min((x for x in (row[first], old[first]) if x is not None), default=None)
            row[last] = max((x for x in (row[last], old[last]) if x is not None), default=None)
            if table == "waqi_station":
                row["created_by_run_id"] = old["created_by_run_id"]
                row["created_at"] = old["created_at"]
            if table == "waqi_station_variable":
                row["is_available"] = row["is_available"] or old["is_available"]
    incoming = frame(spark, table, rows)
    existing = spark.table(TABLE_PREFIX + "." + table)
    if "dataset_id" in existing.columns:
        existing = existing.filter("dataset_id = '" + run.dataset_id + "'")
    joined = incoming.alias("i").join(existing.alias("e"), [incoming[k] == existing[k] for k in key], "inner")
    bad = joined.filter(" OR ".join(f"NOT (i.`{c}` <=> e.`{c}`)" for c in compare)).limit(1).count()
    if bad:
        write_quality_issues(spark, run, [{"rule_id": "supabase_conflicting_existing_key", "severity": "fatal",
                                          "description": f"{table} has a conflicting logical key in Silver"}])
        raise DataQualityError(f"{table}: existing Silver value conflicts with Bronze")
    merge_dataframe(spark, incoming, TABLE_PREFIX + "." + table, key, update=update)
    return duplicates


def normal_name(name):
    value = unicodedata.normalize("NFD", str(name).casefold())
    value = "".join(c for c in value if unicodedata.category(c) != "Mn").replace("đ", "d")
    value = re.sub(r"[^a-z0-9]+", " ", value).strip()
    return re.sub(r"^(thanh pho|tp|tinh) +", "", value)


def distance_meters(a, b):
    """Great-circle distance between two lon/lat Shapely points."""
    lat1, lat2 = math.radians(a.y), math.radians(b.y)
    dlat = lat2 - lat1
    dlon = math.radians(b.x - a.x)
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 6371008.8 * 2 * math.asin(min(1.0, math.sqrt(h)))


def province_lookup(spark, locations):
    from pyspark.sql import functions as F
    from shapely import wkb
    from shapely.geometry import Point
    from shapely.ops import nearest_points

    candidates = spark.table(TABLE_PREFIX + ".admin_unit").filter("is_current = true AND parent_code IS NULL").select(
        "admin_unit_version_id", "admin_code", "name_vi").collect()
    names = {}
    for row in candidates:
        names.setdefault(normal_name(row.name_vi), []).append(row)
    province_ids = [row.admin_unit_version_id for row in candidates]
    boundaries = (spark.table(TABLE_PREFIX + ".admin_boundary")
                  .filter(F.col("admin_unit_version_id").isin(province_ids))
                  .select("admin_unit_version_id", "boundary_wkb", "srid").collect())
    shapes = {}
    for row in boundaries:
        if row.srid != 4326:
            raise DataQualityError("Province boundary must use EPSG:4326 coordinates")
        shapes.setdefault(row.admin_unit_version_id, []).append(wkb.loads(bytes(row.boundary_wkb)))
    resolved = {}
    for loc in locations:
        name = normal_name(loc["province_name"])
        matches = names.get(name, [])
        if len(matches) != 1:
            raise DataQualityError(f"No unique current province for {loc['province_name']!r}")
        province = matches[0]
        point = Point(loc["longitude"], loc["latitude"])
        geometries = shapes.get(province.admin_unit_version_id, [])
        if not geometries:
            raise DataQualityError(f"Province has no boundary: {loc['location_key']}")
        if any(shape.covers(point) for shape in geometries):
            method, confidence, distance = "province_name_and_boundary", 1.0, 0.0
        else:
            distance = min(distance_meters(point, nearest_points(point, shape)[1]) for shape in geometries)
            if distance > PROVINCE_BOUNDARY_TOLERANCE_METERS:
                raise DataQualityError(
                    f"Proxy coordinate is {distance:.0f} m outside configured province: {loc['location_key']}"
                )
            method, confidence = "province_name_boundary_tolerance_250m", 0.9
        resolved[loc["location_id"]] = (
            province.admin_unit_version_id, province.admin_code, method, confidence, distance
        )
    return resolved


def latest_waqi_records(records):
    """Keep the newest provider snapshot for one station observation clock.

    WAQI can return the same ``time.iso`` in consecutive collection hours while
    correcting pollutant or weather values. Bronze retains every raw response;
    Silver is canonical at station + provider observation time, so the latest
    ``collected_at_utc`` wins deterministically.
    """
    selected = {}
    superseded = 0
    for record in records:
        hour, collection_run_id, entry, raw, meta = record
        data = raw.get("data") if isinstance(raw, dict) else None
        if not isinstance(raw, dict) or raw.get("status") != "ok" or not isinstance(data, dict):
            raise DataQualityError("WAQI valid manifest points to invalid provider payload")
        uid = str(entry["requested_source_uid"])
        if str(data.get("idx")) != uid:
            raise DataQualityError("WAQI returned station UID differs from requested UID")
        observation_time = timestamp(data["time"]["iso"])
        collected = timestamp(entry["collected_at_utc"])
        key = (uid, observation_time)
        # The remaining fields make equal collection timestamps deterministic
        # without changing the primary latest-collected policy.
        rank = (collected, hour, str(collection_run_id), meta.source_file)
        previous = selected.get(key)
        if previous is None:
            selected[key] = (rank, record)
            continue
        superseded += 1
        if rank > previous[0]:
            selected[key] = (rank, record)
    ordered = [value[1] for _, value in sorted(selected.items(), key=lambda item: item[0])]
    return ordered, superseded


def waqi(spark, records, run):
    now = utc_now()
    stations, sources, availability, observations, measurements = [], [], [], [], []
    variables = {(r["source_variable"], r["measurement_kind"]): r["variable_id"] for r in variable_rows("waqi")}
    for hour, run_id, entry, raw, meta in records:
        uid = str(entry["requested_source_uid"])
        data = raw.get("data") if isinstance(raw, dict) else None
        if raw.get("status") != "ok" or not isinstance(data, dict):
            raise DataQualityError("WAQI valid manifest points to invalid provider payload")
        if str(data.get("idx")) != uid:
            raise DataQualityError("WAQI returned station UID differs from requested UID")
        observation_time = timestamp(data["time"]["iso"])
        collected = timestamp(entry["collected_at_utc"])
        overall = number(data.get("aqi"), integer=True)
        if overall is None:
            raise DataQualityError("WAQI valid observation has no overall AQI")
        iaqi = data.get("iaqi") if isinstance(data.get("iaqi"), dict) else {}
        city = data.get("city") if isinstance(data.get("city"), dict) else {}
        coords = city.get("geo")
        latitude = number(coords[0], minimum=-90, maximum=90) if isinstance(coords, list) and len(coords) == 2 else None
        longitude = number(coords[1], minimum=-180, maximum=180) if isinstance(coords, list) and len(coords) == 2 else None
        name = city.get("name") or uid
        station_id = sha256_json("waqi-live-station-v1", uid)
        local_date = observation_time.astimezone(timezone(timedelta(hours=7))).date()
        station = dict(station_id=station_id, station_name=name, location_label=name,
                       admin_unit_version_id=None, admin_code=None, latitude=latitude, longitude=longitude,
                       timezone=data["time"].get("tz"), metadata_status="partial", admin_match_method=None,
                       admin_match_confidence=None, first_seen_date=local_date, last_seen_date=local_date,
                       created_by_run_id=run.run_id, updated_by_run_id=run.run_id, created_at=now, updated_at=now)
        stations.append(station)
        sources.append(dict(dataset_id=run.dataset_id, source_station_key=uid, station_id=station_id,
                            source_station_id=uid, source_station_name=name, source_location_label=name,
                            source_file=meta.source_file, source_file_sha256=meta.file_sha256,
                            ingestion_run_id=run.run_id, first_seen_date=local_date,
                            last_seen_date=local_date, loaded_at=now))
        observation_id = sha256_json("waqi-hourly-observation-v1", run.dataset_id, station_id, observation_time)
        dominant = data.get("dominentpol")
        dominant_id = variables.get((dominant, "pollutant_aqi")) if dominant else None
        observations.append(dict(observation_id=observation_id, dataset_id=run.dataset_id,
                                 station_id=station_id, observation_time_utc=observation_time,
                                 overall_aqi=overall, dominant_pollutant_variable_id=dominant_id,
                                 source_timezone=data["time"].get("tz"), collected_at_utc=collected,
                                 qc_flag="ok" if entry.get("validation_status") == "valid" else "missing",
                                 source_file=meta.source_file, source_file_sha256=meta.file_sha256,
                                 ingestion_run_id=run.run_id, loaded_at=now))
        for native, (name, kind, _) in WAQI_FIELDS.items():
            item = iaqi.get(native)
            rejected = name in (entry.get("validation_errors") or {})
            value = None if item is None or rejected or not isinstance(item, dict) else number(item.get("v"),
                                                       integer=False, minimum=-100 if native == "t" else 0,
                                                       maximum=80 if native == "t" else 100 if native == "h" else 360 if native == "wd" else 10000)
            var_id = variables[(name, kind)]
            measurements.append(dict(observation_id=observation_id, dataset_id=run.dataset_id,
                                     station_id=station_id, observation_time_utc=observation_time,
                                     variable_id=var_id, value_native=value,
                                     value_standard=value if kind == "pollutant_aqi" else None,
                                     missing_reason="provider_invalid" if rejected else "not_reported" if value is None else None,
                                     qc_flag="missing" if value is None else "ok", ingestion_run_id=run.run_id,
                                     loaded_at=now))
            availability.append(dict(dataset_id=run.dataset_id, station_id=station_id,
                                     variable_id=var_id, source_column_name=native, is_available=value is not None,
                                     first_observation_date=local_date if value is not None else None,
                                     last_observation_date=local_date if value is not None else None,
                                     last_seen_run_id=run.run_id, updated_at=now))
    station_map = {}
    for row in stations:
        previous = station_map.get(row["station_id"])
        if previous is None:
            station_map[row["station_id"]] = row
        else:
            previous["first_seen_date"] = min(previous["first_seen_date"], row["first_seen_date"])
            previous["last_seen_date"] = max(previous["last_seen_date"], row["last_seen_date"])
    source_map = {}
    for row in sources:
        previous = source_map.get(row["source_station_key"])
        if previous is None:
            source_map[row["source_station_key"]] = row
        else:
            previous["first_seen_date"] = min(previous["first_seen_date"], row["first_seen_date"])
            previous["last_seen_date"] = max(previous["last_seen_date"], row["last_seen_date"])
    availability_map = {}
    for row in availability:
        key = (row["station_id"], row["variable_id"])
        previous = availability_map.get(key)
        if previous is None:
            availability_map[key] = row
        elif row["is_available"]:
            previous["is_available"] = True
            previous["first_observation_date"] = min(
                (d for d in (previous["first_observation_date"], row["first_observation_date"]) if d is not None),
            )
            previous["last_observation_date"] = max(
                (d for d in (previous["last_observation_date"], row["last_observation_date"]) if d is not None),
            )
    return [
        ("waqi_station", list(station_map.values()), ["station_id"], ["station_id"], True),
        ("waqi_station_source", list(source_map.values()), ["dataset_id", "source_station_key"], ["station_id"], True),
        ("waqi_station_variable", list(availability_map.values()), ["dataset_id", "station_id", "variable_id"], ["source_column_name"], True),
        ("waqi_hourly_observation", observations, ["dataset_id", "station_id", "observation_time_utc"],
         ["overall_aqi", "dominant_pollutant_variable_id"], True),
        ("waqi_hourly_measurement", measurements,
         ["dataset_id", "station_id", "observation_time_utc", "variable_id"],
         ["value_native", "missing_reason"], True),
    ], len(observations)


def ninjas(spark, records, run):
    now = utc_now()
    locations = {}
    for _, _, entry, _, _ in records:
        location_id = entry["location_id"]
        details = {k: entry[k] for k in ("location_id", "location_key", "province_name", "query_city", "latitude", "longitude")}
        if location_id in locations and locations[location_id] != details:
            raise DataQualityError("Ninjas location metadata changed within batch")
        locations[location_id] = details
    mapped = province_lookup(spark, locations.values())
    manifest_by_location = {entry["location_id"]: entry["_manifest_source_file"]
                            for _, _, entry, _, _ in records}
    spatial_issues = []
    for location_id, (_, _, method, _, distance) in mapped.items():
        if distance:
            spatial_issues.append({
                "rule_id": "province_proxy_near_boundary", "severity": "warning",
                "issue_type": "spatial_mapping_tolerance",
                "source_file": manifest_by_location[location_id],
                "source_record_locator": locations[location_id]["location_key"],
                "record_key": location_id,
                "description": f"Proxy is {distance:.1f} m outside the named province polygon; accepted within 250 m",
                "original_value": str(distance), "normalized_value": method,
            })
    write_quality_issues(spark, run, spatial_issues)
    loc_rows, observations, measurements = [], [], []
    var_ids = {(r["canonical_name"], r["measurement_kind"]): r["variable_id"] for r in variable_rows("api_ninjas")}
    for hour, collection_run_id, entry, raw, meta in records:
        if not isinstance(raw, dict):
            raise DataQualityError("API Ninjas payload must be an object")
        location_id = entry["location_id"]
        loc = locations[location_id]
        latitude = number(loc["latitude"], minimum=-90, maximum=90)
        longitude = number(loc["longitude"], minimum=-180, maximum=180)
        admin_id, admin_code, mapping_method, mapping_confidence, _ = mapped[location_id]
        proxy_id = sha256_json("province-air-quality-proxy-v1", run.dataset_id, location_id)
        loc_rows.append(dict(dataset_id=run.dataset_id, proxy_location_id=proxy_id,
                             source_location_id=location_id, location_key=loc["location_key"],
                             admin_unit_version_id=admin_id, admin_code=admin_code,
                             query_city=loc["query_city"], query_latitude=latitude,
                             query_longitude=longitude, spatial_representation="city_proxy",
                             mapping_method=mapping_method, mapping_confidence=mapping_confidence,
                             source_file=entry["_manifest_source_file"],
                             source_file_sha256=entry["_manifest_sha256"],
                             ingestion_run_id=run.run_id, loaded_at=now))
        overall = number(raw.get("overall_aqi"), integer=True)
        if overall is None:
            raise DataQualityError("Ninjas valid observation has no overall AQI")
        collected = timestamp(entry["collected_at_utc"])
        observation_id = sha256_json("province-air-quality-observation-v1", run.dataset_id, proxy_id, hour)
        observations.append(dict(observation_id=observation_id, dataset_id=run.dataset_id,
                                 proxy_location_id=proxy_id, admin_unit_version_id=admin_id,
                                 snapshot_hour_utc=hour, collected_at_utc=collected,
                                 overall_aqi=overall, validation_status=entry["validation_status"],
                                 qc_flag="ok" if entry["validation_status"] == "valid" else "missing",
                                 source_collection_run_id=collection_run_id,
                                 source_file=meta.source_file, source_file_sha256=meta.file_sha256,
                                 ingestion_run_id=run.run_id, loaded_at=now))
        for name, provider_key in POLLUTANTS.items():
            item = raw.get(provider_key) if isinstance(raw.get(provider_key), dict) else {}
            for field, kind in (("aqi", "pollutant_aqi"), ("concentration", "concentration")):
                rejected = f"{name}_{field}" in (entry.get("validation_errors") or {})
                value = None if rejected else number(item.get(field), integer=field == "aqi")
                measurements.append(dict(observation_id=observation_id, dataset_id=run.dataset_id,
                                         proxy_location_id=proxy_id, admin_unit_version_id=admin_id,
                                         snapshot_hour_utc=hour, variable_id=var_ids[(name, kind)],
                                         value_native=float(value) if value is not None else None,
                                         value_standard=float(value) if value is not None and kind == "pollutant_aqi" else None,
                                         missing_reason="provider_invalid" if rejected else "not_reported" if value is None else None,
                                         qc_flag="missing" if value is None else "ok",
                                         ingestion_run_id=run.run_id, loaded_at=now))
    return [
        ("province_air_quality_location", loc_rows, ["dataset_id", "source_location_id"],
         ["location_key", "admin_unit_version_id", "query_city", "query_latitude", "query_longitude"], True),
        ("province_air_quality_hourly_observation", observations,
         ["dataset_id", "proxy_location_id", "snapshot_hour_utc"], ["overall_aqi", "admin_unit_version_id"], True),
        ("province_air_quality_hourly_measurement", measurements,
         ["observation_id", "variable_id"], ["value_native", "missing_reason"], True),
    ], len(observations)


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", choices=DATASETS, required=True)
    parser.add_argument("--bronze-path", required=True)
    parser.add_argument("--schema-sql", default=os.environ.get("SILVER_SCHEMA_SQL", "/opt/spark/work-dir/lakehouse/silver/silver.sql"))
    return parser.parse_args()


def main():
    args = parse_args()
    if not args.bronze_path or "ingestion_date=/" in args.bronze_path or args.bronze_path.endswith("batch_id="):
        raise ValueError("--bronze-path is incomplete; run Bronze successfully and use its BRONZE_PATH")
    spark = create_spark("supabase-" + args.source + "-bronze-to-silver")
    run = None
    try:
        bootstrap_schema(spark, args.schema_sql)
        batch = load_bronze_batch(spark, args.bronze_path)
        if (batch.source, batch.dataset_name) != (args.source, DATASETS[args.source]):
            raise ValueError("Bronze source/dataset does not match --source")
        dataset_id = register_dataset(spark, batch, source_uri="https://supabase.com/storage/v1",
                                      description="Supabase private raw API collection")
        run = start_run(spark, batch, dataset_id, "supabase-" + args.source + "-bronze-to-silver",
                        pipeline_version=PIPELINE_VERSION)
        if run.skipped:
            return
        records, issues, input_targets = source_records(spark, batch)
        superseded = 0
        if args.source == "waqi":
            records, superseded = latest_waqi_records(records)
            if superseded:
                issues.append({
                    "rule_id": "waqi_provider_correction_superseded",
                    "severity": "warning",
                    "issue_type": "provider_snapshot_correction",
                    "description": (
                        f"Selected latest collected_at_utc for {superseded} repeated "
                        "station observation snapshot(s); all raw versions remain in Bronze"
                    ),
                })
        write_quality_issues(spark, run, issues)
        specs, output = waqi(spark, records, run) if args.source == "waqi" else ninjas(spark, records, run)
        if not output:
            raise DataQualityError("Batch has no valid or partial observations")
        variables = variable_rows(args.source)
        merge_checked(spark, "variable", variables, ["source_system", "source_variable", "measurement_kind"],
                      ["native_unit", "standard_unit"], run)
        duplicates = superseded
        for table, rows, key, compare, update in specs:
            duplicates += merge_checked(spark, table, rows, key, compare, run, update=update)
        finish_run(spark, run, status="succeeded", input_rows=input_targets, output_rows=output,
                   duplicate_rows=duplicates,
                   invalid_rows=sum(issue["rule_id"] in {"supabase_provider_invalid", "supabase_target_without_raw"}
                                    for issue in issues))
    except Exception as exc:
        if run is not None and not run.skipped:
            if isinstance(exc, DataQualityError):
                write_quality_issues(spark, run, [{"rule_id": "supabase_normalization_failed",
                                                  "severity": "fatal", "description": str(exc)}])
            finish_run(spark, run, status="failed", error_message=str(exc))
        raise
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
