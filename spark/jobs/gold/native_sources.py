"""Independent WAQI daily/provider and Climate TRACE native branch.

No hourly expansion, no emission-to-AQI conversion, no combining hierarchy
levels. Unknown emission units are preserved NULL; GADM stays unallocated.
"""
import argparse
from datetime import datetime,timezone,timedelta
import fcntl
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from pyspark.sql import functions as F
from runtime import Build,bootstrap,spark_session,identifier
from run import code_digest


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--schema',default='gold',type=identifier)
    p.add_argument('--schema-sql',default='/opt/spark/work-dir/lakehouse/gold/gold.sql')
    args=p.parse_args()
    with open('/tmp/tlcn-gold-writer.lock','w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        spark=spark_session()
        try:
            bootstrap(spark,args.schema,args.schema_sql)
            build=Build(spark,args.schema,'silver',{'contract_version':'native-sources-v1','emission_unit_policy':'retain_unknown',
                        'gadm_policy':'unallocated_no_centroid_assignment','waqi_policy':'provider_daily_not_concentration'},
                        datetime(2014,1,1,tzinfo=timezone.utc),datetime(2027,1,1,tzinfo=timezone.utc),'native_sources',code_digest(args.schema_sql))
            names=['ingestion_run','dataset','variable','waqi_daily_observation','emission_aggregate','emission_source','emission_source_observation','waqi_station']
            for name in names:build.read(name)
            earliest=[]
            latest=[]
            for name,lo,hi in [('waqi_daily_observation','observation_date','observation_date'),('emission_aggregate','period_start','period_end'),('emission_source_observation','period_start','period_end')]:
                bounds=build.read(name).agg(F.min(lo),F.max(hi)).first()
                earliest.append(bounds[0]);latest.append(bounds[1])
            build.start=datetime.combine(min(earliest),datetime.min.time(),timezone.utc)
            build.end=datetime.combine(max(latest)+timedelta(days=1),datetime.min.time(),timezone.utc)
            build.identify()
            existing=spark.table(build.prefix+'gold_release').filter(F.col('release_id')==build.release_id).collect()
            if existing:
                registered=existing[0].asDict()
                pointer=spark.table(build.prefix+'gold_current_release').filter(F.col('channel')==build.channel).collect()
                if not pointer or pointer[0].published_at<registered['published_at']:build.activate(registered)
                print('GOLD_NATIVE_REPLAY '+build.release_id,flush=True)
                return
            runs=build.read('ingestion_run').filter("status='succeeded'").select(F.col('run_id').alias('ingestion_run_id'))
            variables=build.read('variable').select('variable_id','canonical_name','measurement_kind','native_unit')
            for name in names:build.read(name).createOrReplaceTempView('n_'+name)
            runs.createOrReplaceTempView('n_success')
            rid=build.release_id
            ws=build.inputs[build.silver+'waqi_daily_observation']
            waqi=spark.sql(f"""SELECT '{rid}' release_id,w.dataset_id,w.station_id,w.observation_date,w.variable_id,
                v.short_name pollutant,w.aqi_value provider_aqi,'provider' aqi_origin,'provider_unspecified' aqi_scheme,
                w.qc_flag quality_status,w.missing_reason,'Asia/Ho_Chi_Minh' calendar_timezone,
                w.ingestion_run_id input_run_id,cast({ws} AS BIGINT) input_snapshot_id
                FROM n_waqi_daily_observation w JOIN n_success r USING(ingestion_run_id)
                JOIN n_variable v USING(variable_id) WHERE v.measurement_kind='daily_aqi' AND v.standard_unit='AQI'""")
            build.write('fact_waqi_station_daily_native',waqi)
            es=build.inputs[build.silver+'emission_aggregate']
            aggregate=spark.sql(f"""SELECT '{rid}' release_id,a.aggregate_id,a.dataset_id,a.country_code,a.period_type,
                a.period_start,a.period_end,a.period_status,a.aggregation_level,a.sector,a.subsector,v.short_name pollutant,
                a.emission_quantity_native quantity_native,v.native_unit unit,
                CASE WHEN v.native_unit IS NULL THEN 'unverified' ELSE 'source_declared' END unit_status,
                a.ingestion_run_id input_run_id,cast({es} AS BIGINT) input_snapshot_id
                FROM n_emission_aggregate a JOIN n_success r USING(ingestion_run_id) JOIN n_variable v USING(variable_id)
                WHERE v.measurement_kind='emission_quantity'""")
            build.write('fact_emission_aggregate_native',aggregate)
            ss=build.inputs[build.silver+'emission_source_observation']
            source=spark.sql(f"""SELECT '{rid}' release_id,o.dataset_id,o.source_id,o.year_label,o.period_start,o.period_end,
                o.period_status,v.short_name pollutant,o.emission_quantity_native quantity_native,s.source_type,
                s.sector,s.subsector,s.latitude,s.longitude,cast(NULL AS STRING) admin_code,
                CASE WHEN s.source_type='gadm-aggregation' THEN 'gadm_crosswalk_unavailable'
                     WHEN s.source_type='point-source' THEN 'point_unmapped' ELSE 'unsupported_source_type' END geographic_mapping_status,
                v.native_unit unit,CASE WHEN v.native_unit IS NULL THEN 'unverified' ELSE 'source_declared' END unit_status,
                o.ingestion_run_id input_run_id,cast({ss} AS BIGINT) input_snapshot_id
                FROM n_emission_source_observation o JOIN n_success r USING(ingestion_run_id)
                JOIN n_emission_source s ON s.source_id=o.source_id AND s.dataset_id=o.dataset_id
                JOIN n_variable v ON v.variable_id=o.variable_id WHERE v.measurement_kind='emission_quantity'""")
            build.write('fact_emission_source_native',source)
            mart=build.rows('fact_emission_aggregate_native').filter("aggregation_level='totals'").select(
                'release_id','dataset_id','country_code','period_type','period_start','period_end','period_status',
                'pollutant','quantity_native','unit','unit_status','aggregation_level')
            build.write('mart_emission_country_period_native',mart)
            if build.rows('fact_waqi_station_daily_native').join(build.read('waqi_station').select('station_id'),'station_id','left_anti').limit(1).count():
                raise ValueError('WAQI native station reference missing')
            counts={}
            for name,keys in {
                'fact_waqi_station_daily_native':['dataset_id','station_id','observation_date','variable_id'],
                'fact_emission_aggregate_native':['aggregate_id'],
                'fact_emission_source_native':['dataset_id','source_id','year_label','pollutant'],
                'mart_emission_country_period_native':['dataset_id','country_code','period_type','period_start','pollutant'],
            }.items():
                frame=build.rows(name)
                counts[name]=frame.count()
                if frame.groupBy(*keys).count().filter('count>1').count():raise ValueError('Duplicate native Gold key: '+name)
                if name.startswith('fact_emission') and frame.filter(F.isnan('quantity_native')|(F.abs(F.col('quantity_native'))==float('inf'))).count():
                    raise ValueError('Non-finite emissions')
            release=build.publish(counts,method_version='not_applicable_native-v1')
            print('GOLD_NATIVE_PUBLISHED '+release['release_id']+' '+str(counts),flush=True)
        finally:spark.stop()

if __name__=='__main__':main()
