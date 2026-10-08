from typing import Protocol

from app.schemas.dashboard import DashboardData
from app.services.temporal import DashboardQuery


class DashboardRepository(Protocol):
    """Each source maps its own records to this source-independent contract."""

    def get_dashboard(self, query: DashboardQuery | None = None) -> DashboardData:
        """Read a snapshot; raise DataSourceUnavailable for source outages."""
        ...


class DataSourceUnavailable(Exception):
    """A configured source could not be read; never substitute generated values."""
