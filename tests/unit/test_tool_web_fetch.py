"""Unit tests for the web_fetch tool handler (SSRF guard + extraction)."""

import json
import socket
from typing import Any
from unittest.mock import MagicMock

import httpx
import pytest

from neurolegal.agent.chat.tools import web_fetch
from neurolegal.agent.chat.tools.base import ToolContext, ToolOutcome
from neurolegal.contracts import ToolsSettings


def _make_ctx(max_chars: int = 20000) -> ToolContext:
    tools = ToolsSettings()
    tools.web_fetch.max_chars = max_chars
    return ToolContext(
        rag_client=MagicMock(),
        acts=None,
        tools=tools,
    )


# ---------------------------------------------------------------------------
# SSRF / bad-scheme blocking
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/x",
        "http://10.0.0.1/",
        "http://169.254.169.254/",
        "ftp://example.com/",
        "not-a-url",
    ],
)
async def test_blocks_private_and_bad_scheme(url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """SSRF guard must block private IPs, loopback, link-local, and bad schemes — no HTTP."""
    http_called = {"called": False}

    # Patch getaddrinfo so that IPs resolve to themselves (no real DNS needed).
    original_getaddrinfo = socket.getaddrinfo

    def fake_getaddrinfo(host: str, port: Any, *args: Any, **kwargs: Any) -> list[Any]:
        # For dotted-decimal IPs, return a minimal addrinfo tuple with that IP.
        # For hostnames, fall through to the real resolver (which won't be called
        # for these test URLs since scheme check happens first or they are IPs).
        try:
            socket.inet_pton(socket.AF_INET, host)
            return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", (host, 0))]
        except OSError:
            pass
        try:
            socket.inet_pton(socket.AF_INET6, host)
            return [(socket.AF_INET6, socket.SOCK_STREAM, 0, "", (host, 0, 0, 0))]
        except OSError:
            pass
        return original_getaddrinfo(host, port, *args, **kwargs)

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)

    real_client = httpx.AsyncClient

    def factory(**kwargs: Any) -> httpx.AsyncClient:
        http_called["called"] = True
        return real_client(**kwargs)

    monkeypatch.setattr(web_fetch.httpx, "AsyncClient", factory)

    ctx = _make_ctx()
    out = await web_fetch.handle({"url": url}, ctx)

    assert isinstance(out, ToolOutcome)
    assert out.web_sources == [], f"Expected no web_sources for blocked url={url!r}"
    data = json.loads(out.tool_result)
    assert "error" in data, f"Expected 'error' key in tool_result for url={url!r}"
    assert http_called["called"] is False, f"HTTP must not be called for blocked url={url!r}"


# ---------------------------------------------------------------------------
# Successful fetch
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """Allowed URL + good response → WebSource with extracted text and title."""
    target_url = "https://example.com/article"
    html_body = (
        "<html><head><title>Тестовая страница</title></head><body><p>контент</p></body></html>"
    )
    extracted_text = "извлечённый текст"
    extracted_title = "Тестовая страница"

    # Bypass SSRF check
    monkeypatch.setattr(web_fetch, "_is_blocked", lambda url: False)

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == target_url
        return httpx.Response(200, text=html_body, headers={"content-type": "text/html"})

    real_client = httpx.AsyncClient

    def factory(**kwargs: Any) -> httpx.AsyncClient:
        kwargs.setdefault("transport", httpx.MockTransport(handler))
        return real_client(**kwargs)

    monkeypatch.setattr(web_fetch.httpx, "AsyncClient", factory)

    # Monkeypatch trafilatura so tests never parse real HTML
    import trafilatura

    monkeypatch.setattr(trafilatura, "extract", lambda html, **kw: extracted_text)

    fake_meta = MagicMock()
    fake_meta.title = extracted_title
    monkeypatch.setattr(trafilatura, "extract_metadata", lambda html, **kw: fake_meta)

    ctx = _make_ctx()
    out = await web_fetch.handle({"url": target_url}, ctx)

    assert isinstance(out, ToolOutcome)
    assert len(out.web_sources) == 1
    src = out.web_sources[0]
    assert src.url == target_url
    assert src.snippet == extracted_text
    assert src.title == extracted_title

    data = json.loads(out.tool_result)
    assert data["url"] == target_url
    assert data["title"] == extracted_title
    assert data["text"] == extracted_text


# ---------------------------------------------------------------------------
# Fetch error (5xx / network error)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_follows_redirect(monkeypatch: pytest.MonkeyPatch) -> None:
    """A 301 to an allowed URL is followed (most real sites redirect)."""
    start = "https://example.com/old"
    final = "https://example.com/new"
    monkeypatch.setattr(web_fetch, "_is_blocked", lambda url: False)

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == start:
            return httpx.Response(301, headers={"location": final})
        assert str(request.url) == final
        return httpx.Response(200, text="<html><body>ok</body></html>")

    real_client = httpx.AsyncClient

    def factory(**kwargs: Any) -> httpx.AsyncClient:
        kwargs.setdefault("transport", httpx.MockTransport(handler))
        return real_client(**kwargs)

    monkeypatch.setattr(web_fetch.httpx, "AsyncClient", factory)
    import trafilatura

    monkeypatch.setattr(trafilatura, "extract", lambda html, **kw: "текст")
    monkeypatch.setattr(trafilatura, "extract_metadata", lambda html, **kw: MagicMock(title="T"))

    out = await web_fetch.handle({"url": start}, _make_ctx())
    assert len(out.web_sources) == 1
    assert out.web_sources[0].snippet == "текст"


@pytest.mark.asyncio
async def test_redirect_to_private_blocked(monkeypatch: pytest.MonkeyPatch) -> None:
    """A redirect whose target resolves to a private IP is blocked (SSRF via redirect)."""
    start = "https://example.com/start"
    evil = "http://169.254.169.254/latest/meta-data"
    # First hop allowed; the redirect target must be re-validated and blocked.
    monkeypatch.setattr(web_fetch, "_is_blocked", lambda url: url != start)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": evil})

    real_client = httpx.AsyncClient

    def factory(**kwargs: Any) -> httpx.AsyncClient:
        kwargs.setdefault("transport", httpx.MockTransport(handler))
        return real_client(**kwargs)

    monkeypatch.setattr(web_fetch.httpx, "AsyncClient", factory)

    out = await web_fetch.handle({"url": start}, _make_ctx())
    assert out.web_sources == []
    assert "error" in json.loads(out.tool_result)


@pytest.mark.asyncio
async def test_fetch_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """HTTP error from allowed host → no web_sources, error in tool_result."""
    # Bypass SSRF check
    monkeypatch.setattr(web_fetch, "_is_blocked", lambda url: False)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="Internal Server Error")

    real_client = httpx.AsyncClient

    def factory(**kwargs: Any) -> httpx.AsyncClient:
        kwargs.setdefault("transport", httpx.MockTransport(handler))
        return real_client(**kwargs)

    monkeypatch.setattr(web_fetch.httpx, "AsyncClient", factory)

    ctx = _make_ctx()
    out = await web_fetch.handle({"url": "https://example.com/fail"}, ctx)

    assert isinstance(out, ToolOutcome)
    assert out.web_sources == []
    data = json.loads(out.tool_result)
    assert "error" in data
