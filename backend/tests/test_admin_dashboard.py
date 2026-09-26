import httpx
import pytest

from app.main import create_app
from app.core.config import Settings

pytestmark = pytest.mark.anyio


async def test_admin_dashboard_includes_management_data_from_mock_backend():
    application = create_app(Settings(dashboard_data_source="mock"))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://testserver",
    ) as client:
        response = await client.get("/api/admin/dashboard")

    assert response.status_code == 200
    body = response.json()
    assert body["provinceSnapshots"]
    assert body["dashboardTrendRecords"]
    assert body["emissionRecords"]
    assert body["emissionSectors"]
    assert body["priorityAreas"]
    assert body["annualProvinceSummaries"]
    assert body["priorityAreas"][0]["provinceCode"] == "01"


async def test_admin_dashboard_projects_source_data_without_fabricating_missing_values():
    from app.repositories.parquet.dashboard import ParquetDashboardRepository
    from app.core.config import DEFAULT_PARQUET_PATH

    application = create_app(dashboard_repository=ParquetDashboardRepository(DEFAULT_PARQUET_PATH))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://testserver",
    ) as client:
        response = await client.get("/api/admin/dashboard")

    assert response.status_code == 200
    body = response.json()
    assert body["dashboardTrendRecords"]
    assert body["priorityAreas"]
    assert body["emissionRecords"] == []
    assert all(row.get("aqi") is None for row in body["dashboardTrendRecords"])
    assert all(row["totalEmissions"] is None for row in body["priorityAreas"])
