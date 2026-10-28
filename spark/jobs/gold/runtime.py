"""Bounded builds, Silver snapshot pins and immutable release publication."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
from pyspark.sql import SparkSession, functions as F


def identifier(value):
    if not re.fullmatch(r"[a-z][a-z0-9_]*",value):
        raise ValueError("Invalid SQL identifier")
    return value


def stable_id(*parts):
    return hashlib.sha256(json.dumps(parts,ensure_ascii=False,separators=(",",":"),default=str).encode()).hexdigest()


def spark_session(master=None):
    key, secret = os.environ["MINIO_ROOT_USER"], os.environ["MINIO_ROOT_PASSWORD"]
    builder=SparkSession.builder.appName("gold-hourly-v1")
    if master is not None:builder=builder.master(master)
    spark=(builder
           .config("spark.sql.catalog.nessie.s3.access-key-id", key)
           .config("spark.sql.catalog.nessie.s3.secret-access-key", secret)
           .config("spark.hadoop.fs.s3a.access.key",key)
           .config("spark.hadoop.fs.s3a.secret.key",secret)
           .config("spark.sql.session.timeZone","UTC")
           .config("spark.sql.shuffle.partitions","2")
           .config("spark.sql.adaptive.enabled","true").getOrCreate())
    spark.sparkContext.setLogLevel("WARN")
    return spark


def bootstrap(spark, schema, path):
    identifier(schema)
    sql=Path(path).read_text().replace("{{schema}}",schema)
    sql="\n".join(line for line in sql.splitlines() if not line.lstrip().startswith("--"))
    for statement in sql.split(";"):
        if statement.strip():
            spark.sql(statement)


PROVIDER_AQI_COLUMNS = {
    "fact_aqi_pollutant_hourly": [
        ("aqi_origin", "STRING"), ("aqi_provider", "STRING"),
        ("provider_aqi_scheme", "STRING"), ("provider_sub_index", "DOUBLE"),
        ("observed_at_utc", "TIMESTAMP"), ("scheduled_at_utc", "TIMESTAMP"),
        ("collected_at_utc", "TIMESTAMP"), ("observation_time_kind", "STRING"),
    ],
    "fact_aqi_hourly": [
        ("aqi_origin", "STRING"), ("aqi_provider", "STRING"),
        ("provider_aqi_scheme", "STRING"), ("observed_at_utc", "TIMESTAMP"),
        ("scheduled_at_utc", "TIMESTAMP"), ("collected_at_utc", "TIMESTAMP"),
        ("observation_time_kind", "STRING"),
    ],
    "fact_aqi_pollutant_daily": [
        ("aqi_origin", "STRING"), ("aqi_provider", "STRING"),
        ("provider_aqi_scheme", "STRING"),
    ],
    "fact_aqi_daily": [
        ("aqi_origin", "STRING"), ("aqi_provider", "STRING"),
        ("provider_aqi_scheme", "STRING"),
    ],
    "mart_air_quality_hourly": [
        ("aqi_provider", "STRING"), ("provider_aqi_scheme", "STRING"),
    ],
    "mart_air_quality_daily": [
        ("aqi_provider", "STRING"), ("provider_aqi_scheme", "STRING"),
    ],
}


def migrate_provider_aqi_columns(spark, schema):
    """Apply the additive provider-AQI schema extension to an existing catalog.

    CREATE TABLE IF NOT EXISTS does not evolve Iceberg tables. Keeping this
    migration beside bootstrap makes old local catalogs and clean installs use
    the same physical schema without rewriting any published snapshot.
    """
    prefix = "nessie." + identifier(schema) + "."
    for name, additions in PROVIDER_AQI_COLUMNS.items():
        table = prefix + name
        existing = set(spark.table(table).columns)
        for column, data_type in additions:
            if column not in existing:
                spark.sql(f"ALTER TABLE {table} ADD COLUMN {column} {data_type}")
                existing.add(column)


def snapshot(spark,table):
    spark.catalog.refreshTable(table)
    # Iceberg currentSnapshot is the catalog head, including after a table
    # rollback. MAX(committed_at) can select a newer abandoned snapshot.
    iceberg=spark._jvm.org.apache.iceberg.spark.Spark3Util.loadIcebergTable(spark._jsparkSession,table)
    iceberg.refresh()
    current=iceberg.currentSnapshot()
    return int(current.snapshotId()) if current is not None else None


class Build:
    def __init__(self,spark,schema,silver_schema,contract,start,end,channel,code_hash):
        self.spark=spark
        self.schema=identifier(schema)
        self.prefix="nessie."+schema+"."
        self.silver="nessie."+identifier(silver_schema)+"."
        self.contract=contract
        self.start,self.end,self.channel=start,end,channel
        self.inputs={}
        self.frames={}
        self.outputs=[]
        self.metrics={"driver_collect_rows":0,"driver_collect_calls":0}
        self.code_hash=code_hash
        self.contract_hash=stable_id(contract)
        self.release_id=None

    def read(self,name):
        identifier(name)
        if name not in self.frames:
            table=self.silver+name
            snap=snapshot(self.spark,table)
            if snap is None:
                raise ValueError("Required Silver table is empty: "+name)
            self.inputs[table]=snap
            self.frames[name]=self.spark.read.option("snapshot-id",str(snap)).table(table)
        return self.frames[name]

    def identify(self):
        from aqi.reference import METHOD_VERSION
        self.release_id=stable_id("gold-release-v1",self.inputs,self.contract_hash,self.start,
                                 self.end,self.channel,self.code_hash,METHOD_VERSION)
        return self.release_id

    def frame(self,name,rows):
        schema=self.spark.table(self.prefix+name).schema
        return self.spark.createDataFrame(rows,schema)

    def write(self,name,rows):
        frame=rows if hasattr(rows,"writeTo") else self.frame(name,rows)
        # Only unpublished stages can be replaced. Published releases skip in runner.
        table=self.prefix+name
        if "release_id" in frame.columns:
            if frame.filter(F.col("release_id")!=self.release_id).limit(1).count():
                raise ValueError("Cross-release write")
            self.spark.sql("DELETE FROM "+table+" WHERE release_id='"+self.release_id+"'")
        frame.select(*self.spark.table(table).columns).coalesce(1).writeTo(table).append()
        if name not in self.outputs:
            self.outputs.append(name)

    def rows(self,name):
        return self.spark.table(self.prefix+name).filter(F.col("release_id")==self.release_id)

    def publish(self,validation,fail_before_pointer=False,fail_after_registry=False,method_version=None):
        from aqi.reference import METHOD_VERSION
        outputs={name:snapshot(self.spark,self.prefix+name) for name in self.outputs}
        if any(v is None for v in outputs.values()):
            raise ValueError("Missing materialization snapshot")
        # The supported orchestration serializes Silver and Gold writers. Also
        # refuse publication if any pinned Silver head changed during this build.
        for table,pinned in self.inputs.items():
            if snapshot(self.spark,table)!=pinned:
                raise ValueError("Silver input changed during build; replay from new snapshots: "+table)
        now=datetime.now(timezone.utc)
        release=dict(release_id=self.release_id,channel=self.channel,scope_start_utc=self.start,
                     scope_end_utc=self.end,input_snapshots_json=json.dumps(self.inputs,sort_keys=True),
                     output_snapshots_json=json.dumps(outputs,sort_keys=True),method_version=method_version or METHOD_VERSION,
                     contract_sha256=self.contract_hash,code_sha256=self.code_hash,published_at=now,
                     validation_json=json.dumps(validation,sort_keys=True))
        # Failure-injection hook: pointer and release registry remain untouched.
        if fail_before_pointer:
            raise RuntimeError("Injected pre-publication failure")
        self.spark.createDataFrame([release],self.spark.table(self.prefix+"gold_release").schema).createOrReplaceTempView("_release")
        self.spark.sql("MERGE INTO "+self.prefix+"gold_release t USING _release s ON t.release_id=s.release_id WHEN NOT MATCHED THEN INSERT *")
        if fail_after_registry:
            raise RuntimeError("Injected failure after registry, before pointer")
        self.activate(release)
        return release

    def activate(self,release):
        if release['channel'] in ('air_quality','provider_air_quality'):
            from publication import publish,current
            if current(self.spark,self.prefix,release['channel']) is None:
                legacy=self.spark.table(self.prefix+'gold_current_release').where("channel='air_quality'").collect()
                if legacy and legacy[0].release_id!=release['release_id']:
                    previous=self.spark.table(self.prefix+'gold_release').where("release_id='"+legacy[0].release_id+"'").collect()
                    if len(previous)!=1:raise ValueError('Legacy pointer has no registry release')
                    publish(self.spark,self.prefix,previous[0].asDict())
            publish(self.spark,self.prefix,release)
        current={k:release[k] for k in self.spark.table(self.prefix+"gold_current_release").columns}
        self.spark.createDataFrame([current],self.spark.table(self.prefix+"gold_current_release").schema).createOrReplaceTempView("_pointer")
        self.spark.sql("MERGE INTO "+self.prefix+"gold_current_release t USING _pointer s ON t.channel=s.channel WHEN MATCHED THEN UPDATE SET * WHEN NOT MATCHED THEN INSERT *")
        return release
