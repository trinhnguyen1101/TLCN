from collections import OrderedDict
from threading import Lock
from app.services.analytics import AnalyticsQuery, DashboardAnalytics, build_analytics
from app.repositories.base import DashboardRepository
from app.schemas.dashboard import AdminDashboardData, DashboardData


class DashboardService:
    def __init__(self, repository: DashboardRepository) -> None:
        self._repository = repository
        self._analytics_cache = OrderedDict()
        self._analytics_lock = Lock()

    def get_dashboard(self) -> DashboardData:
        # Source-specific generation, queries and caching belong in repositories.
        return self._repository.get_dashboard()

    def get_admin_dashboard(self) -> AdminDashboardData:
        admin_reader = getattr(self._repository, "get_admin_dashboard", None)
        if callable(admin_reader):
            return admin_reader()
        from app.repositories.mock.admin_dashboard import project_admin_dashboard

        return project_admin_dashboard(self._repository.get_dashboard())

    def get_analytics(self, query: AnalyticsQuery) -> DashboardAnalytics:
        data = self._repository.get_dashboard()
        generation = data.metadata.generation if data.metadata else None
        key = (generation, query.model_dump_json())
        # Only cache versioned sources; new generations can never reuse old results.
        with self._analytics_lock:
            if generation is not None and key in self._analytics_cache:
                self._analytics_cache.move_to_end(key)
                return self._analytics_cache[key]
        result = build_analytics(data, query)
        if generation is not None:
            with self._analytics_lock:
                self._analytics_cache[key] = result
                while len(self._analytics_cache) > 32:
                    self._analytics_cache.popitem(last=False)
        return result
