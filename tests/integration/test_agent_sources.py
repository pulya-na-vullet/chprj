from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from neurolegal.agent.api.app import app
from neurolegal.agent.auth.deps import get_current_user
from neurolegal.agent.store.models import UserRow
from neurolegal.contracts import (
    SourceArticleDetail,
    SourceArticleListItem,
    SourceArticlesResponse,
    SourcesResponse,
    SourceSummary,
)

pytestmark = pytest.mark.api_with_mocks


def _fake_user() -> UserRow:
    return UserRow(
        id="u1",
        email="u1@example.com",
        password_hash="h",
        is_active=True,
        email_verified_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
    )


def _fake_client() -> AsyncMock:
    c = AsyncMock()
    c.list_sources = AsyncMock(
        return_value=SourcesResponse(
            sources=[
                SourceSummary(
                    source_doc_id="gk-1",
                    short_name="ГК РФ",
                    full_name="x",
                    kind="codex",
                    branch="Гражданское право",
                    redaction=None,
                    status="in_corpus",
                )
            ]
        )
    )
    aid = uuid4()
    c.source_articles = AsyncMock(
        return_value=SourceArticlesResponse(
            source_doc_id="gk-1",
            short_name="ГК РФ",
            articles=[SourceArticleListItem(article_id=aid, number="1", title="Начала")],
        )
    )
    c.article_detail = AsyncMock(
        return_value=SourceArticleDetail(
            article_id=aid, act_short_name="ГК РФ", number="1", title="Начала", full_text="…"
        )
    )
    return c


@pytest.mark.asyncio
async def test_agent_proxies_sources() -> None:
    from neurolegal.agent.api.deps import get_rag_client

    app.dependency_overrides[get_rag_client] = _fake_client
    app.dependency_overrides[get_current_user] = _fake_user
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            r1 = await client.get("/sources")
            r2 = await client.get("/sources/gk-1/articles")
            r3 = await client.get("/sources/articles/abc")
    finally:
        app.dependency_overrides.clear()

    assert r1.status_code == 200 and r1.json()["sources"][0]["short_name"] == "ГК РФ"
    assert r2.status_code == 200 and r2.json()["articles"][0]["number"] == "1"
    assert r3.status_code == 200 and r3.json()["full_text"] == "…"
