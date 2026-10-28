from datetime import datetime
from typing import Literal
from typing import Annotated
from fastapi import APIRouter,Request,Query,HTTPException
from app.schemas.gold import GoldResponse,Pollutant,Resolution

router=APIRouter(prefix='/gold',tags=['gold'])


def repository(request):
    return request.app.state.gold_repository


def checked(function,*args,**kwargs):
    try:
        return function(*args,**kwargs)
    except ValueError as exc:
        raise HTTPException(422,str(exc)) from exc


@router.get('/air-quality',response_model=GoldResponse)
def air_quality(request:Request,resolution:Resolution='hourly',start:datetime|None=None,
                end:datetime|None=None,pollutant:Pollutant='pm25',admin_code:str|None=None,
                release_id:str|None=None,limit:Annotated[int,Query(ge=1,le=25000)]=10000):
    return checked(repository(request).air_quality,resolution,start,end,pollutant,admin_code,release_id,limit)


@router.get('/map',response_model=GoldResponse)
def province_map(request:Request,pollutant:Pollutant='pm25',at:datetime|None=None,release_id:str|None=None,
                 source:str|None=None,series_id:str|None=None,method_version:str|None=None,
                 applicability_profile:str|None=None,compatibility_id:str|None=None):
    return checked(repository(request).province_map,pollutant,at,release_id,source,series_id,method_version,applicability_profile,compatibility_id)


@router.get('/source-quality')
def source_quality(request:Request,release_id:str|None=None):
    return checked(repository(request).quality,release_id)


@router.get('/admin/summary')
def admin_summary(request:Request,release_id:str|None=None):
    return checked(repository(request).admin_summary,release_id)


@router.get('/native/emissions')
def native_emissions(request:Request,pollutant:Annotated[str,Query(pattern=r'^[a-z0-9_]{1,20}$')]='co2',
                     period_type:Literal['year','month']='year',aggregation_level:Literal['totals','sectors','subsectors']='totals',
                     year:Annotated[int|None,Query(ge=1900,le=2200)]=None,
                     source_type:Literal['point-source','gadm-aggregation']|None=None,
                     limit:Annotated[int,Query(ge=1,le=5000)]=1000):
    from app.repositories.gold.serving import GoldServingRepository
    base=repository(request)
    native=GoldServingRepository(base.client,request.app.state.gold_schema,'native_sources')
    return checked(native.native_emissions,pollutant,period_type,aggregation_level,year,source_type,limit)


@router.get('/history')
def history(request:Request,resolution:Resolution='hourly',start:datetime|None=None,end:datetime|None=None,
            pollutant:Pollutant='pm25',admin_code:str|None=None,source:str|None=None,series_id:str|None=None,
            method_version:str|None=None,applicability_profile:str|None=None,compatibility_id:str|None=None,
            timeline_id:str|None=None,cursor:str|None=None,limit:Annotated[int,Query(ge=1,le=25000)]=10000):
    from app.repositories.gold.history import GoldHistoryRepository
    return checked(GoldHistoryRepository(repository(request)).air_quality,resolution,start,end,pollutant,admin_code,
                   source,series_id,method_version,applicability_profile,compatibility_id,timeline_id,limit,cursor)


@router.get('/history/catalog')
def history_catalog(request:Request):
    from app.repositories.gold.history import GoldHistoryRepository
    context=GoldHistoryRepository(repository(request)).resolve()
    return dict(published_timeline_id=context['timeline_id'],segments=[{k:v for k,v in s.items() if k!='snapshots'} for s in context['segments']])


@router.get('/history/aqi-distribution')
def history_aqi_distribution(request:Request,start:datetime|None=None,end:datetime|None=None,
                             admin_code:str|None=None,source:str|None=None,compatibility_id:str|None=None,timeline_id:str|None=None):
    from app.repositories.gold.history import GoldHistoryRepository
    return checked(GoldHistoryRepository(repository(request)).aqi_distribution,start=start,end=end,
                   admin_code=admin_code,source=source,compatibility_id=compatibility_id,timeline_id=timeline_id,limit=25000)


@router.get('/history/quality')
def history_quality(request:Request,start:datetime|None=None,end:datetime|None=None,source:str|None=None,
                    compatibility_id:str|None=None,timeline_id:str|None=None):
    from app.repositories.gold.history import GoldHistoryRepository
    return checked(GoldHistoryRepository(repository(request)).quality,start,end,source,compatibility_id,timeline_id)
