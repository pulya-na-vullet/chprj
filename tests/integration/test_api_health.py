import pytest
from httpx import ASGITransport, AsyncClient

from neurolegal.rag.api.app import app

pytestmark = pytest.mark.db_only


@pytest.mark.asyncio
async def test_healthz_returns_ok() -> None:
    # Engine cache reset is handled by the autouse fixture in
    # tests/integration/conftest.py (`_reset_core_db_engine_cache`).
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/healthz")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["db"] == "ok"
