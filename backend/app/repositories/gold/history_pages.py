"""Bounded snapshot scans. Monthly page boundaries never split a calendar month."""
from datetime import datetime,time,timedelta,timezone
from app.repositories.gold.serving import instant
VN=timezone(timedelta(hours=7))
DATA_SCANS=16
AGGREGATE_SCANS=32


def next_month(day):
    return day.replace(year=day.year+1,month=1) if day.month==12 else day.replace(month=day.month+1)


def window(segments,resolution,lower,upper,page=0):
    active=sorted((s for s in segments if not s.get('withdrawn')),key=lambda s:s['start'])
    if resolution!='monthly':
        if page<0 or (page>=len(active) and page!=0):raise ValueError('Cursor page outside timeline')
        stop=min(len(active),page+DATA_SCANS)
        return active[page:stop],lower,upper,stop if stop<len(active) else None
    months={}
    for index,s in enumerate(active):
        lo=max(lower,instant(s['start']));hi=min(upper,instant(s['end']))
        day=lo.astimezone(VN).date().replace(day=1)
        last=(hi-timedelta(microseconds=1)).astimezone(VN).date().replace(day=1)
        while day<=last:
            months.setdefault(day,set()).add(index);day=next_month(day)
    ordered=sorted(months)
    if page<0 or (page>=len(ordered) and page!=0):raise ValueError('Cursor month outside timeline')
    if not ordered:return [],lower,upper,None
    indexes=set();stop=page
    while stop<len(ordered) and stop-page<12:
        combined=indexes|months[ordered[stop]]
        if len(combined)>AGGREGATE_SCANS:
            if stop==page:raise ValueError('More than 32 segments in one month; rebuild/coalesce daily-aligned scopes')
            break
        indexes=combined;stop+=1
    lo=max(lower,datetime.combine(ordered[page],time(),VN))
    hi=min(upper,datetime.combine(next_month(ordered[stop-1]),time(),VN))
    return [active[i] for i in sorted(indexes)],lo,hi,stop if stop<len(ordered) else None


def batches(segments,size=AGGREGATE_SCANS):
    active=sorted((s for s in segments if not s.get('withdrawn')),key=lambda s:s['start'])
    for i in range(0,len(active),size):yield active[i:i+size]
