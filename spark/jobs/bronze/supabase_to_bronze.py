"""Copy completed Supabase collection runs to an immutable MinIO Bronze batch.

The database selects runs; the private Storage bucket supplies original bytes.
No source response is parsed or rewritten at this layer.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import PurePosixPath
from urllib.parse import parse_qs, quote, urlsplit
from urllib.request import Request, urlopen

SAFE = re.compile(r"^[A-Za-z0-9_-]+$")
SHA = re.compile(r"^[0-9a-f]{64}$")
DATASETS = {"waqi": "live", "api_ninjas": "province_air_quality"}


def utc(value):
    result = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("Timestamp must include UTC offset")
    return result.astimezone(timezone.utc)


def settings():
    jdbc = os.environ["AWS_CONNECTION_STRING"]
    key = os.environ["AWS_SECRET_KEY"]
    if not jdbc.startswith("jdbc:postgresql://") or not key:
        raise ValueError("Expected JDBC PostgreSQL URL and nonempty Storage secret")
    uri = urlsplit(jdbc[5:])
    parameters = parse_qs(uri.query, strict_parsing=True)
    user, password = parameters["user"][0], parameters["password"][0]
    if not user.startswith("postgres.") or not re.fullmatch(r"[a-z0-9]+", user[9:]):
        raise ValueError("Cannot derive Supabase project ref from JDBC username")
    return {
        "host": uri.hostname, "port": uri.port or 5432,
        "dbname": uri.path.lstrip("/"), "user": user, "password": password,
    }, "https://" + user[9:] + ".supabase.co", key


def storage_get(base_url, key, path):
    request = Request(
        base_url + "/storage/v1/object/authenticated/raw-api/" + quote(path, safe="/"),
        headers={"apikey": key, "Authorization": "Bearer " + key},
    )
    with urlopen(request, timeout=30) as response:
        return response.read()


def source_path(path, source, run_id, hour):
    parts = PurePosixPath(path).parts
    prefix = (source, hour.strftime("%Y"), hour.strftime("%m"), hour.strftime("%d"), hour.strftime("%H"), run_id)
    if (len(parts) != 7 or parts[:6] != prefix or PurePosixPath(path).as_posix() != path
            or any(part in {".", "..", ""} for part in parts)):
        raise ValueError("Storage path is outside its declared collection run")
    if parts[6] != "manifest.json" and not re.fullmatch(r"[A-Za-z0-9_-]+\.raw\.json", parts[6]):
        raise ValueError("Unexpected Storage object filename")
    return "/".join(parts[1:])


def verified_manifest(run, source, base_url, key):
    run_id = str(run["run_id"])
    hour = utc(run["scheduled_hour_utc"])
    path = run["manifest_object_path"]
    if not path or source_path(path, source, run_id, hour).split("/")[-1] != "manifest.json":
        raise ValueError("Run has no valid manifest path")
    payload = storage_get(base_url, key, path)
    if not SHA.fullmatch(str(run["manifest_sha256"])) or hashlib.sha256(payload).hexdigest() != run["manifest_sha256"]:
        raise ValueError("Supabase manifest SHA-256 mismatch")
    manifest = json.loads(payload)
    expected = {"source": source, "collection_run_id": run_id, "attempt_number": run["attempt_number"],
                "status": run["status"], "expected_records": run["expected_records"],
                "successful_records": run["successful_records"], "failed_records": run["failed_records"]}
    if any(manifest.get(k) != v for k, v in expected.items()) or utc(manifest["scheduled_hour_utc"]) != hour:
        raise ValueError("Manifest disagrees with collection_runs")
    records = manifest.get("records")
    if not isinstance(records, list) or len(records) != run["expected_records"]:
        raise ValueError("Manifest target count mismatch")
    successes = sum(r.get("outcome") in {"valid", "partial"} for r in records)
    if successes != run["successful_records"] or len(records) - successes != run["failed_records"]:
        raise ValueError("Manifest outcome counts mismatch")
    target_key = "requested_source_uid" if source == "waqi" else "location_key"
    identities = [r.get(target_key) for r in records]
    if any(not v for v in identities) or len(set(identities)) != len(identities):
        raise ValueError("Missing or repeated manifest target")
    objects = [(path, payload, run["manifest_sha256"])]
    seen = {path}
    for record in records:
        raw_path = record.get("raw_object_path")
        if source == "waqi" and raw_path and record.get("raw_stored") is not True:
            if record.get("outcome") in {"valid", "partial"}:
                raise ValueError("Successful WAQI target has no stored raw object")
            continue
        if not raw_path:
            if record.get("outcome") in {"valid", "partial"}:
                raise ValueError("Successful target has no raw object")
            continue
        suffix = source_path(raw_path, source, run_id, hour).split("/")[-1]
        if suffix != str(record[target_key]) + ".raw.json" or raw_path in seen:
            raise ValueError("Raw path/target mismatch or duplicate")
        seen.add(raw_path)
        raw = storage_get(base_url, key, raw_path)
        digest = record.get("payload_sha256")
        if not SHA.fullmatch(str(digest)) or hashlib.sha256(raw).hexdigest() != digest:
            raise ValueError("Raw object SHA-256 mismatch")
        objects.append((raw_path, raw, digest))
    return objects


def inventory(runs, source, base_url, key):
    objects = {}
    for run in runs:
        for path, payload, digest in verified_manifest(run, source, base_url, key):
            relative = source_path(path, source, str(run["run_id"]), utc(run["scheduled_hour_utc"]))
            if relative in objects:
                raise ValueError("Duplicate Bronze relative path")
            objects[relative] = (path, payload, digest)
    if not objects:
        raise ValueError("No completed collection runs in requested window")
    fingerprint = hashlib.sha256()
    for relative, (_, payload, digest) in sorted(objects.items()):
        fingerprint.update(json.dumps([relative, len(payload), digest], ensure_ascii=False).encode("utf-8") + b"\n")
    return objects, fingerprint.hexdigest()


def hpath(spark, path):
    return spark._jvm.org.apache.hadoop.fs.Path(path)


def verified_copy(spark, fs, destination, payload):
    target = hpath(spark, destination)
    digest = hashlib.sha256(payload).hexdigest()
    if not fs.exists(target):
        with tempfile.NamedTemporaryFile(prefix="supabase-bronze-") as staged:
            staged.write(payload)
            staged.flush()
            source = spark._jvm.java.io.FileInputStream(staged.name)
            try:
                sink = fs.create(target, False)
            except Exception:
                source.close()
                raise
            spark._jvm.org.apache.hadoop.io.IOUtils.copyBytes(source, sink, 1024 * 1024, True)
    if fs.getFileStatus(target).getLen() != len(payload):
        raise ValueError("Bronze object size mismatch")
    from landing_to_bronze import remote_sha256
    if remote_sha256(spark, fs, target) != digest:
        raise ValueError("Bronze object SHA-256 mismatch")


def write_batch(spark, source, batch_id, ingestion_date, runs, objects, fingerprint, start, end):
    from landing_to_bronze import configure_minio
    from pyspark.sql import types as T

    fs, bucket = configure_minio(spark)
    dataset = DATASETS[source]
    output = f"{bucket}bronze/{source}/{dataset}/ingestion_date={ingestion_date}/batch_id={batch_id}"
    manifest_path = output + "/_ingestion_manifest"
    metadata_path = output + "/_file_metadata"
    committed = fs.exists(hpath(spark, manifest_path + "/_SUCCESS"))
    if committed:
        old = spark.read.json(manifest_path).first()
        if not old or old.input_fingerprint != fingerprint or old.file_count != len(objects):
            raise ValueError("Completed batch ID belongs to different input")
        if not fs.exists(hpath(spark, metadata_path + "/_SUCCESS")):
            raise ValueError("Completed batch has missing file metadata")
    ingested = datetime.now(timezone.utc)
    for relative, (_, payload, _) in sorted(objects.items()):
        verified_copy(spark, fs, output + "/files/" + relative, payload)
    if committed:
        stored = spark.read.parquet(metadata_path).select("relative_file", "file_sha256", "file_size").collect()
        if {r.relative_file: (r.file_sha256, r.file_size) for r in stored} != {
                p: (v[2], len(v[1])) for p, v in objects.items()} or len(stored) != len(objects):
            raise ValueError("Completed batch metadata mismatch")
    else:
        rows = [(original, relative, source, dataset, "json", len(payload), digest,
             ingested, ingested, datetime.strptime(ingestion_date, "%Y-%m-%d").date(),
             batch_id, output + "/files/" + relative)
            for relative, (original, payload, digest) in sorted(objects.items())]
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
        spark.createDataFrame(rows, schema).write.mode("overwrite" if fs.exists(hpath(spark, metadata_path)) else "errorifexists").parquet(metadata_path)
        stored = spark.read.parquet(metadata_path).select("relative_file", "file_sha256", "file_size").collect()
        if len(stored) != len(rows) or {r.relative_file: (r.file_sha256, r.file_size) for r in stored} != {
                p: (v[2], len(v[1])) for p, v in objects.items()}:
            raise ValueError("Bronze file metadata verification failed")
        manifest = [(1, source, dataset, batch_id, ingestion_date, ingested.isoformat(),
                 len(rows), sum(len(v[1]) for v in objects.values()), fingerprint,
                 "supabase://raw-api", output)]
        names = ["schema_version", "source", "dataset", "batch_id", "ingestion_date",
             "ingestion_timestamp", "file_count", "total_bytes", "input_fingerprint",
             "landing_root", "bronze_path"]
        spark.createDataFrame(manifest, names).coalesce(1).write.mode("overwrite" if fs.exists(hpath(spark, manifest_path)) else "errorifexists").json(manifest_path)
    if not fs.exists(hpath(spark, manifest_path + "/_SUCCESS")):
        raise ValueError("Bronze manifest commit marker missing")
    last = runs[-1]
    checkpoint = {
        "source": source, "window_start_utc": start.isoformat(), "window_end_utc": end.isoformat(),
        "last_completed_run_id": str(last["run_id"]),
        "last_scheduled_hour_utc": utc(last["scheduled_hour_utc"]).isoformat(),
        "bronze_batch_id": batch_id, "object_count": len(objects),
        "input_fingerprint": fingerprint, "completed_at_utc": ingested.isoformat(),
    }
    checkpoint_path = output + "/supabase_checkpoint.json"
    if fs.exists(hpath(spark, checkpoint_path)):
        existing = spark.read.json(checkpoint_path).first().asDict()
        comparable = {key: value for key, value in checkpoint.items() if key != "completed_at_utc"}
        if {key: existing.get(key) for key in comparable} != comparable:
            raise ValueError("Existing Bronze checkpoint differs from requested window")
    else:
        verified_copy(spark, fs, checkpoint_path, json.dumps(checkpoint, sort_keys=True).encode("utf-8"))
    return output


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", choices=DATASETS, required=True)
    parser.add_argument("--window-start", required=True)
    parser.add_argument("--window-end", required=True)
    parser.add_argument("--batch-id")
    parser.add_argument("--ingestion-date")
    return parser.parse_args()


def main():
    args = parse_args()
    if not args.window_start:
        raise ValueError("--window-start is empty; set window_start in this terminal before running Bronze")
    if not args.window_end:
        raise ValueError("--window-end is empty; set window_end in this terminal before running Bronze")
    if args.batch_id is not None and not args.batch_id:
        raise ValueError("--batch-id is empty; set the batch ID in this terminal")
    if args.ingestion_date is not None and not args.ingestion_date:
        raise ValueError("--ingestion-date is empty; set ingestion_date in this terminal")
    import psycopg
    from psycopg.rows import dict_row
    from pyspark.sql import SparkSession

    start, end = utc(args.window_start), utc(args.window_end)
    if start >= end or end > datetime.now(timezone.utc):
        raise ValueError("Expected a completed, nonempty UTC window")
    ingestion_date = args.ingestion_date or datetime.now(timezone.utc).date().isoformat()
    if datetime.strptime(ingestion_date, "%Y-%m-%d").date().isoformat() != ingestion_date:
        raise ValueError("Invalid ingestion date")
    batch_id = args.batch_id or hashlib.sha256(f"{args.source}|{start.isoformat()}|{end.isoformat()}".encode()).hexdigest()[:24]
    if not SAFE.fullmatch(batch_id):
        raise ValueError("Unsafe batch ID")
    db, base_url, key = settings()
    with psycopg.connect(**db, sslmode="require", connect_timeout=15,
                         options="-c default_transaction_read_only=on", row_factory=dict_row) as conn:
        runs = conn.execute(
            "SELECT run_id, source, scheduled_hour_utc, attempt_number, status, expected_records, "
            "successful_records, failed_records, manifest_object_path, manifest_sha256 "
            "FROM public.collection_runs WHERE source=%s AND scheduled_hour_utc >= %s "
            "AND scheduled_hour_utc < %s AND status IN ('succeeded','partial') "
            "ORDER BY scheduled_hour_utc, attempt_number, run_id",
            (args.source, start, end),
        ).fetchall()
    objects, fingerprint = inventory(runs, args.source, base_url, key)
    spark = SparkSession.builder.appName("supabase-to-bronze").getOrCreate()
    spark.conf.set("spark.sql.session.timeZone", "UTC")
    try:
        output = write_batch(spark, args.source, batch_id, ingestion_date, runs, objects, fingerprint, start, end)
        print(f"BRONZE_PATH={output}")
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
