"""Unit test for the agent's RAG HTTP client.

Verifies the agent talks to RAG over HTTP only — no direct imports from
``neurolegal.rag.*`` and a well-formed request body.
"""

import inspect
from typing import Any
from uuid import uuid4

import httpx
import pytest

from neurolegal.agent.tools import rag_client
from neurolegal.agent.tools.rag_client import RagClient
from neurolegal.contracts import SearchedArticle, SearchedChunk


def test_rag_client_does_not_import_rag_internals() -> None:
    """Boundary check: the client file mentions no ``neurolegal.rag.`` imports."""
    src = inspect.getsource(rag_client)
    # Allow string literals like 'neurolegal.rag.api.app:app' in docstrings;
    # disallow only actual `import neurolegal.rag` / `from neurolegal.rag` statements.
    for line in src.splitlines():
        stripped = line.strip()
        if stripped.startswith(("import neurolegal.rag", "from neurolegal.rag")):
            pytest.fail(f"rag_client imports rag internals: {line!r}")


@pytest.mark.asyncio
async def test_search_returns_parsed_articles(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_article = SearchedArticle(
        article_id=str(uuid4()),
        act_short_name="ВК РФ",
        act_kind="codex",
        number="3",
        title="Основные принципы",
        full_text="text",
        matched_chunks=[
            SearchedChunk(
                chunk_id=str(uuid4()),
                score=0.03,
                path="ст. 3 ВК РФ",
                text="snippet",
            )
        ],
        score=0.03,
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/search"
        params = list(request.url.params.multi_items())
        assert ("q", "налог") in params
        assert ("limit", "5") in params
        assert ("acts", "ВК РФ") in params
        return httpx.Response(200, json={"articles": [fake_article.model_dump(mode="json")]})

    real_client = httpx.AsyncClient

    def factory(**kwargs: Any) -> httpx.AsyncClient:
        kwargs.setdefault("transport", httpx.MockTransport(handler))
        return real_client(**kwargs)

    monkeypatch.setattr(rag_client.httpx, "AsyncClient", factory)
    client = RagClient(base_url="http://rag.test")
    articles = await client.search("налог", acts=["ВК РФ"], limit=5)

    assert len(articles) == 1
    assert articles[0].number == "3"
    assert articles[0].act_short_name == "ВК РФ"


@pytest.mark.asyncio
async def test_search_retries_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    """RagClient retries transient httpx errors, like the embedder does."""
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 3:
            raise httpx.ConnectError("boom")
        return httpx.Response(200, json={"articles": []})

    real_client = httpx.AsyncClient

    def factory(**kwargs: Any) -> httpx.AsyncClient:
        kwargs.setdefault("transport", httpx.MockTransport(handler))
        return real_client(**kwargs)

    monkeypatch.setattr(rag_client.httpx, "AsyncClient", factory)
    client = RagClient(base_url="http://rag.test")
    articles = await client.search("налог")

    assert articles == []
    assert calls["n"] == 3


@pytest.mark.asyncio
async def test_search_raises_rag_client_error_after_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("always down")

    real_client = httpx.AsyncClient

    def factory(**kwargs: Any) -> httpx.AsyncClient:
        kwargs.setdefault("transport", httpx.MockTransport(handler))
        return real_client(**kwargs)

    monkeypatch.setattr(rag_client.httpx, "AsyncClient", factory)
    client = RagClient(base_url="http://rag.test")
    with pytest.raises(rag_client.RagClientError):
        await client.search("налог")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body",
    [
        b"<html>proxy error</html>",  # 200 with non-JSON body
        b'{"unexpected": "shape"}',  # 200 with schema-drifted JSON
    ],
)
async def test_search_bad_200_body_raises_rag_client_error(
    monkeypatch: pytest.MonkeyPatch, body: bytes
) -> None:
    """A 200 with a broken body must degrade into RagClientError, not crash
    the agent turn with a raw JSONDecodeError/ValidationError."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=body, headers={"content-type": "application/json"})

    real_client = httpx.AsyncClient

    def factory(**kwargs: Any) -> httpx.AsyncClient:
        kwargs.setdefault("transport", httpx.MockTransport(handler))
        return real_client(**kwargs)

    monkeypatch.setattr(rag_client.httpx, "AsyncClient", factory)
    client = RagClient(base_url="http://rag.test")
    with pytest.raises(rag_client.RagClientError):
        await client.search("налог")


@pytest.mark.asyncio
async def test_search_fails_fast_on_422(monkeypatch: pytest.MonkeyPatch) -> None:
    """Deterministic 4xx must surface as RagClientError without retries."""
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(422, json={"detail": "q too long"})

    real_client = httpx.AsyncClient

    def factory(**kwargs: Any) -> httpx.AsyncClient:
        kwargs.setdefault("transport", httpx.MockTransport(handler))
        return real_client(**kwargs)

    monkeypatch.setattr(rag_client.httpx, "AsyncClient", factory)
    client = RagClient(base_url="http://rag.test")
    with pytest.raises(rag_client.RagClientError):
        await client.search("налог")
    assert calls["n"] == 1


@pytest.mark.asyncio
async def test_list_acts_returns_parsed_summaries(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/acts"
        return httpx.Response(
            200,
            json={
                "acts": [
                    {"short_name": "ГК РФ", "full_name": "Гражданский кодекс", "kind": "codex"}
                ]
            },
        )

    real_client = httpx.AsyncClient

    def factory(**kwargs: Any) -> httpx.AsyncClient:
        kwargs.setdefault("transport", httpx.MockTransport(handler))
        return real_client(**kwargs)

    monkeypatch.setattr(rag_client.httpx, "AsyncClient", factory)
    client = RagClient(base_url="http://rag.test")
    acts = await client.list_acts()

    assert len(acts) == 1
    assert acts[0].short_name == "ГК РФ"
    assert acts[0].kind == "codex"


@pytest.mark.asyncio
async def test_fetch_article_returns_parsed_articles(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_article = SearchedArticle(
        article_id=str(uuid4()),
        act_short_name="ГК РФ",
        act_kind="codex",
        number="1477",
        title="Объекты интеллектуальной собственности",
        full_text="text",
        matched_chunks=[],
        score=0.0,
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/article"
        params = dict(request.url.params)
        assert params.get("act") == "ГК РФ"
        assert params.get("number") == "1477"
        return httpx.Response(200, json={"articles": [fake_article.model_dump(mode="json")]})

    real_client = httpx.AsyncClient

    def factory(**kwargs: Any) -> httpx.AsyncClient:
        kwargs.setdefault("transport", httpx.MockTransport(handler))
        return real_client(**kwargs)

    monkeypatch.setattr(rag_client.httpx, "AsyncClient", factory)
    client = RagClient(base_url="http://rag.test")
    articles = await client.fetch_article("ГК РФ", "1477")

    assert len(articles) == 1
    assert articles[0].number == "1477"


@pytest.mark.asyncio
async def test_list_acts_raises_after_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    real_client = httpx.AsyncClient

    def factory(**kwargs: Any) -> httpx.AsyncClient:
        kwargs.setdefault("transport", httpx.MockTransport(handler))
        return real_client(**kwargs)

    monkeypatch.setattr(rag_client.httpx, "AsyncClient", factory)
    client = RagClient(base_url="http://rag.test")
    with pytest.raises(rag_client.RagClientError):
        await client.list_acts()
