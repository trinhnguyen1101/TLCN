import json
from pathlib import Path

import pytest

from app.repositories.mock.dashboard import get_status

pytestmark = pytest.mark.anyio


async def test_health(client):
    response = await client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_dashboard_matches_original_frontend_data(client):
    # Captured by executing the original TypeScript module before migration.
    expected = json.loads(
        (Path(__file__).parent / "fixtures/dashboard.json").read_text(encoding="utf-8")
    )
    response = await client.get("/api/dashboard")
    assert response.status_code == 200
    assert response.json() == expected
    assert (await client.get("/api/dashboard")).json() == expected


@pytest.mark.parametrize(("aqi", "status"), [
    (50, "Tốt"), (51, "Trung bình"), (100, "Trung bình"),
    (101, "Kém"), (150, "Kém"), (151, "Xấu"),
])
def test_aqi_status_boundaries(aqi, status):
    assert get_status(aqi) == status


async def test_dashboard_schema_exposes_frontend_field_names(client):
    schema = (await client.get("/openapi.json")).json()
    assert set(schema["components"]["schemas"]["DashboardData"]["properties"]) == {
        "provinceSnapshots", "emissionRecords", "emissionSectors", "dashboardTrendRecords", "metadata",
    }
