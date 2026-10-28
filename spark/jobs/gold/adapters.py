"""Only adapters depend on Silver schema. Gold/AQI consume canonical hour facts."""
import json
from pyspark.sql import functions as F
from runtime import stable_id
from aqi.engine import HOUR, valid


def bounded_collect(frame,limit=100000,metrics=None):
    rows=frame.limit(limit+1).collect()
    if metrics is not None:
        metrics['driver_collect_rows']+=len(rows)
        metrics['driver_collect_calls']+=1
    if len(rows)>limit:raise ValueError('Driver row budget exceeded; use smaller Gold backfill chunks')
    return rows


def cams(build,dataset_id,locations):
    contract=build.contract
    source=build.read("cams_cube_standard_source").filter(F.col("dataset_id")==dataset_id)
    successful=build.read("ingestion_run").filter("status='succeeded'").select(F.col("run_id").alias("ingestion_run_id"))
    source=source.join(successful,"ingestion_run_id","inner")
    source_rows=source.collect()
    columns=contract["pollutants"]
    for row in source_rows:
        if row.column_name in columns:
            metadata=json.loads(row.conversion_metadata)
            if row.standard_unit!=contract["unit"] or row.quality_status!="validated" or metadata["source_time"]["stepType"]!="instant":
                raise ValueError("CAMS source unit/semantics unverified")
    if set(columns)-{r.column_name for r in source_rows}:
        raise ValueError("Missing CAMS source mapping")
    cube=(build.read("cams_cube_standard").filter(F.col("dataset_id")==dataset_id)
          .filter((F.col("valid_time")>=F.lit(build.start-11*HOUR)) & (F.col("valid_time")<F.lit(build.end)))
          .join(successful,"ingestion_run_id","inner"))
    if cube.limit(1).count()==0:
        raise ValueError("No successful Silver CAMS rows in requested scope")
    if cube.groupBy("dataset_id","grid_id","valid_time").count().filter("count>1").count():
        raise ValueError("Conflicting CAMS logical keys")
    if cube.filter(F.col("valid_time")!=F.date_trunc("hour",F.col("valid_time"))).count():
        raise ValueError("CAMS instantaneous input not aligned to hour")
    grids={r.grid_id:r.row_count*r.column_count for r in build.read("cams_grid").collect()}
    for g,n in grids.items():
        invalid=None
        for col in columns:
            test=F.col(col).isNull() | (F.size(col)!=n)
            invalid=test if invalid is None else invalid|test
        if cube.filter(F.col("grid_id")==g).filter(invalid).count():
            raise ValueError("CAMS array shape mismatch")
    # No explode archive: broadcast only intersecting grid indices and sample
    # the six arrays at those indices, after restricting time range.
    joined=cube.join(F.broadcast(build.bridge),"grid_id","inner")
    frames=[]
    for col,pollutant in columns.items():
        value=F.element_at(F.col(col),F.col("grid_point_id").cast("int")+1).cast("double")
        valid=value.isNotNull() & (~F.isnan(value)) & (F.abs(value)!=F.lit(float("inf"))) & (value>=0)
        frames.append(joined.select("dataset_id","valid_time","location_id","ingestion_run_id",
                      F.lit(pollutant).alias("pollutant"),F.when(valid,value).alias("v"),"area_fraction"))
    long=frames[0]
    for frame in frames[1:]:
        long=long.unionByName(frame)
    # Multiple horizontal grids must not overlap in one series/time.
    if len(grids)>1:
        active=cube.select("grid_id").distinct().count()
        if active>1:
            raise ValueError("Multiple grids require separate contracts/series")
    grouped=long.groupBy("dataset_id","valid_time","location_id","pollutant").agg(
        F.sum(F.when(F.col("v").isNotNull(),F.col("v")*F.col("area_fraction"))).alias("numerator"),
        F.sum(F.when(F.col("v").isNotNull(),F.col("area_fraction")).otherwise(0.0)).alias("coverage"),
        F.sum(F.when(F.col("v").isNotNull(),1).otherwise(0)).alias("cells"),
        F.sum(F.when(F.col("v").isNotNull(),F.col("area_fraction")**2).otherwise(0.0)).alias("squares"),
        F.sort_array(F.collect_set("ingestion_run_id")).alias("input_run_ids"))
    rows=[]
    snap=build.inputs[build.silver+"cams_cube_standard"]
    for r in bounded_collect(grouped,metrics=build.metrics):
        coverage=float(r.coverage)
        sufficient=coverage>=contract["minimum_spatial_coverage"]
        rows.append(dict(location_id=r.location_id,dataset_id=r.dataset_id,pollutant=r.pollutant,
                         hour_start_utc=r.valid_time,observed_at_utc=r.valid_time,
                         value=float(r.numerator/coverage) if sufficient and coverage>0 else None,
                         unit=contract["unit"],source_resolution_minutes=contract["source_resolution_minutes"],
                         temporal_support=contract["temporal_support"],spatial_representation="area_estimate",
                         vertical_support=contract["vertical_support"][r.pollutant],reference_eligible=False,
                         quality_status="ok" if sufficient else "insufficient_spatial_coverage",
                         missing_reason=None if sufficient else "spatial_coverage_below_policy",
                         spatial_coverage_ratio=min(1.0,coverage),grid_cells=int(r.cells),
                         effective_cells=coverage**2/float(r.squares) if r.squares else 0.0,
                         input_run_ids=r.input_run_ids,input_snapshot_id=snap))
    return canonical(build,rows,locations,"cams")


def normalized_hourly(build,dataset_id,locations):
    """Future Silver adapter contract, including per-row verified semantics.

    Fixture rows are admitted only in isolated gold_test namespaces by runner.
    Provider snapshots/instantaneous input stay ineligible even at 60 minutes.
    """
    if build.contract['applicability_profile'] not in ('area_estimate','model_estimate'):
        raise ValueError('Province adapter cannot publish station/proxy location semantics')
    name=build.contract["silver_table"]
    input=build.read(name).filter(F.col("dataset_id")==dataset_id)
    input=input.filter((F.col("hour_start_utc")>=F.lit(build.start-11*HOUR)) & (F.col("hour_start_utc")<F.lit(build.end)))
    lookup={r["admin_code"]:r["location_id"] for r in locations}
    rows=[]
    successful={r.run_id:r.dataset_id for r in build.read('ingestion_run').filter(F.col('status')=='succeeded').collect()}
    is_fixture=build.schema.startswith('gold_test') and build.silver.startswith('nessie.gold_test')
    for row in bounded_collect(input,metrics=build.metrics):
        r=row.asDict(recursive=True)
        from source_contracts import verify_storage_clock
        verify_storage_clock(r)
        if not r.get('input_run_ids') or (not is_fixture and any(successful.get(run_id)!=r['dataset_id'] for run_id in r['input_run_ids'])):
            raise ValueError('Normalized input references unsuccessful/unknown Silver attempts')
        if r['spatial_representation']!='area_estimate':
            raise ValueError('Province adapter requires preaggregated area representation')
        if r["admin_code"] not in lookup:
            raise ValueError("Unmapped input admin code")
        if r["hour_start_utc"]!=r["hour_start_utc"].replace(minute=0,second=0,microsecond=0):
            raise ValueError("Normalized Silver hour not aligned")
        if build.contract.get('require_measurement_intervals'):
            from source_contracts import verify
            from datetime import timezone
            metadata=dict(r,source_dataset=r['dataset_id'])
            # Spark TIMESTAMP values are naive Python datetimes in the pinned UTC session.
            for key in ('hour_start_utc','observed_at_utc','collected_at_utc','scheduled_at_utc','measurement_start_utc','measurement_end_utc'):
                if metadata.get(key) is not None:metadata[key]=metadata[key].replace(tzinfo=timezone.utc)
            verify(metadata)
        r["location_id"]=lookup[r.pop("admin_code")]
        r["input_snapshot_id"]=build.inputs[build.silver+name]
        rows.append(r)
    if not rows:
        raise ValueError("No normalized Silver measurements")
    return canonical(build,rows,locations,build.contract["source_system"])


def canonical(build,rows,locations,source_system):
    declared=build.contract.get('metric_policies',{})
    if source_system=='cams':
        declared={p:dict(measurement_kind='concentration',unit=build.contract['unit'],vertical_support=v)
                  for p,v in build.contract['vertical_support'].items()}
    metrics={}
    # Metric availability is data, not a unit/vertical policy change. Keep the
    # declared dimension even if every SO2 value is withdrawn from this chunk.
    for pollutant,policy in declared.items():
        if policy['measurement_kind']!='concentration' or policy['unit']!='ug/m3':
            raise ValueError('Unsupported declared concentration metric policy')
        metric_id=stable_id('metric-v1',pollutant,'concentration',policy['unit'],policy['vertical_support'])
        metrics[metric_id]=dict(release_id=build.release_id,metric_id=metric_id,pollutant=pollutant,
            measurement_kind='concentration',unit=policy['unit'],vertical_support=policy['vertical_support'],
            unit_policy_version=build.contract['contract_version'])
    series={}
    facts=[]
    for raw in rows:
        r=dict(raw)
        coverage_gate=build.contract.get('minimum_spatial_coverage')
        if coverage_gate is not None:
            if not 0<=coverage_gate<=1:raise ValueError('Invalid spatial coverage policy')
            coverage=r.get('spatial_coverage_ratio')
            if coverage is None or coverage<coverage_gate:
                r.update(value=None,quality_status='insufficient_spatial_coverage',missing_reason='spatial_coverage_below_policy')
        original=r['value']
        if not valid(original):
            r['value']=None
            r['missing_reason']=r.get('missing_reason') or ('missing_concentration' if original is None else 'invalid_concentration')
            if r['quality_status']=='ok':r['quality_status']='missing' if original is None else 'invalid'
        elif r['quality_status']!='ok':
            r['value']=None
            r['missing_reason']=r.get('missing_reason') or 'quality_rejected'
        pollutant=r["pollutant"]
        if r["unit"] != "ug/m3":
            raise ValueError("Canonical concentration adapter requires verified ug/m3")
        if pollutant not in ("pm25","pm10","co","no2","so2","o3"):
            raise ValueError("MVP adapter accepts six concentration pollutants only")
        if declared:
            policy=declared.get(pollutant)
            if not policy or any(r.get(k)!=policy[k] for k in ('unit','vertical_support')):
                raise ValueError('Input unit/vertical support conflicts with declared metric policy')
        metric_id=stable_id("metric-v1",pollutant,"concentration",r["unit"],r["vertical_support"])
        metrics[metric_id]=dict(release_id=build.release_id,metric_id=metric_id,pollutant=pollutant,
                               measurement_kind="concentration",unit=r["unit"],vertical_support=r["vertical_support"],
                               unit_policy_version=build.contract["contract_version"])
        series_id=stable_id("series-v1",r["dataset_id"],r["location_id"],build.contract_hash,
                            r["source_resolution_minutes"],r["temporal_support"],r["spatial_representation"])
        series[series_id]=dict(release_id=build.release_id,series_id=series_id,dataset_id=r["dataset_id"],
                              location_id=r["location_id"],source_system=source_system,
                              source_contract_version=build.contract["contract_version"],
                              source_resolution_minutes=r["source_resolution_minutes"],temporal_support=r["temporal_support"],
                              applicability_profile=build.contract["applicability_profile"],
                              spatial_policy_version=build.contract["spatial_method"])
        fact=dict(r)
        fact.pop("dataset_id")
        fact.pop("location_id")
        fact.update(release_id=build.release_id,series_id=series_id,metric_id=metric_id,source_dataset=r["dataset_id"])
        facts.append(fact)
    if len({(r["series_id"],r["hour_start_utc"],r["metric_id"]) for r in facts})!=len(facts):
        raise ValueError("Duplicate canonical hourly measurements")
    build.write("dim_metric",list(metrics.values()))
    build.write("dim_air_quality_series",list(series.values()))
    # Keep source variable mapping separate from provider indices.
    bridge=[]
    if source_system=="cams":
        for r in build.read("cams_cube_standard_source").filter(F.col("dataset_id")==rows[0]["dataset_id"]).collect():
            p=build.contract["pollutants"].get(r.column_name)
            if p:
                m=next(m for m in metrics.values() if m["pollutant"]==p)
                bridge.append(dict(release_id=build.release_id,dataset_id=r.dataset_id,variable_id=r.variable_id,
                                   source_column=r.column_name,metric_id=m["metric_id"],source_unit=r.native_unit,
                                   standard_unit=r.standard_unit,metric_policy_version=build.contract["contract_version"]))
        bridge=list({(r["dataset_id"],r["variable_id"],r["metric_id"]):r for r in bridge}.values())
    build.write("bridge_source_variable_metric",bridge)
    provenance=[]
    for f in facts:
        if f.get('source_version'):
            provenance.append(dict(release_id=build.release_id,series_id=f['series_id'],hour_start_utc=f['hour_start_utc'],
                metric_id=f['metric_id'],source_version=f['source_version'],observed_at_utc=f.get('observed_at_utc'),
                collected_at_utc=f.get('collected_at_utc'),scheduled_at_utc=f.get('scheduled_at_utc'),
                measurement_start_utc=f.get('measurement_start_utc'),measurement_end_utc=f.get('measurement_end_utc'),
                observation_time_kind=f.get('observation_time_kind','source_observed')))
    if provenance:build.write('fact_measurement_provenance',provenance)
    build.write("fact_air_quality_hourly",facts)
    return facts,list(series.values())
