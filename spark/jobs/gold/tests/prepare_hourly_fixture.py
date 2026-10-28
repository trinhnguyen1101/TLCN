"""ISOLATED TEST ONLY: synthetic hourly input; never a production source.

Real Silver geography is copied with snapshot provenance. Concentrations below
are test fixtures, explicitly marked in namespace, dataset and run identity.
"""
import sys
import argparse
from pathlib import Path
from datetime import date,datetime,timedelta,timezone
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from runtime import spark_session,snapshot
from aqi.engine import local_day_bounds,HOUR


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--start-date',default='2026-01-02')
    parser.add_argument('--days',type=int,default=2)
    parser.add_argument('--namespace',default='gold_test_silver')
    args=parser.parse_args()
    spark=spark_session()
    try:
        from runtime import identifier
        identifier(args.namespace)
        if not args.namespace.startswith('gold_test'):raise ValueError('Fixture namespace required')
        if not 1<=args.days<=31:raise ValueError('Bounded fixtures only')
        namespace='nessie.'+args.namespace
        spark.sql('CREATE NAMESPACE IF NOT EXISTS '+namespace)
        for name in ['admin_unit','admin_boundary','ingestion_run']:
            target=namespace+'.'+name
            if not spark.catalog.tableExists(target):
                snap=snapshot(spark,'nessie.silver.'+name)
                spark.sql('CREATE TABLE '+target+" USING iceberg LOCATION 's3a://lakehouse/"+args.namespace+"/"+name+"' AS SELECT * FROM nessie.silver."+name+' VERSION AS OF '+str(snap))
                print('FIXTURE_GEOGRAPHY '+name+' source_snapshot='+str(snap),flush=True)
        table=namespace+'.hourly_concentration'
        spark.sql('''CREATE TABLE IF NOT EXISTS '''+table+''' (
            dataset_id STRING NOT NULL, admin_code STRING NOT NULL, pollutant STRING NOT NULL,
            hour_start_utc TIMESTAMP NOT NULL, observed_at_utc TIMESTAMP NOT NULL,
            value DOUBLE, unit STRING NOT NULL, source_resolution_minutes INT NOT NULL,
            temporal_support STRING NOT NULL, spatial_representation STRING NOT NULL,
            vertical_support STRING NOT NULL, reference_eligible BOOLEAN NOT NULL,
            quality_status STRING NOT NULL, missing_reason STRING, spatial_coverage_ratio DOUBLE,
            source_version STRING, collected_at_utc TIMESTAMP, scheduled_at_utc TIMESTAMP,
            measurement_start_utc TIMESTAMP, measurement_end_utc TIMESTAMP, observation_time_kind STRING,
            grid_cells INT, effective_cells DOUBLE, input_run_ids ARRAY<STRING> NOT NULL
        ) USING iceberg LOCATION 's3a://lakehouse/{fixture_namespace}/hourly_concentration'
          TBLPROPERTIES ('format-version'='2','write.parquet.compression-codec'='zstd')'''.format(fixture_namespace=args.namespace))
        start,_=local_day_bounds(date.fromisoformat(args.start_date))
        rows=[]
        # 48 hourly means plus 11 halo hours; one province. Entire input valid.
        existing={r[0] for r in spark.table(table).select('hour_start_utc').distinct().collect()}
        for i in range(-11,args.days*24):
            if (start+i*HOUR).replace(tzinfo=None) in existing:continue
            for pollutant in ['pm25','pm10','co','no2','so2','o3']:
                value=25.0 if pollutant=='pm25' else 10.0
                rows.append(dict(dataset_id='hourly_fixture_only',admin_code='01',pollutant=pollutant,
                    hour_start_utc=start+i*HOUR,observed_at_utc=start+i*HOUR,source_version='hourly-fixture-v2',
                    collected_at_utc=start+(i+1)*HOUR,scheduled_at_utc=start+i*HOUR,
                    measurement_start_utc=start+i*HOUR,measurement_end_utc=start+(i+1)*HOUR,observation_time_kind='interval_start',value=value,unit='ug/m3',
                    source_resolution_minutes=60,temporal_support='hourly_mean',spatial_representation='area_estimate',
                    vertical_support='model_surface',reference_eligible=False,quality_status='ok',missing_reason=None,
                    spatial_coverage_ratio=1.0,grid_cells=1,effective_cells=1.0,input_run_ids=['fixture_not_production']))
        if rows:spark.createDataFrame(rows,spark.table(table).schema).coalesce(1).writeTo(table).append()
        print('FIXTURE_ROWS '+str(len(rows)),flush=True)
    finally:
        spark.stop()

if __name__=='__main__':
    main()
