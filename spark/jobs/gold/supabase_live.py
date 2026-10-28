"""Publish Supabase WAQI/API Ninjas Silver snapshots as historical Gold AQI.

This adapter preserves provider-reported overall and pollutant AQI. It never
relabels provider indices as computed VN_AQI, never treats WAQI IAQI as
concentration, and never fabricates an API Ninjas observation timestamp.
"""
import argparse
import fcntl
from datetime import date
import hashlib
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pyspark.sql import Window, functions as F

from aqi.engine import local_day_bounds
from dimensions import build_geography, build_time_method
from provider_aqi import POLLUTANTS, PROFILES, SCHEMES, overall_fact, pollutant_fact
from run import code_digest, distribute
from runtime import (Build, bootstrap, identifier, migrate_provider_aqi_columns,
                     spark_session, stable_id)


DATASETS = {"waqi": "live", "api_ninjas": "province_air_quality"}


def _naive(value):
    return value.replace(tzinfo=None)


def _dataset(build, source):
    rows = (build.read("dataset")
            .filter((F.col("source_system") == source) & (F.col("dataset_name") == DATASETS[source]))
            .collect())
    if len(rows) != 1:
        raise ValueError(f"Expected one Silver {source}/{DATASETS[source]} dataset, found {len(rows)}")
    return rows[0].asDict(recursive=True)


def _successful(build, dataset_id):
    return (build.read("ingestion_run")
            .filter((F.col("dataset_id") == dataset_id) & (F.col("status") == "succeeded"))
            .select(F.col("run_id").alias("ingestion_run_id")))


def _source_rows(build, source, dataset_id):
    lo, hi = F.lit(_naive(build.start)), F.lit(_naive(build.end))
    success = _successful(build, dataset_id)
    variables = {r.variable_id: r.asDict(recursive=True) for r in build.read("variable").collect()
                 if r.source_system == source and r.canonical_name in POLLUTANTS
                 and r.measurement_kind == "pollutant_aqi"}
    if {r["canonical_name"] for r in variables.values()} != set(POLLUTANTS):
        raise ValueError("Silver provider pollutant-AQI variable registry is incomplete")

    if source == "waqi":
        observations = (build.read("waqi_hourly_observation")
            .filter((F.col("dataset_id") == dataset_id) & (F.col("observation_time_utc") >= lo)
                    & (F.col("observation_time_utc") < hi))
            .join(success, "ingestion_run_id", "inner")
            .withColumn("hour_start_utc", F.date_trunc("hour", F.col("observation_time_utc"))))
        # A station can expose more than one actual instant in an analytical hour.
        # Preserve the latest actual source observation deterministically.
        rank = Window.partitionBy("dataset_id", "station_id", "hour_start_utc").orderBy(
            F.col("observation_time_utc").desc(), F.col("collected_at_utc").desc(),
            F.col("observation_id").desc())
        observations = observations.withColumn("_rank", F.row_number().over(rank)).filter("_rank=1").drop("_rank")
        observation_rows = [r.asDict(recursive=True) for r in observations.collect()]
        ids = [r["observation_id"] for r in observation_rows]
        measurements = (build.read("waqi_hourly_measurement").filter(F.col("observation_id").isin(ids))
                        .filter(F.col("variable_id").isin(list(variables))).collect()) if ids else []
        station_ids = sorted({r["station_id"] for r in observation_rows})
        locations = (build.read("waqi_station").filter(F.col("station_id").isin(station_ids)).collect()
                     if station_ids else [])
    else:
        observations = (build.read("province_air_quality_hourly_observation")
            .filter((F.col("dataset_id") == dataset_id) & (F.col("snapshot_hour_utc") >= lo)
                    & (F.col("snapshot_hour_utc") < hi))
            .join(success, "ingestion_run_id", "inner")
            .withColumn("hour_start_utc", F.col("snapshot_hour_utc")))
        observation_rows = [r.asDict(recursive=True) for r in observations.collect()]
        ids = [r["observation_id"] for r in observation_rows]
        measurements = (build.read("province_air_quality_hourly_measurement")
                        .filter(F.col("observation_id").isin(ids))
                        .filter(F.col("variable_id").isin(list(variables))).collect()) if ids else []
        proxy_ids = sorted({r["proxy_location_id"] for r in observation_rows})
        locations = (build.read("province_air_quality_location")
                     .filter((F.col("dataset_id") == dataset_id) & F.col("proxy_location_id").isin(proxy_ids)).collect()
                     if proxy_ids else [])
    if not observation_rows:
        raise ValueError("No succeeded Silver provider observations in requested local-date scope")
    return observation_rows, [r.asDict(recursive=True) for r in measurements], variables, \
        [r.asDict(recursive=True) for r in locations]


def _dimensions(build, source, dataset, observation_rows, variables, source_locations):
    scheme, profile = SCHEMES[source], PROFILES[source]
    location_rows = []
    location_ids = {}
    if source == "waqi":
        for row in source_locations:
            location_id = stable_id("waqi-station-location-v1", row["station_id"])
            location_ids[row["station_id"]] = location_id
            mapped = bool(row.get("admin_unit_version_id") and row.get("admin_code"))
            location_rows.append(dict(release_id=build.release_id, location_id=location_id,
                admin_unit_version_id=row.get("admin_unit_version_id"), name=row["station_name"],
                admin_code=row.get("admin_code"), location_kind="station",
                spatial_representation="station_point",
                mapping_status="verified" if mapped else "unresolved"))
    else:
        for row in source_locations:
            location_id = stable_id("api-ninjas-city-proxy-location-v1", row["proxy_location_id"])
            location_ids[row["proxy_location_id"]] = location_id
            location_rows.append(dict(release_id=build.release_id, location_id=location_id,
                admin_unit_version_id=row["admin_unit_version_id"], name=row["query_city"],
                admin_code=row["admin_code"], location_kind="city_proxy",
                spatial_representation="city_proxy", mapping_status="verified"))
    referenced = {r["station_id"] if source == "waqi" else r["proxy_location_id"] for r in observation_rows}
    if referenced != set(location_ids):
        raise ValueError("Provider observation/location inventory mismatch")

    series_rows, series_ids = [], {}
    for source_id, location_id in location_ids.items():
        series_id = stable_id("provider-aqi-series-v1", dataset["dataset_id"], location_id, scheme, profile)
        series_ids[source_id] = series_id
        series_rows.append(dict(release_id=build.release_id, series_id=series_id,
            dataset_id=dataset["dataset_id"], location_id=location_id, source_system=source,
            source_contract_version=scheme, source_resolution_minutes=60,
            temporal_support="provider_snapshot", applicability_profile=profile,
            spatial_policy_version="station-point-v1" if source == "waqi" else "city-proxy-v1"))

    metric_rows, metric_ids, bridge_rows = [], {}, []
    for variable_id, variable in variables.items():
        pollutant = variable["canonical_name"]
        metric_id = stable_id("metric-v1", pollutant, "pollutant_aqi", "AQI", "not_applicable", scheme)
        metric_ids[variable_id] = metric_id
        metric_rows.append(dict(release_id=build.release_id, metric_id=metric_id, pollutant=pollutant,
            measurement_kind="pollutant_aqi", unit="AQI", vertical_support="not_applicable",
            unit_policy_version=scheme))
        bridge_rows.append(dict(release_id=build.release_id, dataset_id=dataset["dataset_id"],
            variable_id=variable_id, source_column=variable["source_variable"], metric_id=metric_id,
            source_unit="AQI", standard_unit="AQI", metric_policy_version=scheme))
    return location_rows, series_rows, metric_rows, bridge_rows, location_ids, series_ids, metric_ids


def _facts(build, source, observations, measurements, variables, series_ids):
    by_observation = {}
    for row in measurements:
        key = (row["observation_id"], row["variable_id"])
        if key in by_observation:
            raise ValueError("Duplicate Silver provider pollutant measurement")
        by_observation[key] = row
    variable_by_pollutant = {v["canonical_name"]: key for key, v in variables.items()}
    canonical_by_variable = {key: v["canonical_name"] for key, v in variables.items()}
    overall_rows, component_rows = [], []
    for observation in observations:
        source_id = observation["station_id"] if source == "waqi" else observation["proxy_location_id"]
        series_id = series_ids[source_id]
        if source == "waqi":
            hour = observation["hour_start_utc"]
            observed, scheduled = observation["observation_time_utc"], None
            kind = "provider_observation"
            dominant = canonical_by_variable.get(observation.get("dominant_pollutant_variable_id"))
        else:
            hour = observation["snapshot_hour_utc"]
            observed, scheduled = None, observation["snapshot_hour_utc"]
            kind = "scheduled_provider_snapshot"
            dominant = None
        overall_rows.append(overall_fact(source=source, release_id=build.release_id,
            series_id=series_id, hour_start=hour, provider_aqi=observation.get("overall_aqi"),
            observed_at=observed, scheduled_at=scheduled,
            collected_at=observation["collected_at_utc"], observation_time_kind=kind,
            dominant_pollutants=[dominant] if dominant else [],
            input_run_id=observation["ingestion_run_id"], input_snapshots=build.inputs))
        for pollutant in POLLUTANTS:
            measurement = by_observation.get((observation["observation_id"], variable_by_pollutant[pollutant]))
            if measurement is None:
                raise ValueError("Silver provider observation lacks a pollutant-AQI row")
            value = measurement.get("value_standard")
            component_rows.append(pollutant_fact(source=source, release_id=build.release_id,
                series_id=series_id, pollutant=pollutant, hour_start=hour,
                provider_sub_index=value, missing_reason=measurement.get("missing_reason"),
                observed_at=observed, scheduled_at=scheduled,
                collected_at=observation["collected_at_utc"], observation_time_kind=kind,
                input_run_id=observation["ingestion_run_id"], input_snapshots=build.inputs))
    return overall_rows, component_rows


def _mart_rows(build, source, overall_rows, component_rows, series_rows, location_rows):
    overall = {(r["series_id"], r["hour_start_utc"]): r for r in overall_rows}
    series = {r["series_id"]: r for r in series_rows}
    locations = {r["location_id"]: r for r in location_rows}
    rows = []
    for component in component_rows:
        header = overall[component["series_id"], component["hour_start_utc"]]
        descriptor = series[component["series_id"]]
        location = locations[descriptor["location_id"]]
        value = component["provider_sub_index"]
        rows.append(dict(release_id=build.release_id, series_id=component["series_id"],
            location_id=descriptor["location_id"], admin_code=location.get("admin_code"), source=source,
            source_resolution_minutes=60, temporal_support="provider_snapshot",
            spatial_representation=location["spatial_representation"],
            applicability_profile=descriptor["applicability_profile"], pollutant=component["pollutant"],
            unit="AQI", value=value, quality_status="ok" if value is not None else "missing",
            missing_reason=component["missing_reason"], coverage=None, aqi=header["aqi"],
            aqi_category=None, aqi_color=None, dominant_pollutants=header["dominant_pollutants"],
            aqi_method_version=header["method_version"], aqi_status=header["status"],
            aqi_missing_reason=header["missing_reason"], aqi_origin="provider",
            aqi_provider=source, provider_aqi_scheme=header["provider_aqi_scheme"],
            sub_index=component["sub_index"], provider_aqi=header["aqi"],
            hour_start_utc=component["hour_start_utc"], observation_time=header["observed_at_utc"],
            grid_cells=None, effective_cells=None))
    return rows


def _quality(build):
    build.rows("mart_air_quality_hourly").createOrReplaceTempView("provider_hourly")
    quality = build.spark.sql("""
      SELECT release_id,series_id,source,
             to_date(from_utc_timestamp(hour_start_utc,'Asia/Ho_Chi_Minh')) date_local,
             pollutant,24 expected_hours,cast(count(*) AS INT) observed_slots,
             cast(count(value) AS INT) valid_measurements,
             cast(count_if(quality_status NOT IN ('ok','missing')) AS INT) invalid_measurements,
             cast(24-count(value) AS INT) missing_hours,count(value)/24.0 measurement_coverage,
             max(observation_time) latest_observation_time,source_resolution_minutes,temporal_support,
             count(DISTINCT hour_start_utc) collection_attempts,cast(NULL AS BIGINT) failed_ingestions,
             'provider_snapshot_slots; observation_time may be unknown' quality_scope
      FROM provider_hourly GROUP BY release_id,series_id,source,
             to_date(from_utc_timestamp(hour_start_utc,'Asia/Ho_Chi_Minh')),
             pollutant,source_resolution_minutes,temporal_support
    """)
    build.write("mart_source_quality_daily", quality)


def _validate(build, source, expected_observations):
    keys = {
        "dim_location": ["location_id"], "dim_air_quality_series": ["series_id"],
        "dim_metric": ["metric_id"],
        "bridge_source_variable_metric": ["dataset_id", "variable_id", "metric_id"],
        "fact_aqi_hourly": ["series_id", "hour_start_utc", "method_version", "applicability_profile"],
        "fact_aqi_pollutant_hourly": ["series_id", "hour_start_utc", "pollutant", "basis", "method_version", "applicability_profile"],
        "mart_air_quality_hourly": ["series_id", "hour_start_utc", "pollutant"],
        "mart_source_quality_daily": ["series_id", "date_local", "pollutant"],
    }
    counts = {}
    for name, columns in keys.items():
        rows = build.rows(name)
        counts[name] = rows.count()
        if rows.groupBy(*columns).count().filter("count>1").limit(1).count():
            raise ValueError("Duplicate provider Gold key: " + name)
        condition = None
        for column in columns:
            condition = F.col(column).isNull() if condition is None else condition | F.col(column).isNull()
        if rows.filter(condition).limit(1).count():
            raise ValueError("NULL provider Gold key: " + name)
    if counts["fact_aqi_hourly"] != expected_observations:
        raise ValueError("Provider observation count changed during Gold materialization")
    if counts["fact_aqi_pollutant_hourly"] != expected_observations * len(POLLUTANTS):
        raise ValueError("Provider pollutant scope is incomplete")
    if counts["mart_air_quality_hourly"] != counts["fact_aqi_pollutant_hourly"]:
        raise ValueError("Provider serving mart lost rows")
    if build.rows("fact_aqi_hourly").filter(
            (F.col("aqi_origin") != "provider") | (F.col("aqi_provider") != source)
            | F.col("provider_aqi_scheme").isNull() | (F.col("aqi") < 0)).limit(1).count():
        raise ValueError("Invalid provider overall AQI contract")
    if build.rows("fact_aqi_pollutant_hourly").filter(
            (F.col("aqi_origin") != "provider") | (F.col("aqi_provider") != source)
            | (F.col("basis") != "provider_snapshot_slot")
            | (F.col("provider_sub_index") < 0)).limit(1).count():
        raise ValueError("Invalid provider pollutant AQI contract")
    expected_kind = "station" if source == "waqi" else "city_proxy"
    source_locations = build.rows("dim_location").filter(F.col("location_kind") == expected_kind)
    if source_locations.count() != counts["dim_air_quality_series"]:
        raise ValueError("Provider series/location cardinality mismatch")
    return counts


def execute(args):
    started = time.monotonic()
    lock = open("/tmp/tlcn-gold-writer.lock", "w")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    spark = spark_session()
    try:
        distribute(spark)
        schema = identifier(args.schema)
        contract_path = Path(args.contract or (Path(args.schema_sql).parent / "contracts" /
            ("waqi-live-provider-v1.json" if args.source == "waqi" else "api-ninjas-provider-v1.json")))
        contract = json.loads(contract_path.read_text())
        if contract.get("source_system") != args.source or contract.get("aqi_origin") != "provider":
            raise ValueError("Provider contract/source mismatch")
        contract["geography"] = json.loads((contract_path.parent / "reporting-geography-v1.json").read_text())
        start = local_day_bounds(date.fromisoformat(args.start_date))[0]
        end = local_day_bounds(date.fromisoformat(args.end_date))[0]
        if not 0 < (end - start).days <= 31:
            raise ValueError("Use bounded scopes of 1..31 local days")
        bootstrap(spark, schema, args.schema_sql)
        migrate_provider_aqi_columns(spark, schema)
        build = Build(spark, schema, args.silver_schema, contract, start, end,
                      args.channel, code_digest(args.schema_sql))
        inputs = ["admin_unit", "admin_boundary", "ingestion_run", "dataset", "variable"]
        inputs += (["waqi_station", "waqi_hourly_observation", "waqi_hourly_measurement"]
                   if args.source == "waqi" else
                   ["province_air_quality_location", "province_air_quality_hourly_observation",
                    "province_air_quality_hourly_measurement"])
        for name in inputs:
            build.read(name)
        dataset = _dataset(build, args.source)
        observations, measurements, variables, source_locations = _source_rows(
            build, args.source, dataset["dataset_id"])
        build.identify()
        print("GOLD_PROVIDER_BEGIN " + json.dumps(dict(release_id=build.release_id,
              source=args.source, inputs=build.inputs), default=str), flush=True)
        existing = spark.table(build.prefix + "gold_release").filter(F.col("release_id") == build.release_id).collect()
        if existing:
            build.activate(existing[0].asDict())
            print("GOLD_PROVIDER_REPLAY " + build.release_id, flush=True)
            return

        base_locations = build_geography(build)
        build_time_method(build)
        method_rows = [r.asDict(recursive=True) for r in build.rows("dim_aqi_method").collect()]
        method_rows.append(dict(release_id=build.release_id, method_version=SCHEMES[args.source],
            reference_url=contract["reference_url"], reference_sha256=build.contract_hash,
            calendar_timezone="Asia/Ho_Chi_Minh",
            policies_json=json.dumps({"aqi_origin": "provider", "calculation": "not performed by lakehouse",
                "temporal_support": "provider_snapshot", "spatial_representation": contract["spatial_representation"]},
                sort_keys=True)))
        build.write("dim_aqi_method", method_rows)
        values = _dimensions(build, args.source, dataset, observations, variables, source_locations)
        locations, series, metrics, bridges, _, series_ids, _ = values
        build.write("dim_location", base_locations + locations)
        build.write("dim_air_quality_series", series)
        build.write("dim_metric", metrics)
        build.write("bridge_source_variable_metric", bridges)
        overall, components = _facts(build, args.source, observations, measurements, variables, series_ids)
        build.write("fact_aqi_hourly", overall)
        build.write("fact_aqi_pollutant_hourly", components)
        build.write("mart_air_quality_hourly", _mart_rows(build, args.source, overall, components, series, locations))
        _quality(build)
        counts = _validate(build, args.source, len(observations))
        release = build.publish(counts, method_version=SCHEMES[args.source])
        print("GOLD_PROVIDER_PUBLISHED " + json.dumps(dict(release_id=release["release_id"],
              source=args.source, counts=counts, elapsed_seconds=round(time.monotonic()-started, 3)),
              sort_keys=True), flush=True)
    finally:
        spark.stop()
        lock.close()


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", choices=DATASETS, required=True)
    parser.add_argument("--schema", default="gold")
    parser.add_argument("--silver-schema", default="silver")
    parser.add_argument("--schema-sql", default="/opt/spark/work-dir/lakehouse/gold/gold.sql")
    parser.add_argument("--contract")
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--end-date", required=True, help="exclusive local Vietnam date")
    parser.add_argument("--channel", default="provider_air_quality")
    return parser.parse_args()


if __name__ == "__main__":
    execute(parse_args())
