import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.router import api_router
from app.core.config import Settings
from app.repositories.base import DashboardRepository, DataSourceUnavailable
from app.repositories.factory import create_dashboard_repository
from app.services.dashboard import DashboardService


def create_app(
    settings: Settings | None = None,
    dashboard_repository: DashboardRepository | None = None,
) -> FastAPI:
    settings = settings if settings is not None else Settings.from_env()
    repository = (
        dashboard_repository if dashboard_repository is not None
        else create_dashboard_repository(settings)
    )
    application = FastAPI(title="Air Quality API", version="0.1.0")
    application.state.dashboard_service = DashboardService(repository)
    application.include_router(api_router)

    @application.exception_handler(DataSourceUnavailable)
    async def source_unavailable(
        request: Request, exc: DataSourceUnavailable,
    ) -> JSONResponse:
        logging.getLogger(__name__).warning("Dashboard data source unavailable", exc_info=exc)
        return JSONResponse(
            status_code=503,
            content={"detail": "Dashboard data source is temporarily unavailable."},
        )

    return application


app = create_app()
