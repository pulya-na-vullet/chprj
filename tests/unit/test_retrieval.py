from unittest.mock import AsyncMock, patch

import pytest

from neurolegal.rag.retrieval.service import RetrievalService


class _StubEmbedder:
    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [[0.0] * 1024 for _ in texts]


@pytest.mark.asyncio
async def test_retrieval_service_calls_embedder_then_search() -> None:
    fake_embedder = AsyncMock()
    fake_embedder.embed = AsyncMock(return_value=[[0.1] * 1024])

    fake_session = AsyncMock()

    with patch(
        "neurolegal.rag.retrieval.service.hybrid_search", new=AsyncMock(return_value=[])
    ) as mock_hs:
        svc = RetrievalService(fake_embedder)
        out = await svc.search(fake_session, "свобода договора", acts=["ГК"], limit=5)

    assert out == []
    fake_embedder.embed.assert_called_once_with(["свобода договора"])
    mock_hs.assert_called_once()
    kwargs = mock_hs.call_args.kwargs
    assert kwargs["query_text"] == "свобода договора"
    assert kwargs["acts"] == ["ГК"]
    assert kwargs["limit"] == 5


@pytest.mark.asyncio
async def test_retrieval_service_forwards_min_score() -> None:
    svc = RetrievalService(_StubEmbedder())
    fake = AsyncMock(return_value=[])
    with patch("neurolegal.rag.retrieval.service.hybrid_search", fake):
        await svc.search(session=None, query="q", acts=None, limit=8, min_score=0.05)  # type: ignore[arg-type]
    _, kwargs = fake.call_args
    assert kwargs["min_score"] == 0.05


@pytest.mark.asyncio
async def test_retrieval_service_forwards_none_min_score() -> None:
    """None sentinel means "let the caller / route decide". The service
    forwards it verbatim to hybrid_search; routes interpret None as
    'use settings.rag_min_score', and a non-None value as an explicit override."""
    svc = RetrievalService(_StubEmbedder())
    fake = AsyncMock(return_value=[])
    with patch("neurolegal.rag.retrieval.service.hybrid_search", fake):
        await svc.search(session=None, query="q", acts=None, limit=8, min_score=None)  # type: ignore[arg-type]
    _, kwargs = fake.call_args
    assert kwargs["min_score"] is None
