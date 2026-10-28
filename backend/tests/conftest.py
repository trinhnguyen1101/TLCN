"""Explicit isolated ASGI fixture for legacy monthly analytics contract tests."""
import pytest
from httpx import ASGITransport, AsyncClient
from app.main import create_app
from app.core.config import Settings
from app.schemas.dashboard import DashboardData, DashboardTrendRecord, ProvinceSnapshot
from datetime import date


@pytest.fixture
def anyio_backend():
    return 'asyncio'


@pytest.fixture
async def client():
    data = DashboardData(
        province_snapshots=[ProvinceSnapshot(province_code=c, province_name=c,
                            aqi=None, status=None, pm25=None, pm10=None) for c in ['a','b','c']],
        dashboard_trend_records=[DashboardTrendRecord(province_code=c, date=date(2025,m,1),
                pm25=v, pm10=v, o3=None, no2=None, so2=None, co=None)
                for c,m,v in [('a',1,10),('a',2,15),('a',3,30),('b',1,20),('b',2,25),('b',3,None)]],
        emission_records=[], emission_sectors=[])

    class MonthlyFixtureRepository:
        def get_dashboard(self, query=None):
            return data.model_copy(deep=True)

    app = create_app(Settings(), MonthlyFixtureRepository())
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as session:
        yield session
