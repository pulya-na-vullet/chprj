from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from neurolegal.contracts import SearchedArticle, SearchedChunk
from neurolegal.rag.api.app import app

pytestmark = pytest.mark.api_with_mocks


@pytest.fixture
def fake_results() -> list[SearchedArticle]:
    return [
        SearchedArticle(
            article_id=uuid4(),
            act_short_name="ГК РФ",
            act_kind="codex",
            number="421",
            title="Свобода договора",
            full_text="1. ...",
            matched_chunks=[
                SearchedChunk(chunk_id=uuid4(), path="ст. 421 ч. 1 ГК РФ", text="...", score=0.5),
            ],
            score=0.5,
        )
    ]


@pytest.mark.asyncio
async def test_search_returns_articles(fake_results: list[SearchedArticle]) -> None:
    from neurolegal.rag.api.deps import get_retrieval_service

    fake_svc = AsyncMock()
    fake_svc.search = AsyncMock(return_value=fake_results)
    app.dependency_overrides[get_retrieval_service] = lambda: fake_svc
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/search", params={"q": "свобода договора", "limit": 5})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert len(body["articles"]) == 1
    assert body["articles"][0]["number"] == "421"


@pytest.mark.asyncio
async def test_search_validates_q_length() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/search", params={"q": ""})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_retrieve_with_precomputed_vector(fake_results: list[SearchedArticle]) -> None:
    with patch(
        "neurolegal.rag.api.routes_search.hybrid_search", new=AsyncMock(return_value=fake_results)
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/retrieve",
                json={
                    "query_text": "свобода договора",
                    "query_vector": [0.1] * 1024,
                    "acts": ["ГК РФ"],
                    "limit": 5,
                },
            )

    assert response.status_code == 200
    assert len(response.json()["articles"]) == 1
