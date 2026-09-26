from app.repositories.base import DashboardRepository
from app.schemas.dashboard import AdminDashboardData, DashboardData


class DashboardService:
    def __init__(self, repository: DashboardRepository) -> None:
        self._repository = repository

    def get_dashboard(self) -> DashboardData:
        # Source-specific generation, queries and caching belong in repositories.
        return self._repository.get_dashboard()

    def get_admin_dashboard(self) -> AdminDashboardData:
        admin_reader = getattr(self._repository, "get_admin_dashboard", None)
        if callable(admin_reader):
            return admin_reader()
        from app.repositories.mock.admin_dashboard import project_admin_dashboard

        return project_admin_dashboard(self._repository.get_dashboard())
