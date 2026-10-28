from copy import deepcopy
from datetime import datetime,timedelta,timezone,date
import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from source_contracts import verify,verify_storage_clock
from station_proxy import waqi,ninjas,NINJAS_POLICY
from aqi.engine import hourly,daily,HOUR,local_day_bounds


def row(h,**changes):
    r=dict(hour_start_utc=h,observed_at_utc=h,collected_at_utc=h+HOUR,
        measurement_start_utc=h,measurement_end_utc=h+HOUR,source_dataset='fixture',source_version='v1',
        source_resolution_minutes=60,temporal_support='hourly_mean',unit='ug/m3',quality_status='ok',
        vertical_support='model_surface',spatial_representation='area_estimate',value=25,reference_eligible=False)
    r.update(changes);return r

class ContractTests(unittest.TestCase):
    def test_unknown_actual_clock_never_uses_collection_or_schedule(self):
        h=datetime(2026,1,1,tzinfo=timezone.utc)
        r=row(h,observed_at_utc=None,scheduled_at_utc=h,collected_at_utc=h+HOUR,temporal_support='provider_snapshot')
        self.assertIsNone(verify(r)['observed_at_utc'])
        with self.assertRaisesRegex(ValueError,'Actual observation timestamp unavailable'):
            verify_storage_clock(r)
        # A real interval-end observation is preserved, not relabelled to h.
        self.assertEqual(verify_storage_clock(row(h,observed_at_utc=h+HOUR))['observed_at_utc'],h+HOUR)
    def test_3h_hourly_instantaneous_and_provider_never_become_means(self):
        h=datetime(2026,1,1,tzinfo=timezone.utc)
        for support,cadence in [('instantaneous',180),('instantaneous',60),('provider_snapshot',60)]:
            r=verify(row(h,temporal_support=support,source_resolution_minutes=cadence))
            self.assertFalse(r['temporal_aqi_eligible'])
            _,overall=hourly(h,{(h,'pm25'):r},'area_estimate')
            self.assertIsNone(overall['aqi'])
    def test_complete_future_hourly_and_midnight_o3(self):
        day=date(2026,1,1);start,end=local_day_bounds(day)
        readings={}
        for i in range(-11,24):
            for p in ['pm25','pm10','co','no2','so2','o3']:
                h=start+i*HOUR;readings[h,p]=verify(row(h,value=25 if p=='pm25' else 10))
        values=[hourly(start+i*HOUR,readings,'area_estimate')[1]['aqi'] for i in range(24)]
        self.assertEqual(values,[50]*24)
        components,overall=daily(day,readings,'area_estimate')
        self.assertEqual(overall['aqi'],50)
        o3=[c for c in components if c['pollutant']=='o3' and c['basis']=='max8h'][0]
        self.assertEqual(o3['input_count'],24)
        with self.assertRaises(ValueError):verify(row(start,measurement_end_utc=start+2*HOUR))
        with self.assertRaises(ValueError):verify(row(start,measurement_start_utc=None))
    def test_ninjas_unknown_observation_and_verified_units(self):
        h=datetime(2026,1,1,tzinfo=timezone.utc)
        observation=dict(dataset_id='fixture',source_resolution_minutes=60,snapshot_hour_utc=h,collected_at_utc=h+HOUR,overall_aqi=80)
        measurement=[dict(variable_id='pm',value_standard=10,qc_flag='ok')]
        variables={'pm':dict(measurement_kind='concentration',standard_unit='ug/m3',pollutant='pm25')}
        location=dict(location_id='proxy1',spatial_representation='city_proxy',mapping_status='verified')
        with self.assertRaises(ValueError):ninjas(observation,measurement,variables,location,'v1','unknown')
        result=ninjas(observation,measurement,variables,location,'v1',NINJAS_POLICY)
        self.assertIsNone(result['concentrations'][0]['observed_at_utc'])
        self.assertFalse(result['concentrations'][0]['temporal_aqi_eligible'])
        self.assertEqual(result['provider_aqi'],80)
    def test_waqi_iaqi_is_not_concentration(self):
        h=datetime(2026,1,1,tzinfo=timezone.utc)
        result=waqi(dict(observation_time_utc=h,collected_at_utc=h,overall_aqi=70),
            [dict(variable_id='pm',value_native=70)],{'pm':dict(measurement_kind='iaqi')},
            dict(location_id='station1',location_kind='station',mapping_status='verified'))
        self.assertEqual(result['concentrations'],[])
        self.assertEqual(result['provider']['components'][0]['provider_sub_index'],70)
