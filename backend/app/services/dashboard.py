from app.repositories.base import DashboardRepository
from app.schemas.dashboard import AdminDashboardData, DashboardData
from app.services.admin_projection import project_admin_dashboard
from app.services.temporal import DashboardQuery


class DashboardService:
    def __init__(self, repository: DashboardRepository) -> None:
        self._repository = repository

    def get_dashboard(self, query: DashboardQuery | None = None) -> DashboardData:
        # Source-specific generation, queries and caching belong in repositories.
        return self._repository.get_dashboard(query) if query else self._repository.get_dashboard()

    def get_admin_dashboard(self, query: DashboardQuery | None = None) -> AdminDashboardData:
        admin_reader = getattr(self._repository, "get_admin_dashboard", None)
        if callable(admin_reader):
            return admin_reader(query) if query else admin_reader()
        return project_admin_dashboard(self.get_dashboard(query))
