from fastapi import Request

from app.services.dashboard import DashboardService


def get_dashboard_service(request: Request) -> DashboardService:
    return request.app.state.dashboard_service
