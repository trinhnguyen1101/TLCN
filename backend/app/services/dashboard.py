from collections import OrderedDict
from threading import Lock
from app.services.analytics import AnalyticsQuery, DashboardAnalytics, build_analytics
from app.repositories.base import DashboardRepository
from app.schemas.dashboard import AdminDashboardData, DashboardData
from app.services.admin_projection import project_admin_dashboard
from app.services.temporal import DashboardQuery


class DashboardService:
    def __init__(self, repository: DashboardRepository) -> None:
        self._repository = repository
        self._analytics_cache = OrderedDict()
        self._analytics_lock = Lock()

    def get_dashboard(self, query: DashboardQuery | None = None) -> DashboardData:
        # Source-specific generation, queries and caching belong in repositories.
        return self._repository.get_dashboard(query) if query else self._repository.get_dashboard()

    def get_admin_dashboard(self, query: DashboardQuery | None = None) -> AdminDashboardData:
        admin_reader = getattr(self._repository, "get_admin_dashboard", None)
        if callable(admin_reader):
            return admin_reader(query) if query else admin_reader()
        return project_admin_dashboard(self.get_dashboard(query))

    def get_analytics(self, query: AnalyticsQuery, temporal_query: DashboardQuery | None = None) -> DashboardAnalytics:
        if temporal_query is not None:
            data = self._repository.get_dashboard(temporal_query)
            return build_analytics(data, query, temporal_query.resolution)
        reader = getattr(self._repository, 'get_analytics', None)
        if callable(reader):
            return reader(query)
        # Read before consulting the cache: outages and generation changes must
        # remain visible. Legacy repository's unbounded read is its monthly view.
        data = self._repository.get_dashboard()
        generation = data.metadata.generation if data.metadata else None
        key = (generation, query.model_dump_json())
        if generation is not None:
            with self._analytics_lock:
                if key in self._analytics_cache:
                    self._analytics_cache.move_to_end(key)
                    return self._analytics_cache[key].model_copy(deep=True)
        result = build_analytics(data, query)
        if generation is not None:
            with self._analytics_lock:
                self._analytics_cache[key] = result
                self._analytics_cache.move_to_end(key)
                while len(self._analytics_cache) > 32:
                    self._analytics_cache.popitem(last=False)
        return result.model_copy(deep=True)
