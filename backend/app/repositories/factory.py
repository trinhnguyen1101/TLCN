from app.core.config import Settings
from app.repositories.base import DashboardRepository


def create_dashboard_repository(settings: Settings) -> DashboardRepository:
    if settings.dashboard_data_source == "mock":
        # Keep demo implementation imports local to this explicitly chosen path.
        from app.repositories.mock.dashboard import MockDashboardRepository

        return MockDashboardRepository()

    if settings.dashboard_data_source == "parquet":
        from app.repositories.parquet.dashboard import ParquetDashboardRepository

        return ParquetDashboardRepository(settings.dashboard_parquet_path)

    raise ValueError(
        f"Unsupported DASHBOARD_DATA_SOURCE: {settings.dashboard_data_source!r}. "
        "Register a repository for this source before enabling it."
    )
