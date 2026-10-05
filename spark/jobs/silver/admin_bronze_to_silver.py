"""Transform one Vietnamese administrative-reference Bronze batch to Silver."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime

from pyspark.sql import functions as F, types as T

from common import (
    TABLE_PREFIX,
    DataQualityError,
    bootstrap_schema,
    create_spark,
    deduplicate_or_fail,
    finish_run,
    load_bronze_batch,
    merge_dataframe,
    metadata_rows,
    register_dataset,
    sha256_json,
    start_run,
    utc_now,
    write_quality_issues,
)


PIPELINE = "admin-bronze-to-silver"
OPEN_ADMIN_DATASET = "vietnam_administrative_divisions"
PROVINCES_DATASET = "vietnamese-provinces-database"


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bronze-path", required=True)
    parser.add_argument(
        "--schema-sql",
        default=os.environ.get(
            "SILVER_SCHEMA_SQL", "/opt/spark/work-dir/lakehouse/silver/silver.sql"
        ),
    )
    parser.add_argument("--source-version")
    return parser.parse_args()


def one_metadata(batch, suffix: str):
    matches = [row for row in metadata_rows(batch) if row.source_file.endswith(suffix)]
    if len(matches) != 1:
        raise ValueError(f"Expected exactly one Bronze file ending {suffix!r}, found {len(matches)}")
    return matches[0]


def source_contract(spark, batch, explicit_version):
    if batch.dataset_name == OPEN_ADMIN_DATASET:
        meta = one_metadata(batch, "metadata/source.json")
        source = spark.read.option("multiline", True).json(meta.bronze_object).first()
        snapshot_date = datetime.strptime(source.snapshot_date, "%Y-%m-%d").date()
        version = explicit_version or (
            snapshot_date.isoformat() if source.git_commit in {None, "..."} else source.git_commit
        )
        return version, snapshot_date, source.source_url, "CC-BY-4.0", False
    if batch.dataset_name == PROVINCES_DATASET:
        meta = one_metadata(batch, "json/vn_provinces_metadata.json")
        source = spark.read.option("multiline", True).json(meta.bronze_object).first()
        snapshot_date = datetime.fromisoformat(source.GeneratedAt.replace("Z", "+00:00")).date()
        return explicit_version or source.DatasetVersion, snapshot_date, None, None, True
    raise ValueError(f"Unsupported administrative Bronze dataset: {batch.dataset_name}")


def admin_version_id(code, snapshot_date):
    return sha256_json("admin-unit-version-v1", code, snapshot_date)


def read_open_admin(spark, batch, run, snapshot_date):
    frames = []
    for suffix in ("all-province.json", "all-ward.json"):
        meta = one_metadata(batch, suffix)
        frame = spark.read.option("multiline", True).json(meta.bronze_object)
        frame = frame.select(
            F.coalesce(F.col("code.id"), F.col("id")).cast("string").alias("admin_code"),
            F.col("parent.id").cast("string").alias("parent_code"),
            F.col("level").cast("int").alias("admin_level"),
            F.col("level_name.local").alias("unit_type"),
            F.trim(F.col("name.local")).alias("name_vi"),
            F.trim(F.col("name.en")).alias("name_en"),
            F.lit(None).cast("string").alias("full_name_vi"),
            F.lit(None).cast("string").alias("full_name_en"),
            F.col("name.slug").alias("slug"),
            F.col("zip_codes").cast("array<string>").alias("postal_codes"),
            F.lit(meta.source_file).alias("source_file"),
            F.lit(meta.file_sha256).alias("source_file_sha256"),
        )
        frames.append(frame)
    result = frames[0].unionByName(frames[1])
    return add_admin_contract(result, run, snapshot_date)


def compact_postal_array(*columns):
    values = F.flatten(F.array(*[
        F.when(column.isNull(), F.array().cast("array<string>"))
        .otherwise(F.transform(F.split(column, ","), lambda value: F.trim(value)))
        for column in columns
    ]))
    return F.filter(values, lambda value: value.isNotNull() & (value != ""))


def read_provinces_database(spark, batch, run, snapshot_date):
    meta = one_metadata(batch, "json/full_json_generated_data_vn_units.json")
    provinces = spark.read.option("multiline", True).json(meta.bronze_object)
    province_rows = provinces.select(
        F.col("Code").cast("string").alias("admin_code"),
        F.lit(None).cast("string").alias("parent_code"),
        F.lit(1).alias("admin_level"),
        F.col("AdministrativeUnitShortName").alias("unit_type"),
        F.trim("Name").alias("name_vi"), F.trim("NameEn").alias("name_en"),
        F.trim("FullName").alias("full_name_vi"), F.trim("FullNameEn").alias("full_name_en"),
        F.col("CodeName").alias("slug"),
        compact_postal_array(F.col("PostalCodePrefix")).alias("postal_codes"),
    )
    ward_rows = provinces.select(F.explode("Wards").alias("ward")).select(
        F.col("ward.Code").cast("string").alias("admin_code"),
        F.col("ward.ProvinceCode").cast("string").alias("parent_code"),
        F.lit(2).alias("admin_level"),
        F.col("ward.AdministrativeUnitShortName").alias("unit_type"),
        F.trim("ward.Name").alias("name_vi"), F.trim("ward.NameEn").alias("name_en"),
        F.trim("ward.FullName").alias("full_name_vi"), F.trim("ward.FullNameEn").alias("full_name_en"),
        F.col("ward.CodeName").alias("slug"),
        compact_postal_array(F.col("ward.PostalCode")).alias("postal_codes"),
    )
    result = province_rows.unionByName(ward_rows).withColumn("source_file", F.lit(meta.source_file)) \
        .withColumn("source_file_sha256", F.lit(meta.file_sha256))
    return add_admin_contract(result, run, snapshot_date)


def add_admin_contract(frame, run, snapshot_date):
    version_udf = F.udf(lambda code: admin_version_id(code, snapshot_date), "string")
    return frame.select(
        version_udf("admin_code").alias("admin_unit_version_id"),
        "admin_code",
        F.when(F.col("parent_code").isNotNull(), version_udf("parent_code"))
        .alias("parent_admin_unit_version_id"),
        "parent_code", "admin_level", "unit_type", "name_vi", "name_en",
        "full_name_vi", "full_name_en", "slug", "postal_codes",
        F.lit(snapshot_date).cast("date").alias("snapshot_date"),
        F.lit(None).cast("date").alias("valid_from"),
        F.lit(None).cast("date").alias("valid_to"),
        F.lit(True).alias("is_current"),
        F.lit(run.run_id).alias("created_by_run_id"),
        F.lit(utc_now()).cast("timestamp").alias("created_at"),
        "source_file", "source_file_sha256",
    )


GEOMETRY_SCHEMA = T.ArrayType(T.StructType([
    T.StructField("admin_code", T.StringType(), True),
    T.StructField("boundary_wkb", T.BinaryType(), True),
    T.StructField("geometry_type", T.StringType(), True),
    T.StructField("area_km2", T.DoubleType(), True),
    T.StructField("bbox_min_lon", T.DoubleType(), True),
    T.StructField("bbox_min_lat", T.DoubleType(), True),
    T.StructField("bbox_max_lon", T.DoubleType(), True),
    T.StructField("bbox_max_lat", T.DoubleType(), True),
    T.StructField("srid", T.IntegerType(), True),
    T.StructField("source_geometry_index", T.IntegerType(), True),
    T.StructField("error", T.StringType(), True),
]))


@F.udf(GEOMETRY_SCHEMA)
def parse_geojson(value):
    try:
        from shapely.geometry import shape

        document = json.loads(value)
        crs = document.get("crs")
        srid = 4326
        if crs:
            name = str(crs.get("properties", {}).get("name", ""))
            if "EPSG" in name.upper():
                srid = int(name.rsplit(":", 1)[-1])
        result = []
        for index, feature in enumerate(document.get("features") or []):
            geometry = shape(feature.get("geometry"))
            props = feature.get("properties") or {}
            code = str(props.get("code") or feature.get("id") or "").strip()
            bounds = feature.get("bbox") or document.get("bbox") or list(geometry.bounds)
            if len(bounds) != 4:
                raise ValueError("bbox must contain four coordinates")
            area = props.get("areaKm2")
            result.append({
                "admin_code": code or None,
                "boundary_wkb": bytes(geometry.wkb),
                "geometry_type": geometry.geom_type,
                "area_km2": float(area) if area not in {None, ""} else None,
                "bbox_min_lon": float(bounds[0]), "bbox_min_lat": float(bounds[1]),
                "bbox_max_lon": float(bounds[2]), "bbox_max_lat": float(bounds[3]),
                "srid": srid, "source_geometry_index": index, "error": None,
            })
        if not result:
            raise ValueError("FeatureCollection has no features")
        return result
    except Exception as exc:  # returned as DQ data instead of silently dropping the file
        return [{"error": str(exc)}]


def read_boundaries(spark, batch, run, dataset_id, snapshot_date, admin_units):
    geo_meta = batch.metadata.filter(F.lower("file_format") == "geojson").select(
        "source_file", "file_sha256", "bronze_object"
    )
    paths = [row.bronze_object for row in geo_meta.select("bronze_object").collect()]
    if not paths:
        return None
    documents = spark.read.option("wholetext", True).text(paths).withColumn(
        "bronze_object", F.input_file_name()
    )
    documents = documents.withColumn(
        "source_file", F.regexp_extract("bronze_object", r"/files/(.*)$", 1)
    ).join(geo_meta.select("source_file", "file_sha256"), "source_file", "left")
    parsed = documents.select(
        "source_file", "file_sha256", F.explode(parse_geojson("value")).alias("geometry")
    ).select("source_file", "file_sha256", "geometry.*")
    bad = parsed.filter(
        F.col("error").isNotNull() | F.col("admin_code").isNull()
        | F.col("file_sha256").isNull() | F.col("boundary_wkb").isNull()
        | (F.col("bbox_min_lon") > F.col("bbox_max_lon"))
        | (F.col("bbox_min_lat") > F.col("bbox_max_lat"))
        | (~F.col("bbox_min_lat").between(-90.0, 90.0))
        | (~F.col("bbox_max_lat").between(-90.0, 90.0))
        | (~F.col("bbox_min_lon").between(-180.0, 180.0))
        | (~F.col("bbox_max_lon").between(-180.0, 180.0))
    )
    bad_rows = bad.limit(100).collect()
    if bad_rows:
        write_quality_issues(spark, run, ({
            "source_file": row.source_file,
            "source_record_locator": f"json:pointer=/features/{row.source_geometry_index}",
            "column_name": "geometry",
            "rule_id": "admin_boundary_geometry",
            "issue_type": "invalid_geometry",
            "severity": "fatal",
            "description": row.error or "Boundary geometry or bbox is invalid.",
        } for row in bad_rows))
        raise DataQualityError("Administrative boundary geometry validation failed")

    version_udf = F.udf(lambda code: admin_version_id(code, snapshot_date), "string")
    boundary_id_udf = F.udf(
        lambda version_id, sha, index: sha256_json(
            "admin-boundary-v1", version_id, dataset_id, sha, index
        ), "string",
    )
    boundaries = parsed.filter(F.col("error").isNull()).select(
        F.lit(None).cast("string").alias("boundary_id"),
        version_udf("admin_code").alias("admin_unit_version_id"),
        "admin_code", "boundary_wkb", "geometry_type", "area_km2",
        "bbox_min_lon", "bbox_min_lat", "bbox_max_lon", "bbox_max_lat", "srid",
        F.lit(dataset_id).alias("dataset_id"), "source_file",
        F.col("file_sha256").alias("source_file_sha256"), "source_geometry_index",
        F.lit(run.run_id).alias("ingestion_run_id"),
        F.lit(snapshot_date).cast("date").alias("snapshot_date"),
        F.lit(utc_now()).cast("timestamp").alias("loaded_at"),
    )
    boundaries = boundaries.withColumn(
        "boundary_id",
        boundary_id_udf(
            "admin_unit_version_id", "source_file_sha256", "source_geometry_index"
        ),
    )
    missing_admin = boundaries.join(
        admin_units.select("admin_unit_version_id"), "admin_unit_version_id", "left_anti"
    ).limit(20).collect()
    if missing_admin:
        write_quality_issues(spark, run, ({
            "source_file": row.source_file,
            "record_key": row.admin_code,
            "rule_id": "admin_boundary_missing_unit",
            "issue_type": "missing_reference",
            "severity": "fatal",
            "description": "Boundary admin_code has no administrative unit in the same snapshot.",
        } for row in missing_admin))
        raise DataQualityError("Administrative boundaries reference unknown admin codes")
    boundaries, duplicates = deduplicate_or_fail(
        spark, boundaries, key_columns=["boundary_id"],
        compare_columns=[
            "admin_unit_version_id", "admin_code", "boundary_wkb", "geometry_type", "area_km2",
            "bbox_min_lon", "bbox_min_lat", "bbox_max_lon", "bbox_max_lat", "srid",
        ], run=run, rule_id="admin_boundary_conflicting_duplicate",
    )
    return boundaries, duplicates


def transform(spark, batch, run, dataset_id, source_version, snapshot_date, preferred):
    if batch.dataset_name == OPEN_ADMIN_DATASET:
        admin_with_lineage = read_open_admin(spark, batch, run, snapshot_date)
    else:
        admin_with_lineage = read_provinces_database(spark, batch, run, snapshot_date)

    invalid = admin_with_lineage.filter(
        F.col("admin_code").isNull() | F.col("name_vi").isNull()
        | F.col("unit_type").isNull() | (~F.col("admin_level").isin(1, 2))
        | ((F.col("admin_level") == 1) & F.col("parent_code").isNotNull())
        | ((F.col("admin_level") == 2) & F.col("parent_code").isNull())
    )
    bad = invalid.limit(100).collect()
    if bad:
        write_quality_issues(spark, run, ({
            "source_file": row.source_file, "record_key": row.admin_code,
            "rule_id": "admin_unit_contract", "issue_type": "invalid_hierarchy",
            "severity": "fatal", "description": "Administrative identity/name/hierarchy is invalid.",
        } for row in bad))
        raise DataQualityError("Administrative unit validation failed")

    admin_columns = spark.table(f"{TABLE_PREFIX}.admin_unit").columns
    admin_units = admin_with_lineage.select(*admin_columns)
    admin_units, admin_duplicates = deduplicate_or_fail(
        spark, admin_units, key_columns=["admin_unit_version_id"],
        compare_columns=[
            "admin_code", "parent_admin_unit_version_id", "parent_code", "admin_level",
            "unit_type", "name_vi", "name_en", "full_name_vi", "full_name_en", "slug",
            "postal_codes", "snapshot_date",
        ], run=run, rule_id="admin_unit_conflicting_duplicate",
    )
    missing_parents = admin_units.filter(F.col("parent_admin_unit_version_id").isNotNull()).join(
        admin_units.select(F.col("admin_unit_version_id").alias("parent_admin_unit_version_id")),
        "parent_admin_unit_version_id", "left_anti",
    ).limit(20).collect()
    if missing_parents:
        write_quality_issues(spark, run, ({
            "record_key": row.admin_code,
            "rule_id": "admin_unit_missing_parent", "issue_type": "missing_reference",
            "severity": "fatal",
            "description": "Administrative unit parent is absent from the same source snapshot.",
        } for row in missing_parents))
        raise DataQualityError("Administrative unit references a parent absent from the same snapshot")

    existing_max = spark.table(f"{TABLE_PREFIX}.admin_unit").groupBy("admin_code").agg(
        F.max("snapshot_date").alias("_existing_snapshot_date")
    )
    admin_units = admin_units.join(existing_max, "admin_code", "left").withColumn(
        "is_current",
        F.when(F.col("_existing_snapshot_date") > F.col("snapshot_date"), F.lit(False))
        .otherwise(F.col("is_current")),
    ).drop("_existing_snapshot_date").select(*admin_columns)

    sources = admin_with_lineage.select(
        "admin_unit_version_id", F.lit(dataset_id).alias("dataset_id"),
        F.col("admin_code").alias("source_admin_code"),
        F.concat(F.lit("json:id="), F.col("admin_code")).alias("source_record_locator"),
        F.lit(source_version).cast("string").alias("source_version"),
        F.lit(snapshot_date).cast("date").alias("source_snapshot_date"),
        "source_file", "source_file_sha256", F.lit(run.run_id).alias("ingestion_run_id"),
        F.lit(preferred).alias("is_preferred_source"),
        F.lit(utc_now()).cast("timestamp").alias("loaded_at"),
    ).dropDuplicates([
        "admin_unit_version_id", "dataset_id", "source_admin_code", "source_record_locator"
    ])

    boundary_result = None
    if batch.dataset_name == PROVINCES_DATASET:
        boundary_result = read_boundaries(
            spark, batch, run, dataset_id, snapshot_date, admin_units
        )

    merge_dataframe(spark, admin_units, f"{TABLE_PREFIX}.admin_unit", ["admin_unit_version_id"])
    merge_dataframe(
        spark, sources, f"{TABLE_PREFIX}.admin_unit_source",
        ["admin_unit_version_id", "dataset_id", "source_admin_code", "source_record_locator"],
    )
    boundary_count = 0
    boundary_duplicates = 0
    if boundary_result:
        boundaries, boundary_duplicates = boundary_result
        merge_dataframe(spark, boundaries, f"{TABLE_PREFIX}.admin_boundary", ["boundary_id"])
        boundary_count = boundaries.count()

    # Snapshot date drives current-version ordering only; it is deliberately
    # not copied into legal valid_from/valid_to dates.
    current_view = f"_current_admin_{run.run_id}"
    admin_units.select("admin_code", "snapshot_date").createOrReplaceTempView(current_view)
    spark.sql(
        f"MERGE INTO {TABLE_PREFIX}.admin_unit t USING {current_view} s "
        "ON t.admin_code=s.admin_code AND t.snapshot_date < s.snapshot_date "
        "WHEN MATCHED THEN UPDATE SET t.is_current=false"
    )
    spark.catalog.dropTempView(current_view)
    return (
        admin_units.count() + boundary_count, admin_units.count() + boundary_count,
        admin_duplicates + boundary_duplicates,
    )


def main():
    args = parse_args()
    spark = create_spark(PIPELINE)
    run = None
    try:
        bootstrap_schema(spark, args.schema_sql)
        batch = load_bronze_batch(spark, args.bronze_path)
        if batch.source != "reference":
            raise ValueError(f"Expected reference Bronze source, got {batch.source}")
        source_version, snapshot_date, source_uri, license_name, preferred = source_contract(
            spark, batch, args.source_version
        )
        dataset_id = register_dataset(
            spark, batch, source_version=source_version, source_uri=source_uri,
            license_name=license_name,
            description="Vietnam administrative names, hierarchy, postal codes and boundaries.",
        )
        run = start_run(spark, batch, dataset_id, PIPELINE)
        if run.skipped:
            return
        input_rows, output_rows, duplicates = transform(
            spark, batch, run, dataset_id, source_version, snapshot_date, preferred
        )
        finish_run(
            spark, run, status="succeeded", input_rows=input_rows, output_rows=output_rows,
            duplicate_rows=duplicates,
        )
    except Exception as exc:
        if run is not None and not run.skipped:
            finish_run(spark, run, status="failed", error_message=str(exc))
        raise
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
