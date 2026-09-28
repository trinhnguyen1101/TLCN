from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.dependencies import get_dashboard_service
from app.schemas.dashboard import AdminDashboardData, DashboardData
from app.services.dashboard import DashboardService
from app.services.analytics import AnalyticsQuery, DashboardAnalytics

router = APIRouter(tags=["dashboard"])


@router.get(
    "/dashboard",
    response_model=DashboardData,
    response_model_exclude_unset=True,
    responses={503: {"description": "The configured data source is unavailable"}},
)
def get_dashboard(
    service: Annotated[DashboardService, Depends(get_dashboard_service)],
) -> DashboardData:
    return service.get_dashboard()


@router.get(
    "/admin/dashboard",
    response_model=AdminDashboardData,
    response_model_exclude_unset=True,
    responses={503: {"description": "The configured data source is unavailable"}},
)
def get_admin_dashboard(
    service: Annotated[DashboardService, Depends(get_dashboard_service)],
) -> AdminDashboardData:
    return service.get_admin_dashboard()


@router.get('/dashboard/analytics', response_model=DashboardAnalytics,
            responses={503: {'description': 'The configured data source is unavailable'}})
def get_dashboard_analytics(
    query: Annotated[AnalyticsQuery, Query()],
    service: Annotated[DashboardService, Depends(get_dashboard_service)],
) -> DashboardAnalytics:
    try:
        return service.get_analytics(query)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
