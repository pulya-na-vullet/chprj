"""Unit tests for /embed validation. No DB or external services needed —
the embedder dependency is overridden with a stub so we exercise only the
Pydantic validation surface."""

from typing import Any
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from neurolegal.rag.api.app import app
from neurolegal.rag.api.deps import get_embedder


@pytest.fixture(autouse=True)
def _stub_embedder() -> Any:
    """Replace the real embedder with an AsyncMock so the 422 path doesn't try
    to call OpenRouter."""

    fake = AsyncMock(return_value=[[0.0] * 1024])
    app.dependency_overrides[get_embedder] = lambda: fake
    yield
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_embed_rejects_oversize_text() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/embed", json={"texts": ["x" * 8001]})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_embed_rejects_oversize_batch() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/embed", json={"texts": ["x" * 3000] * 100})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_embed_accepts_at_per_text_limit() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/embed", json={"texts": ["x" * 8000]})
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_embed_accepts_below_batch_limit() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/embed", json={"texts": ["x" * 2000] * 100})
    assert resp.status_code == 200
