"""Pure temporal/unit adapter gates. Cadence alone never grants AQI eligibility."""
from datetime import datetime,timedelta,timezone
from copy import deepcopy


def as_utc(value):
    if value is None:return None
    if isinstance(value,str):value=datetime.fromisoformat(value.replace('Z','+00:00'))
    if value.tzinfo is None:raise ValueError('Adapter input needs an explicit UTC offset')
    return value.astimezone(timezone.utc)


def verify_storage_clock(row):
    """Current physical fact requires an actual observation clock, independent
    of the interval label. Never substitute collection/schedule for this field.
    Unknown-clock provider snapshots need the reviewed additive migration.
    """
    if row.get('observed_at_utc') is None:
        raise ValueError('Actual observation timestamp unavailable: current Gold fact requires observed_at_utc; unknown-clock source onboarding is blocked')
    return row


def verify(row,require_intervals=True):
    result=deepcopy(row)
    required=('source_resolution_minutes','temporal_support','source_dataset','source_version','unit',
              'quality_status','vertical_support','spatial_representation')
    if any(result.get(k) is None for k in required):raise ValueError('Missing source semantic contract')
    if result['source_resolution_minutes']<=0:raise ValueError('Invalid source cadence')
    for name in ('hour_start_utc','observed_at_utc','collected_at_utc','scheduled_at_utc','measurement_start_utc','measurement_end_utc'):
        result[name]=as_utc(result.get(name))
    slot=result['hour_start_utc']
    if slot is None or slot.minute or slot.second or slot.microsecond:raise ValueError('Hour slot must be aligned')
    if result['unit']!='ug/m3':raise ValueError('Unverified canonical concentration unit')
    mean=result['temporal_support']=='hourly_mean'
    if mean and require_intervals:
        lo,hi=result['measurement_start_utc'],result['measurement_end_utc']
        if lo!=slot or hi!=slot+timedelta(hours=1):raise ValueError('Hourly mean needs the exact declared [hour,hour+1) interval')
    result['temporal_aqi_eligible']=bool(mean and result['source_resolution_minutes']==60 and result['quality_status']=='ok')
    return result
