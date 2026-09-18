"""Integration test for GET /article exact lookup endpoint.

Marked db_only — skips when no real DATABASE_URL is available.
The assertions are tolerant of an empty corpus (no seeded data required).
"""

from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from neurolegal.rag.api.app import app
from neurolegal.rag.api.deps import db_session
from neurolegal.rag.store.db import get_sessionmaker

pytestmark = pytest.mark.db_only


@pytest_asyncio.fixture(loop_scope="module")
async def session() -> AsyncGenerator[AsyncSession, None]:
    async with get_sessionmaker()() as s:
        yield s
        await s.rollback()


@pytest.mark.asyncio(loop_scope="module")
async def test_article_returns_search_response_shape(session: AsyncSession) -> None:
    async def _override() -> AsyncGenerator[AsyncSession, None]:
        yield session

    app.dependency_overrides[db_session] = _override
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/article", params={"act": "ГК РФ", "number": "1"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert "articles" in body
    assert isinstance(body["articles"], list)


@pytest.mark.asyncio(loop_scope="module")
async def test_article_validates_empty_params(session: AsyncSession) -> None:
    async def _override() -> AsyncGenerator[AsyncSession, None]:
        yield session

    app.dependency_overrides[db_session] = _override
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/article", params={"act": "", "number": "1"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
