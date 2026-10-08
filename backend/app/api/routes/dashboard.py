from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.api.dependencies import get_dashboard_service
from app.schemas.dashboard import AdminDashboardData, DashboardData
from app.services.dashboard import DashboardService
from app.services.temporal import DashboardQuery, InvalidDashboardQuery, Resolution, utc_bound

router = APIRouter(tags=["dashboard"])


def dashboard_query(resolution: Resolution = "3h", start: str | None = None, end: str | None = None):
    query = DashboardQuery(resolution, start, end)
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
