import httpx
import pytest

from app.core.config import Settings
from app.main import create_app
from app.repositories.base import DataSourceUnavailable
from app.repositories.mock.dashboard import MockDashboardRepository
from app.schemas.dashboard import DashboardData

pytestmark = pytest.mark.anyio


def source_data() -> DashboardData:
    return DashboardData.model_validate({
        "provinceSnapshots": [{
            "provinceCode": "92", "provinceName": "Cần Thơ", "aqi": 40,
            "status": "Tốt", "pm25": 12.75, "pm10": 23.5,
        }],
        "emissionRecords": [{
            "provinceCode": "92", "provinceName": "Cần Thơ", "year": 2026,
            "month": 9, "sector": "Agriculture", "emissionTonnes": 100.125,
        }],
        "emissionSectors": ["Agriculture"],
        "dashboardTrendRecords": [{
            "provinceCode": "92", "date": "2026-09-15", "pm25": 12.75,
            "pm10": 23.5, "o3": 10.2, "no2": 4.1, "so2": 2.3, "co": 0.65,
        }],
    })


class InMemoryRepository:
    def __init__(self, data: DashboardData):
        self.data = data

    def get_dashboard(self) -> DashboardData:
        return self.data


def client_for(repository):
    application = create_app(dashboard_repository=repository)
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://testserver",
    )


async def test_another_source_uses_same_api_without_mock_generation(monkeypatch):
    def fail_if_called(self):
        raise AssertionError("The mock source must not run")

    monkeypatch.setattr(MockDashboardRepository, "get_dashboard", fail_if_called)
    repository = InMemoryRepository(source_data())
    async with client_for(repository) as client:
        response = await client.get("/api/dashboard")
        assert response.status_code == 200
        assert response.json() == repository.data.model_dump(mode="json", by_alias=True, exclude_unset=True)
        # The service must not impose the demo provider's permanent cache.
        repository.data.province_snapshots[0].pm25 = 14.25
        updated = await client.get("/api/dashboard")
        assert updated.json()["provinceSnapshots"][0]["pm25"] == 14.25


async def test_empty_source_does_not_fall_back_to_mock():
    empty = DashboardData(
        province_snapshots=[], emission_records=[],
        emission_sectors=[], dashboard_trend_records=[],
    )
    async with client_for(InMemoryRepository(empty)) as client:
        response = await client.get("/api/dashboard")
    assert response.status_code == 200
    assert response.json() == empty.model_dump(mode="json", by_alias=True, exclude_unset=True)


async def test_source_outage_returns_503_without_demo_data_or_internal_details():
    class UnavailableRepository:
        def get_dashboard(self) -> DashboardData:
            raise DataSourceUnavailable("Internal connection details")

    async with client_for(UnavailableRepository()) as client:
        response = await client.get("/api/dashboard")
    assert response.status_code == 503
    assert response.json() == {"detail": "Dashboard data source is temporarily unavailable."}


@pytest.mark.parametrize("source", ["real", "unknown", ""])
def test_unimplemented_source_fails_instead_of_silently_using_mock(source):
    with pytest.raises(ValueError, match="Unsupported DASHBOARD_DATA_SOURCE"):
        create_app(Settings(dashboard_data_source=source))


def test_data_source_setting_is_read_from_environment(monkeypatch):
    monkeypatch.setenv("DASHBOARD_DATA_SOURCE", "unknown")
    with pytest.raises(ValueError, match="Unsupported DASHBOARD_DATA_SOURCE"):
        create_app()


def test_mock_response_mutation_does_not_corrupt_cached_data():
    repository = MockDashboardRepository()
    first = repository.get_dashboard()
    first.province_snapshots[0].pm25 = 999
    first.emission_records.clear()
    fresh = repository.get_dashboard()
    assert fresh.province_snapshots[0].pm25 == 48
    assert len(fresh.emission_records) == 20


def test_default_sample_path_stays_inside_backend(monkeypatch):
    from pathlib import Path
    from app.core.config import DEFAULT_PARQUET_PATH
    from app.etl.eac4 import DEFAULT_OUTPUT

    monkeypatch.delenv("DASHBOARD_PARQUET_PATH", raising=False)
    monkeypatch.delenv("DASHBOARD_DATA_SOURCE", raising=False)
    backend = Path(__file__).resolve().parents[1]
    assert DEFAULT_PARQUET_PATH == backend / "data/samples/cams/eac4_provinces"
    assert Settings.from_env().dashboard_parquet_path == DEFAULT_PARQUET_PATH
    assert DEFAULT_OUTPUT == DEFAULT_PARQUET_PATH


async def test_bundled_sample_runs_without_etl():
    from app.repositories.parquet.dashboard import ParquetDashboardRepository
    from app.core.config import DEFAULT_PARQUET_PATH

    async with client_for(ParquetDashboardRepository(DEFAULT_PARQUET_PATH)) as client:
        response = await client.get("/api/dashboard")
    assert response.status_code == 200
    body = response.json()
    assert len(body["provinceSnapshots"]) == 34
    assert body["dashboardTrendRecords"]
    assert body["metadata"]["source"] == "CAMS EAC4 sample"
    assert "Dữ liệu mẫu tạm thời" in body["metadata"]["note"]
