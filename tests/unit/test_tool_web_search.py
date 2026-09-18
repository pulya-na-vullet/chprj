"""Unit tests for the web_search tool handler."""

import json
from typing import Any
from unittest.mock import MagicMock

import httpx
import pytest

from neurolegal.agent.chat.tools import web_search
from neurolegal.agent.chat.tools.base import ToolContext, ToolOutcome
from neurolegal.contracts import ToolsSettings


def _make_ctx(
    tavily_api_key: str | None = None,
    max_results: int = 5,
) -> ToolContext:
    tools = ToolsSettings()
    tools.web_search.max_results = max_results
    return ToolContext(
        rag_client=MagicMock(),
        acts=None,
        tools=tools,
        tavily_api_key=tavily_api_key,
    )


@pytest.mark.asyncio
async def test_no_key_degrades(monkeypatch: pytest.MonkeyPatch) -> None:
    """No key → error outcome, no web_sources, unavailable stays False, no HTTP call."""
    http_called = {"called": False}

    real_client = httpx.AsyncClient

    def factory(**kwargs: Any) -> httpx.AsyncClient:
        http_called["called"] = True
        return real_client(**kwargs)

    monkeypatch.setattr(web_search.httpx, "AsyncClient", factory)

    ctx = _make_ctx(tavily_api_key=None)
    out = await web_search.handle({"query": "налог"}, ctx)

    assert isinstance(out, ToolOutcome)
    assert out.web_sources == []
    assert out.unavailable is False
    assert http_called["called"] is False
    # tool_result must signal the problem
    data = json.loads(out.tool_result)
    assert "error" in data


@pytest.mark.asyncio
async def test_returns_sources(monkeypatch: pytest.MonkeyPatch) -> None:
    """Valid key + successful Tavily response → 2 WebSource items."""
    tavily_response = {
        "results": [
            {"url": "https://example.com/1", "title": "Title One", "content": "Snippet one"},
            {"url": "https://example.com/2", "title": "Title Two", "content": "Snippet two"},
        ]
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert "api.tavily.com" in str(request.url)
        body = json.loads(request.content)
        assert body["api_key"] == "fake-key"
        assert body["query"] == "налог"
        return httpx.Response(200, json=tavily_response)

    real_client = httpx.AsyncClient

    def factory(**kwargs: Any) -> httpx.AsyncClient:
        kwargs.setdefault("transport", httpx.MockTransport(handler))
        return real_client(**kwargs)

    monkeypatch.setattr(web_search.httpx, "AsyncClient", factory)

    ctx = _make_ctx(tavily_api_key="fake-key")
    out = await web_search.handle({"query": "налог"}, ctx)

    assert out.unavailable is False
    assert len(out.web_sources) == 2
    assert out.web_sources[0].url == "https://example.com/1"
    assert out.web_sources[0].title == "Title One"
    assert out.web_sources[0].snippet == "Snippet one"
    assert out.web_sources[1].url == "https://example.com/2"

    # Sources must also appear in the tool_result JSON
    result_data = json.loads(out.tool_result)
    assert "results" in result_data
    assert len(result_data["results"]) == 2
    assert result_data["results"][0]["url"] == "https://example.com/1"


@pytest.mark.asyncio
async def test_empty_query(monkeypatch: pytest.MonkeyPatch) -> None:
    """Whitespace-only query → error outcome, no HTTP call."""
    http_called = {"called": False}

    real_client = httpx.AsyncClient

    def factory(**kwargs: Any) -> httpx.AsyncClient:
        http_called["called"] = True
        return real_client(**kwargs)

    monkeypatch.setattr(web_search.httpx, "AsyncClient", factory)

    ctx = _make_ctx(tavily_api_key="fake-key")
    out = await web_search.handle({"query": "   "}, ctx)

    assert out.web_sources == []
    assert out.unavailable is False
    assert http_called["called"] is False
    data = json.loads(out.tool_result)
    assert "error" in data


@pytest.mark.asyncio
async def test_tavily_error_degrades(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tavily 500 → graceful degradation: no web_sources, unavailable=False."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"message": "internal error"})

    real_client = httpx.AsyncClient

    def factory(**kwargs: Any) -> httpx.AsyncClient:
        kwargs.setdefault("transport", httpx.MockTransport(handler))
        return real_client(**kwargs)

    monkeypatch.setattr(web_search.httpx, "AsyncClient", factory)

    ctx = _make_ctx(tavily_api_key="fake-key")
    out = await web_search.handle({"query": "налог"}, ctx)

    assert out.web_sources == []
    assert out.unavailable is False
    data = json.loads(out.tool_result)
    assert "error" in data
