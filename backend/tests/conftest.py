import httpx
import pytest

from app.core.config import Settings
from app.main import create_app


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client():
    application = create_app(Settings(dashboard_data_source="mock"))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://testserver",
    ) as api_client:
        yield api_client
