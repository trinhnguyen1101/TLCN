from app.core.config import Settings
from app.repositories.base import DashboardRepository


def create_dashboard_repository(settings: Settings) -> DashboardRepository:
    if settings.dashboard_data_source == "parquet":
        from app.repositories.parquet.dashboard import ParquetDashboardRepository

        return ParquetDashboardRepository(settings.dashboard_parquet_path)

    if settings.dashboard_data_source == "gold":
        from app.repositories.gold.client import TrinoClient
        from app.repositories.gold.serving import GoldServingRepository
        from app.repositories.gold.dashboard import GoldDashboardRepository
        return GoldDashboardRepository(GoldServingRepository(
            TrinoClient(settings.gold_trino_uri, settings.gold_trino_user),
            settings.gold_schema, settings.gold_channel,
        ))

    raise ValueError(
        f"Unsupported DASHBOARD_DATA_SOURCE: {settings.dashboard_data_source!r}. "
        "Register a repository for this source before enabling it."
    )
