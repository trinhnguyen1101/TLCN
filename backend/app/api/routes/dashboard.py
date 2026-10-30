from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request

from app.api.dependencies import get_dashboard_service
from app.schemas.dashboard import AdminDashboardData, DashboardData
from app.services.dashboard import DashboardService
from app.services.temporal import DashboardQuery, InvalidDashboardQuery, Resolution, utc_bound

router = APIRouter(tags=["dashboard"])


def dashboard_query(request: Request, resolution: Resolution | None = None, start: str | None = None, end: str | None = None,
                    source: str | None = None,series_id: str | None = None,method_version: str | None = None,
                    applicability_profile: str | None = None,compatibility_id: str | None = None):
    selected = resolution or "hourly"
    filters=dict(source=source,series_id=series_id,method_version=method_version,applicability_profile=applicability_profile,compatibility_id=compatibility_id)
    if request.app.state.dashboard_data_source!='gold' and any(filters.values()):
        raise HTTPException(422,'Source/semantic selection requires Gold mode')
    query = DashboardQuery(selected, start, end,**filters)
    try:
        for value in (start, end):
            if value:
                utc_bound(value)
        if start and end:
            query.bounds(end)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return query


@router.get(
    "/dashboard",
    response_model=DashboardData,
    response_model_exclude_unset=True,
    responses={503: {"description": "The configured data source is unavailable"}},
)
def get_dashboard(
    service: Annotated[DashboardService, Depends(get_dashboard_service)],
    query: Annotated[DashboardQuery, Depends(dashboard_query)],
) -> DashboardData:
    try:
        return service.get_dashboard(query)
    except (InvalidDashboardQuery, ValueError) as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get(
    "/admin/dashboard",
    response_model=AdminDashboardData,
    response_model_exclude_unset=True,
    responses={503: {"description": "The configured data source is unavailable"}},
)
def get_admin_dashboard(
    service: Annotated[DashboardService, Depends(get_dashboard_service)],
    query: Annotated[DashboardQuery, Depends(dashboard_query)],
) -> AdminDashboardData:
    try:
        return service.get_admin_dashboard(query)
    except (InvalidDashboardQuery, ValueError) as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get('/dashboard/analytics')
def get_analytics(
    request: Request,
    service: Annotated[DashboardService, Depends(get_dashboard_service)],
    province_code: str = 'all', metric: str = 'pm25', year: int | None = None,
    month: int | None = None, start_date: str | None = None, end_date: str | None = None,
    provinceCode: str | None = None, startDate: str | None = None, endDate: str | None = None,
    resolution: Resolution | None = None, start: str | None = None, end: str | None = None,
):
    from app.services.analytics import AnalyticsQuery
    from pydantic import ValidationError
    try:
        query = AnalyticsQuery(province_code=provinceCode or province_code, metric=metric,
                               year=year, month=month, start_date=startDate or start_date,
                               end_date=endDate or end_date)
        temporal = None
        if request.app.state.dashboard_data_source == "parquet" and (resolution or start or end):
            temporal = DashboardQuery(resolution or "hourly", start, end)
            for value in (start, end):
                if value:
                    utc_bound(value)
        return service.get_analytics(query, temporal)
    except (InvalidDashboardQuery, ValueError, ValidationError) as exc:
        raise HTTPException(422, str(exc)) from exc
