"""Read-only source transforms awaiting succeeded Silver operational data.

These transforms do not publish or treat provider IAQI as concentration. A
caller must join pinned Silver variable/run/location mappings before use.
"""
from source_contracts import as_utc,verify

POLLUTANTS={'pm25','pm10','so2','no2','co','o3'}
NINJAS_POLICY='api-ninjas-ugm3-reviewed-2026-10-28'


def waqi(observation,measurements,variables,location):
    if location.get('location_kind')!='station' or location.get('mapping_status')!='verified':
        raise ValueError('WAQI requires a verified station mapping, not a province proxy')
    observed=as_utc(observation['observation_time_utc'])
    provider=dict(location_id=location['location_id'],source='waqi',aqi_origin='provider',aqi_scheme='provider_reported',
                  provider_aqi=observation.get('overall_aqi'),quality_status=observation.get('qc_flag','unverified'),observed_at_utc=observed,
                  collected_at_utc=as_utc(observation['collected_at_utc']),temporal_support='provider_snapshot',
                  applicability_profile='station_reference',computed_aqi=None,components=[])
    concentrations=[]
    for row in measurements:
        variable=variables[row['variable_id']]
        kind=variable['measurement_kind']
        if kind in ('aqi','iaqi','pollutant_aqi','air_quality_index'):
            provider['components'].append(dict(variable_id=row['variable_id'],provider_sub_index=row.get('value_native')))
        elif kind=='concentration':
            if variable.get('standard_unit')!='ug/m3':raise ValueError('WAQI concentration unit unverified')
            concentrations.append(dict(pollutant=variable['pollutant'],value=row.get('value_standard'),unit='ug/m3',
                observed_at_utc=observed,temporal_support='provider_snapshot',reference_eligible=False))
    return dict(provider=provider,concentrations=concentrations)


def ninjas(observation,measurements,variables,location,source_version,unit_policy):
    if unit_policy!=NINJAS_POLICY:raise ValueError('API Ninjas unit migration has not been certified')
    if location.get('spatial_representation')!='city_proxy' or location.get('mapping_status')!='verified':
        raise ValueError('Ninjas requires a verified city proxy identity')
    slot=as_utc(observation['snapshot_hour_utc'])
    rows=[]
    for row in measurements:
        variable=variables[row['variable_id']]
        if variable['measurement_kind']!='concentration':continue
        if variable.get('standard_unit')!='ug/m3' or variable.get('pollutant') not in POLLUTANTS:raise ValueError('Ninjas unit/metric mismatch')
        # Provider response contains no observation timestamp. The scheduled slot
        # is explicitly a snapshot label; collection time is not observation time.
        value=row.get('value_standard')
        result=verify(dict(source_dataset=observation['dataset_id'],source_version=source_version,
            source_resolution_minutes=observation.get('source_resolution_minutes'),temporal_support='provider_snapshot',hour_start_utc=slot,
            observed_at_utc=None,collected_at_utc=observation['collected_at_utc'],scheduled_at_utc=slot,
            unit='ug/m3',quality_status=row['qc_flag'],vertical_support='unspecified_provider',
            spatial_representation='city_proxy',value=value))
        result.update(pollutant=variable['pollutant'],location_id=location['location_id'],
                      applicability_profile='proxy_estimate',reference_eligible=False)
        rows.append(result)
    return dict(concentrations=rows,provider_aqi=observation.get('overall_aqi'),aqi_origin='provider',computed_aqi=None)
