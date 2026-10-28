"""Scope planning from actual changed instants, independent of source cadence."""
from datetime import timedelta
from aqi.engine import VN,HOUR,check_hour,local_day_bounds


def invalidation_scope(changed_hours):
    if not changed_hours:
        raise ValueError('Changed-hour inventory required; no guessed lookback')
    for hour in changed_hours:check_hour(hour)
    first=min(changed_hours)
    last=max(changed_hours)+11*HOUR
    first_day,last_day=first.astimezone(VN).date(),last.astimezone(VN).date()
    end_date=last_day+timedelta(days=1)
    return dict(start_date=first_day.isoformat(),end_date=end_date.isoformat(),
                required_input_start_utc=local_day_bounds(first_day)[0]-11*HOUR,
                pm_end_exclusive=max(changed_hours)+12*HOUR,
                o3_end_exclusive=max(changed_hours)+8*HOUR,
                policy='replace entire declared local-day scope, then rebuild daily/monthly marts')
