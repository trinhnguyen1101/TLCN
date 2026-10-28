import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.middleware.gzip import GZipMiddleware

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
    application.state.dashboard_data_source = settings.dashboard_data_source
    application.state.dashboard_service = DashboardService(repository)
    from app.repositories.gold.client import TrinoClient
    from app.repositories.gold.serving import GoldServingRepository
    application.state.gold_schema = settings.gold_schema
    application.state.gold_repository = GoldServingRepository(
        TrinoClient(settings.gold_trino_uri, settings.gold_trino_user),
        settings.gold_schema, settings.gold_channel,
    )
    application.add_middleware(GZipMiddleware, minimum_size=1000)
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
