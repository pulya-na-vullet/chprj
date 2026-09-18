from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from neurolegal.rag.api.app import app
from neurolegal.rag.api.deps import get_embedder

pytestmark = pytest.mark.api_with_mocks


@pytest.mark.asyncio
async def test_embed_returns_vectors() -> None:
    fake_embedder = AsyncMock()
    fake_embedder.embed = AsyncMock(return_value=[[0.1] * 1024, [0.2] * 1024])
    app.dependency_overrides[get_embedder] = lambda: fake_embedder
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/embed", json={"texts": ["a", "b"]})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert len(body["vectors"]) == 2
    assert all(len(v) == 1024 for v in body["vectors"])


@pytest.mark.asyncio
async def test_embed_validates_empty_texts() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/embed", json={"texts": []})
    assert response.status_code == 422
