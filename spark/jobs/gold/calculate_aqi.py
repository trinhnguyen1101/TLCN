"""Execute pure AQI functions per series on Spark workers, preserving time slots."""
from datetime import timezone
import json
from pyspark import StorageLevel
from pyspark.sql import functions as F
from aqi.engine import hourly,daily,HOUR,VN
from aqi.reference import METHOD_VERSION


def series_results(item,start,end,release_id,lineage):
    series_id,group=item
    group=list(group)
    readings={}
    profile=group[0]["applicability_profile"]
    for row in group:
        h=row["hour_start_utc"].replace(tzinfo=timezone.utc)
        readings[(h,row["pollutant"])]=row
    h=start
    while h<end:
        cs,overall=hourly(h,readings,profile)
        for c in cs:
            c.update(release_id=release_id,series_id=series_id,hour_start_utc=h,
                     method_version=METHOD_VERSION,applicability_profile=profile,input_lineage_json=lineage,
                     aqi_origin="computed",aqi_provider=None,provider_aqi_scheme=None,
                     provider_sub_index=None,observed_at_utc=None,scheduled_at_utc=None,
                     collected_at_utc=None,observation_time_kind=None)
            yield ("fact_aqi_pollutant_hourly",json.dumps(c,default=str))
        overall.update(release_id=release_id,series_id=series_id,hour_start_utc=h,input_lineage_json=lineage,
                       aqi_origin="computed",aqi_provider=None,provider_aqi_scheme=None,
                       observed_at_utc=None,scheduled_at_utc=None,collected_at_utc=None,
                       observation_time_kind=None)
        yield ("fact_aqi_hourly",json.dumps(overall,default=str))
        h+=HOUR
    day=start.astimezone(VN).date()
    last=end.astimezone(VN).date()
    while day<last:
        cs,overall=daily(day,readings,profile)
        for c in cs:
            c.update(release_id=release_id,series_id=series_id,aqi_date_local=day,
                     method_version=METHOD_VERSION,applicability_profile=profile,input_lineage_json=lineage,
                     aqi_origin="computed",aqi_provider=None,provider_aqi_scheme=None)
            yield ("fact_aqi_pollutant_daily",json.dumps(c,default=str))
        overall.update(release_id=release_id,series_id=series_id,aqi_date_local=day,input_lineage_json=lineage,
                       aqi_origin="computed",aqi_provider=None,provider_aqi_scheme=None)
        yield ("fact_aqi_daily",json.dumps(overall,default=str))
        day+=HOUR*24


def calculate(build):
    source=build.rows("fact_air_quality_hourly").join(
        build.rows("dim_air_quality_series").select("series_id","applicability_profile"),"series_id")
    start,end,rid=build.start,build.end,build.release_id
    lineage=json.dumps(dict(silver_snapshots=build.inputs,contract_sha256=build.contract_hash),sort_keys=True)
    grouped=source.rdd.map(lambda r:(r.series_id,r.asDict(recursive=True))).groupByKey(2)
    results=grouped.flatMap(lambda item:series_results(item,start,end,rid,lineage)).persist(StorageLevel.DISK_ONLY)
    try:
        for name in ("fact_aqi_pollutant_hourly","fact_aqi_hourly","fact_aqi_pollutant_daily","fact_aqi_daily"):
            payloads=results.filter(lambda row:row[0]==name).map(lambda row:row[1])
            schema=build.spark.table(build.prefix+name).schema
            frame=build.spark.read.schema(schema).option("timestampFormat","yyyy-MM-dd HH:mm:ssXXX").json(payloads)
            build.write(name,frame)
    finally:
        results.unpersist()
