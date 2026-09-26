from app.repositories.base import DashboardRepository
from app.schemas.dashboard import DashboardData


class DashboardService:
    def __init__(self, repository: DashboardRepository) -> None:
        self._repository = repository

    def get_dashboard(self) -> DashboardData:
        # Source-specific generation, queries and caching belong in repositories.
        return self._repository.get_dashboard()
