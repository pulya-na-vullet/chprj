from pathlib import Path
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from neurolegal.rag.api.app import app

pytestmark = pytest.mark.api_with_mocks


@pytest.mark.asyncio
async def test_sources_lists_manifest_with_status() -> None:
    from datetime import datetime

    from neurolegal.rag.api.deps import db_session, get_manifest_path
    from neurolegal.rag.store.admin import ActDbStats

    manifest_path = Path("corpus/manifest.yaml")
    fake_stats = [
        ActDbStats(
            act_id="a",
            source_doc_id="gk-1",
            short_name="ГК РФ",
            full_name="x",
            kind="codex",
            ingested_at=datetime(2026, 1, 1),
            articles_count=1,
            chunks_count=1,
        )
    ]
    app.dependency_overrides[db_session] = lambda: None
    app.dependency_overrides[get_manifest_path] = lambda: manifest_path
    try:
        with patch(
            "neurolegal.rag.api.routes_sources.act_stats", AsyncMock(return_value=fake_stats)
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/sources")
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    body = resp.json()
    assert "sources" in body and len(body["sources"]) >= 30
    assert {"in_corpus", "planned"} >= {s["status"] for s in body["sources"]}
    # client-safe: no operator fields leaked
    assert all("docx_path" not in s and "chunks_count" not in s for s in body["sources"])


@pytest.mark.asyncio
async def test_source_articles() -> None:
    from neurolegal.rag.api.deps import db_session
    from neurolegal.rag.store.admin import ArticleListEntry

    app.dependency_overrides[db_session] = lambda: None
    entries = [
        ArticleListEntry(article_id=str(uuid4()), number="1", title="Начала", chunks_count=2)
    ]
    try:
        with patch(
            "neurolegal.rag.api.routes_sources.list_articles", AsyncMock(return_value=entries)
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/sources/gk-1/articles")
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    body = resp.json()
    assert body["source_doc_id"] == "gk-1"
    assert body["articles"][0]["number"] == "1"


@pytest.mark.asyncio
async def test_article_detail_404() -> None:
    from neurolegal.rag.api.deps import db_session

    app.dependency_overrides[db_session] = lambda: None
    try:
        with patch(
            "neurolegal.rag.api.routes_sources.article_detail", AsyncMock(return_value=None)
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get(f"/sources/articles/{uuid4()}")
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 404
