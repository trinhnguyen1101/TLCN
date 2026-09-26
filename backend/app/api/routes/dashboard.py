from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.dependencies import get_dashboard_service
from app.schemas.dashboard import AdminDashboardData, DashboardData
from app.services.dashboard import DashboardService

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
