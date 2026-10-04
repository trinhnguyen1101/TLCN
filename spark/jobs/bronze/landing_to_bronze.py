"""Copy original Landing files to MinIO Bronze via Spark's Hadoop S3A client.

The file bytes and names are unchanged. Spark writes provenance as a separate
Parquet dataset; no source schema is inferred or transformed at this layer.
"""

import argparse
import hashlib
import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit
from uuid import uuid4


LOG = logging.getLogger("landing_to_bronze")
DEFAULT_LANDING = Path("/opt/spark/work-dir/landing")
SAFE_COMPONENT = re.compile(r"^[A-Za-z0-9_-]+$")
BUFFER_BYTES = 1024 * 1024


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True, help="Path below Landing, e.g. CAMS/EAC4")
    parser.add_argument("--landing-root", type=Path, default=DEFAULT_LANDING)
    parser.add_argument("--batch-id", help="Stable ID to resume or verify a batch")
    parser.add_argument("--ingestion-date", help="UTC partition date YYYY-MM-DD to resume a batch")
    parser.add_argument("--check-only", action="store_true", help="Validate local input without Spark or MinIO")
    return parser.parse_args()


def dataset_parts(value):
    if "\\" in value or value.startswith("/"):
        raise ValueError("--dataset must be a relative POSIX path")
    parts = PurePosixPath(value).parts
    if len(parts) < 2 or any(not SAFE_COMPONENT.fullmatch(part) for part in parts):
        raise ValueError("--dataset needs source/dataset with safe path components")
    return parts


def inventory(landing_root, parts):
    root = landing_root.resolve(strict=True)
    dataset_root = root.joinpath(*parts)
    if not dataset_root.is_dir() or dataset_root.is_symlink():
        raise ValueError(f"Dataset directory not found: {dataset_root}")
    paths = []
    for current, dirs, names in os.walk(dataset_root, followlinks=False):
        for name in dirs + names:
            path = Path(current, name)
            if path.is_symlink():
                raise ValueError(f"Landing symlink is not supported: {path}")
        for name in names:
            path = Path(current, name)
            if not path.is_file():
                raise ValueError(f"Not a regular Landing file: {path}")
            paths.append(path)
    if not paths:
        raise ValueError(f"No input files under {dataset_root}")

    specs = []
    fingerprint = hashlib.sha256()
    for path in sorted(paths, key=lambda item: item.relative_to(root).as_posix()):
        relative = path.relative_to(root).as_posix()
        within_dataset = path.relative_to(dataset_root).as_posix()
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(BUFFER_BYTES), b""):
                digest.update(chunk)
        stat = path.stat()
        specs.append((str(path), relative, within_dataset, stat.st_size, digest.hexdigest(), stat.st_mtime))
        fingerprint.update(json.dumps([relative, stat.st_size, digest.hexdigest()], ensure_ascii=False).encode("utf-8"))
        fingerprint.update(b"\n")
    return root, specs, fingerprint.hexdigest()


def hadoop_path(spark, uri):
    return spark._jvm.org.apache.hadoop.fs.Path(uri)


def configure_minio(spark):
    user = os.environ.get("MINIO_ROOT_USER")
    password = os.environ.get("MINIO_ROOT_PASSWORD")
    if not user or not password:
        raise RuntimeError("MINIO_ROOT_USER and MINIO_ROOT_PASSWORD are required")
    warehouse = spark.conf.get("spark.sql.catalog.nessie.warehouse", "")
    parsed = urlsplit(warehouse)
    if parsed.scheme != "s3a" or not parsed.netloc:
        raise RuntimeError("Nessie warehouse must be configured as an s3a:// bucket")
    conf = spark.sparkContext._jsc.hadoopConfiguration()
    endpoint = conf.get("fs.s3a.endpoint")
    if not endpoint or "${" in endpoint:
        raise RuntimeError("fs.s3a.endpoint is missing from spark-defaults.conf")
    conf.set("fs.s3a.access.key", user)
    conf.set("fs.s3a.secret.key", password)
    conf.set("fs.s3a.aws.credentials.provider", "org.apache.hadoop.fs.s3a.SimpleAWSCredentialsProvider")
    bucket_uri = f"s3a://{parsed.netloc}/"
    bucket_path = hadoop_path(spark, bucket_uri)
    fs = bucket_path.getFileSystem(conf)
    if not fs.exists(bucket_path):
        raise RuntimeError(f"MinIO bucket is unavailable: {bucket_uri}")
    LOG.info("MinIO connection OK: endpoint=%s bucket=%s", endpoint, parsed.netloc)
    return fs, bucket_uri


def remote_sha256(spark, fs, path):
    jvm = spark._jvm
    digest = jvm.java.security.MessageDigest.getInstance("SHA-256")
    source = jvm.java.security.DigestInputStream(fs.open(path), digest)
    sink = jvm.java.io.OutputStream.nullOutputStream()
    jvm.org.apache.hadoop.io.IOUtils.copyBytes(source, sink, BUFFER_BYTES, True)
    return bytes(value & 0xFF for value in digest.digest()).hex()


def copy_and_verify(spark, fs, specs, output):
    jvm = spark._jvm
    for local, source_file, within_dataset, size, expected_sha256, _ in specs:
        target = hadoop_path(spark, f"{output}/files/{within_dataset}")
        if not fs.exists(target):
            source = jvm.java.io.FileInputStream(local)
            try:
                sink = fs.create(target, False)
            except Exception:
                source.close()
                raise
            jvm.org.apache.hadoop.io.IOUtils.copyBytes(source, sink, BUFFER_BYTES, True)
        if fs.getFileStatus(target).getLen() != size or remote_sha256(spark, fs, target) != expected_sha256:
            raise RuntimeError(f"Bronze object differs from Landing; batch stopped at {source_file}")
    LOG.info("Verified %d original files and their SHA-256 hashes from MinIO", len(specs))


def main():
    args = parse_args()
    parts = dataset_parts(args.dataset)
    landing_root, specs, fingerprint = inventory(args.landing_root, parts)
    total_bytes = sum(spec[3] for spec in specs)
    LOG.info("Input %s: %d files, %d bytes, fingerprint=%s", args.dataset, len(specs), total_bytes, fingerprint)
    if args.check_only:
        return

    batch_id = args.batch_id or uuid4().hex
    if not SAFE_COMPONENT.fullmatch(batch_id):
        raise ValueError("--batch-id may contain only letters, digits, underscores and hyphens")
    ingestion_date = args.ingestion_date or datetime.now(timezone.utc).date().isoformat()
    try:
        if datetime.strptime(ingestion_date, "%Y-%m-%d").date().isoformat() != ingestion_date:
            raise ValueError
    except ValueError as exc:
        raise ValueError("--ingestion-date must be a valid YYYY-MM-DD date") from exc

    from pyspark.sql import SparkSession, types as T

    spark = SparkSession.builder.appName("landing-to-bronze").getOrCreate()
    spark.sparkContext.setLogLevel("ERROR")
    spark.conf.set("spark.sql.session.timeZone", "UTC")
    try:
        fs, bucket_uri = configure_minio(spark)
        source = parts[0].lower()
        dataset = "/".join(part.lower() for part in parts[1:])
        output = f"{bucket_uri}bronze/{source}/{dataset}/ingestion_date={ingestion_date}/batch_id={batch_id}"
        manifest = f"{output}/_ingestion_manifest"
        metadata = f"{output}/_file_metadata"
        manifest_success = hadoop_path(spark, f"{manifest}/_SUCCESS")
        metadata_success = hadoop_path(spark, f"{metadata}/_SUCCESS")

        if fs.exists(manifest_success):
            old = spark.read.json(manifest).first()
            if not old or old.input_fingerprint != fingerprint or old.file_count != len(specs):
                raise RuntimeError(f"Batch ID already belongs to different input: {output}")
            if not fs.exists(metadata_success):
                raise RuntimeError(f"Batch manifest exists but file metadata is missing: {output}")
            copy_and_verify(spark, fs, specs, output)
            LOG.info("Batch already complete; verified without rewriting: %s", output)
            return

        ingested_at = datetime.now(timezone.utc)
        copy_and_verify(spark, fs, specs, output)
        rows = [(
            relative, within_dataset, source, dataset, Path(within_dataset).suffix.lower().lstrip("."),
            size, file_sha256, datetime.fromtimestamp(modified, timezone.utc),
            ingested_at, datetime.strptime(ingestion_date, "%Y-%m-%d").date(), batch_id,
            f"{output}/files/{within_dataset}",
        ) for _, relative, within_dataset, size, file_sha256, modified in specs]
        schema = T.StructType([
            T.StructField("source_file", T.StringType(), False),
            T.StructField("relative_file", T.StringType(), False),
            T.StructField("source", T.StringType(), False),
            T.StructField("dataset", T.StringType(), False),
            T.StructField("file_format", T.StringType(), False),
            T.StructField("file_size", T.LongType(), False),
            T.StructField("file_sha256", T.StringType(), False),
            T.StructField("modification_time", T.TimestampType(), False),
            T.StructField("ingestion_timestamp", T.TimestampType(), False),
            T.StructField("ingestion_date", T.DateType(), False),
            T.StructField("batch_id", T.StringType(), False),
            T.StructField("bronze_object", T.StringType(), False),
        ])
        metadata_mode = "overwrite" if fs.exists(hadoop_path(spark, metadata)) else "errorifexists"
        spark.createDataFrame(rows, schema).write.mode(metadata_mode).parquet(metadata)
        stored = spark.read.parquet(metadata).select("source_file", "file_size", "file_sha256").collect()
        expected = {relative: (size, file_sha256) for _, relative, _, size, file_sha256, _ in specs}
        if len(stored) != len(specs) or {r.source_file: (r.file_size, r.file_sha256) for r in stored} != expected:
            raise RuntimeError(f"Bronze file metadata verification failed: {metadata}")

        manifest_row = [(
            1, source, dataset, batch_id, ingestion_date, ingested_at.isoformat(),
            len(specs), total_bytes, fingerprint, str(landing_root), output,
        )]
        manifest_columns = [
            "schema_version", "source", "dataset", "batch_id", "ingestion_date",
            "ingestion_timestamp", "file_count", "total_bytes", "input_fingerprint",
            "landing_root", "bronze_path",
        ]
        manifest_mode = "overwrite" if fs.exists(hadoop_path(spark, manifest)) else "errorifexists"
        spark.createDataFrame(manifest_row, manifest_columns).coalesce(1).write.mode(manifest_mode).json(manifest)
        LOG.info("Completed Bronze batch: %s", output)
    finally:
        spark.stop()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    try:
        main()
    except Exception:
        LOG.exception("Landing to Bronze failed")
        raise
