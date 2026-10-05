"""Shared Bronze -> Silver helpers for Spark 3.5 and Apache Iceberg.

The Bronze contract is the immutable raw-file layout produced by
``landing_to_bronze.py``.  Jobs consume only ``files/`` and its two sidecars;
they never fall back to the host Landing directory.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import PurePosixPath
from typing import Iterable, Sequence
from uuid import uuid4

from pyspark.sql import DataFrame, SparkSession, functions as F, types as T


CATALOG = "nessie"
NAMESPACE = "silver"
TABLE_PREFIX = f"{CATALOG}.{NAMESPACE}"
PIPELINE_VERSION = "1.0.0"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class DataQualityError(RuntimeError):
    """Raised when continuing would choose one conflicting/invalid record."""


@dataclass(frozen=True)
class BronzeBatch:
    bronze_path: str
    source: str
    dataset_name: str
    batch_id: str
    ingestion_date: date
    ingestion_timestamp: datetime
    input_fingerprint: str
    file_count: int
    landing_root: str | None
    metadata: DataFrame


@dataclass(frozen=True)
class RunContext:
    run_id: str
    logical_run_id: str
    attempt_number: int
    dataset_id: str
    started_at: datetime
    skipped: bool = False


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _normalized_component(value, *, lowercase: bool = False) -> str:
    if value is None:
        result = ""
    elif isinstance(value, (date, datetime)):
        result = value.isoformat()
    else:
        result = unicodedata.normalize("NFC", str(value).strip())
    return result.lower() if lowercase else result


def sha256_json(namespace: str, *components) -> str:
    """Return the README contract's compact UTF-8 JSON SHA-256 identity."""
    values = [_normalized_component(namespace)]
    values.extend(_normalized_component(value) for value in components)
    payload = json.dumps(values, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@F.udf(T.StringType())
def sha256_json_udf(namespace, *components):
    return sha256_json(namespace, *components)


def deterministic_id(namespace: str, *columns) -> F.Column:
    return sha256_json_udf(F.lit(namespace), *columns)


def create_spark(app_name: str) -> SparkSession:
    spark = SparkSession.builder.appName(app_name).getOrCreate()
    spark.sparkContext.setLogLevel("WARN")
    spark.conf.set("spark.sql.session.timeZone", "UTC")
    return spark


def bootstrap_schema(spark: SparkSession, schema_sql: str) -> None:
    """Execute the checked-in Spark SQL schema one statement at a time."""
    with open(schema_sql, "r", encoding="utf-8") as handle:
        sql_text = handle.read()
    sql_text = "\n".join(
        line for line in sql_text.splitlines() if not line.lstrip().startswith("--")
    )
    for statement in sql_text.split(";"):
        if statement.strip():
            spark.sql(statement)


def _hadoop_path(spark: SparkSession, value: str):
    return spark._jvm.org.apache.hadoop.fs.Path(value)


def _require_success_marker(spark: SparkSession, path: str) -> None:
    hadoop_path = _hadoop_path(spark, path)
    fs = hadoop_path.getFileSystem(spark.sparkContext._jsc.hadoopConfiguration())
    if not fs.exists(hadoop_path):
        raise ValueError(f"Incomplete Bronze batch; missing {path}")


def _parse_utc_timestamp(value) -> datetime:
    if isinstance(value, datetime):
        return value.replace(tzinfo=value.tzinfo or timezone.utc)
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed.replace(tzinfo=parsed.tzinfo or timezone.utc)


def _valid_source_file(value: str) -> bool:
    if not value or "\\" in value or value.startswith("/"):
        return False
    parts = PurePosixPath(value).parts
    return bool(parts) and all(part not in {"", ".", ".."} for part in parts)


def load_bronze_batch(spark: SparkSession, bronze_path: str) -> BronzeBatch:
    """Load and validate one complete Bronze batch and its per-file metadata."""
    base = bronze_path.rstrip("/")
    if not base.startswith("s3a://") or "/../" in f"/{base}/":
        raise ValueError("--bronze-path must be a normalized s3a:// Bronze batch path")
    _require_success_marker(spark, f"{base}/_ingestion_manifest/_SUCCESS")
    _require_success_marker(spark, f"{base}/_file_metadata/_SUCCESS")

    manifests = spark.read.json(f"{base}/_ingestion_manifest").collect()
    if len(manifests) != 1:
        raise ValueError(f"Expected one Bronze manifest row, found {len(manifests)}")
    manifest = manifests[0].asDict(recursive=True)
    required_manifest = {
        "source", "dataset", "batch_id", "ingestion_date", "ingestion_timestamp",
        "file_count", "input_fingerprint", "bronze_path",
    }
    missing = required_manifest.difference(manifest)
    if missing:
        raise ValueError(f"Bronze manifest missing fields: {sorted(missing)}")
    if manifest["bronze_path"].rstrip("/") != base:
        raise ValueError("Bronze manifest path does not match --bronze-path")
    if not SHA256_RE.fullmatch(str(manifest["input_fingerprint"])):
        raise ValueError("Bronze input_fingerprint is not lowercase SHA-256")

    raw_metadata = spark.read.parquet(f"{base}/_file_metadata")
    required_metadata = {
        "source_file", "relative_file", "source", "dataset", "file_format",
        "file_size", "file_sha256", "ingestion_timestamp", "ingestion_date",
        "batch_id", "bronze_object",
    }
    missing = required_metadata.difference(raw_metadata.columns)
    if missing:
        raise ValueError(f"Bronze _file_metadata missing fields: {sorted(missing)}")

    # landing_to_bronze.py calls the Landing-root-relative value source_file.
    # Silver's contract instead requires the path relative to <batch>/files/,
    # which is the Bronze sidecar's relative_file field.
    metadata = (
        raw_metadata.withColumnRenamed("source_file", "landing_source_file")
        .withColumnRenamed("relative_file", "source_file")
    )
    invalid = metadata.filter(
        (~F.col("file_sha256").rlike("^[0-9a-f]{64}$"))
        | (F.col("file_size") < 0)
        | (F.col("batch_id") != F.lit(str(manifest["batch_id"])))
        | (F.col("source") != F.lit(str(manifest["source"])))
        | (F.col("dataset") != F.lit(str(manifest["dataset"])))
    ).limit(1).count()
    if invalid:
        raise ValueError("Bronze _file_metadata failed SHA/path/batch validation")
    bad_paths = [row.source_file for row in metadata.select("source_file").collect()
                 if not _valid_source_file(row.source_file)]
    if bad_paths:
        raise ValueError(f"Invalid Bronze relative source path: {bad_paths[0]!r}")
    actual_count = metadata.count()
    if actual_count != int(manifest["file_count"]):
        raise ValueError(
            f"Bronze manifest file_count={manifest['file_count']} but metadata has {actual_count}"
        )

    ingestion_date = datetime.strptime(str(manifest["ingestion_date"]), "%Y-%m-%d").date()
    return BronzeBatch(
        bronze_path=base,
        source=str(manifest["source"]).strip().lower(),
        dataset_name=str(manifest["dataset"]).strip(),
        batch_id=str(manifest["batch_id"]),
        ingestion_date=ingestion_date,
        ingestion_timestamp=_parse_utc_timestamp(manifest["ingestion_timestamp"]),
        input_fingerprint=str(manifest["input_fingerprint"]),
        file_count=actual_count,
        landing_root=manifest.get("landing_root"),
        metadata=metadata,
    )


def _sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def merge_dataframe(
    spark: SparkSession,
    dataframe: DataFrame,
    table: str,
    key_columns: Sequence[str],
    *,
    update: bool = True,
) -> None:
    """MERGE a DataFrame into one Iceberg table using an explicit logical key."""
    table_columns = spark.table(table).columns
    missing = set(table_columns).difference(dataframe.columns)
    extra = set(dataframe.columns).difference(table_columns)
    if missing or extra:
        raise ValueError(f"Schema mismatch for {table}: missing={sorted(missing)}, extra={sorted(extra)}")
    view = f"_merge_{table.rsplit('.', 1)[-1]}_{uuid4().hex}"
    dataframe.select(*table_columns).createOrReplaceTempView(view)
    condition = " AND ".join(f"t.`{key}` <=> s.`{key}`" for key in key_columns)
    matched = "WHEN MATCHED THEN UPDATE SET *" if update else ""
    spark.sql(
        f"MERGE INTO {table} t USING {view} s ON {condition} "
        f"{matched} WHEN NOT MATCHED THEN INSERT *"
    )
    spark.catalog.dropTempView(view)


def register_dataset(
    spark: SparkSession,
    batch: BronzeBatch,
    *,
    source_version: str | None = None,
    source_uri: str | None = None,
    license_name: str | None = None,
    description: str | None = None,
) -> str:
    dataset_id = sha256_json(
        "silver-dataset-v1", batch.source.lower(), batch.dataset_name, source_version or ""
    )
    schema = spark.table(f"{TABLE_PREFIX}.dataset").schema
    row = [(
        dataset_id, batch.dataset_name, batch.source.lower(), source_version,
        source_uri, batch.landing_root, license_name, batch.ingestion_timestamp,
        utc_now(), description,
    )]
    dataframe = spark.createDataFrame(row, schema)
    merge_dataframe(
        spark, dataframe, f"{TABLE_PREFIX}.dataset",
        ["source_system", "dataset_name", "source_version"],
    )
    return dataset_id


def start_run(
    spark: SparkSession,
    batch: BronzeBatch,
    dataset_id: str,
    pipeline_name: str,
    *,
    pipeline_version: str = PIPELINE_VERSION,
) -> RunContext:
    pipeline_name = pipeline_name.strip().lower()
    logical_id = sha256_json(
        "silver-run-v1", dataset_id, batch.batch_id, pipeline_name, pipeline_version
    )
    succeeded = spark.sql(
        f"SELECT run_id, attempt_number, started_at FROM {TABLE_PREFIX}.ingestion_run "
        f"WHERE logical_run_id={_sql_literal(logical_id)} AND status='succeeded' LIMIT 1"
    ).collect()
    if succeeded:
        row = succeeded[0]
        return RunContext(row.run_id, logical_id, row.attempt_number, dataset_id, row.started_at, True)

    max_attempt = spark.sql(
        f"SELECT coalesce(max(attempt_number), 0) AS n FROM {TABLE_PREFIX}.ingestion_run "
        f"WHERE logical_run_id={_sql_literal(logical_id)}"
    ).first().n
    context = RunContext(uuid4().hex, logical_id, int(max_attempt) + 1, dataset_id, utc_now())
    schema = spark.table(f"{TABLE_PREFIX}.ingestion_run").schema
    row = [(
        context.run_id, context.logical_run_id, context.attempt_number, dataset_id,
        batch.batch_id, batch.ingestion_date, batch.bronze_path, batch.input_fingerprint,
        pipeline_name, pipeline_version, context.started_at, None, batch.file_count,
        None, None, 0, 0, 0, "running", None, context.started_at,
    )]
    merge_dataframe(
        spark, spark.createDataFrame(row, schema), f"{TABLE_PREFIX}.ingestion_run", ["run_id"]
    )
    return context


def finish_run(
    spark: SparkSession,
    run: RunContext,
    *,
    status: str,
    input_rows: int | None = None,
    output_rows: int | None = None,
    duplicate_rows: int = 0,
    invalid_rows: int = 0,
    quarantined_rows: int = 0,
    error_message: str | None = None,
) -> None:
    if status not in {"succeeded", "failed", "partial"}:
        raise ValueError(f"Invalid terminal run status: {status}")
    finished = utc_now().replace(tzinfo=None).isoformat(sep=" ")
    error_sql = "NULL" if error_message is None else _sql_literal(error_message[:4000])
    values = {
        "input_rows": "NULL" if input_rows is None else str(int(input_rows)),
        "output_rows": "NULL" if output_rows is None else str(int(output_rows)),
        "duplicate_rows": str(int(duplicate_rows)),
        "invalid_rows": str(int(invalid_rows)),
        "quarantined_rows": str(int(quarantined_rows)),
    }
    spark.sql(
        f"UPDATE {TABLE_PREFIX}.ingestion_run SET "
        f"finished_at=TIMESTAMP {_sql_literal(finished)}, status={_sql_literal(status)}, "
        f"input_rows={values['input_rows']}, output_rows={values['output_rows']}, "
        f"duplicate_rows={values['duplicate_rows']}, invalid_rows={values['invalid_rows']}, "
        f"quarantined_rows={values['quarantined_rows']}, error_message={error_sql} "
        f"WHERE run_id={_sql_literal(run.run_id)}"
    )


def write_quality_issues(
    spark: SparkSession,
    run: RunContext,
    rows: Iterable[dict],
) -> int:
    now = utc_now()
    prepared = []
    for row in rows:
        source_file = row.get("source_file")
        locator = row.get("source_record_locator")
        column = row.get("column_name")
        rule_id = row["rule_id"]
        prepared.append((
            sha256_json("silver-dq-issue-v1", run.run_id, rule_id, source_file, locator, column),
            run.run_id, run.dataset_id, now, source_file, locator, row.get("record_key"),
            column, rule_id, row.get("issue_type", "invalid_value"),
            row.get("severity", "error"), row.get("description"),
            row.get("original_value"), row.get("normalized_value"), row.get("raw_record_json"),
        ))
    if not prepared:
        return 0
    schema = spark.table(f"{TABLE_PREFIX}.data_quality_issue").schema
    merge_dataframe(
        spark, spark.createDataFrame(prepared, schema),
        f"{TABLE_PREFIX}.data_quality_issue", ["issue_id"],
    )
    return len(prepared)


def deduplicate_or_fail(
    spark: SparkSession,
    dataframe: DataFrame,
    *,
    key_columns: Sequence[str],
    compare_columns: Sequence[str],
    run: RunContext,
    rule_id: str,
) -> tuple[DataFrame, int]:
    """Remove exact duplicates and reject conflicting rows sharing a key."""
    input_count = dataframe.count()
    exact = dataframe.dropDuplicates(list(key_columns) + list(compare_columns))
    exact_count = exact.count()
    signature = F.to_json(F.struct(*[F.col(name) for name in compare_columns]))
    conflicts = (
        exact.groupBy(*key_columns)
        .agg(F.countDistinct(signature).alias("variants"))
        .filter(F.col("variants") > 1)
    )
    samples = conflicts.limit(20).collect()
    if samples:
        issues = []
        for row in samples:
            key = {name: row[name] for name in key_columns}
            issues.append({
                "rule_id": rule_id,
                "issue_type": "conflicting_duplicate",
                "severity": "fatal",
                "record_key": json.dumps(key, ensure_ascii=False, default=str, separators=(",", ":")),
                "description": "Logical key has multiple distinct non-key payloads; no row was selected.",
            })
        write_quality_issues(spark, run, issues)
        raise DataQualityError(f"{rule_id}: found conflicting duplicate logical keys")
    return exact.dropDuplicates(list(key_columns)), input_count - exact_count


def trim_strings(dataframe: DataFrame) -> DataFrame:
    """Trim all string cells and convert blanks to NULL without touching numerics."""
    result = dataframe
    for field in dataframe.schema.fields:
        if isinstance(field.dataType, T.StringType):
            trimmed = F.trim(F.col(f"`{field.name}`"))
            result = result.withColumn(field.name, F.when(trimmed == "", None).otherwise(trimmed))
    return result


def normalize_column_names(dataframe: DataFrame) -> DataFrame:
    result = dataframe
    seen = set()
    for original in dataframe.columns:
        normalized = unicodedata.normalize("NFC", original.lstrip("\ufeff").strip())
        if not normalized or normalized in seen:
            raise ValueError(f"Invalid/duplicate normalized source column: {original!r}")
        seen.add(normalized)
        if original != normalized:
            result = result.withColumnRenamed(original, normalized)
    return result


def assert_required_columns(dataframe: DataFrame, required: Sequence[str], source_file: str) -> None:
    missing = set(required).difference(dataframe.columns)
    if missing:
        raise ValueError(f"{source_file} missing required columns: {sorted(missing)}")


def metadata_rows(batch: BronzeBatch, extensions: Sequence[str] | None = None):
    query = batch.metadata
    if extensions:
        query = query.filter(F.lower(F.col("file_format")).isin([x.lower() for x in extensions]))
    return query.collect()

