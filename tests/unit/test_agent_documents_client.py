"""Unit test for the agent's documents-hub HTTP client (MockTransport)."""

import inspect
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest

from neurolegal.agent.tools import documents_client
from neurolegal.agent.tools.documents_client import (
    DocumentsClient,
    DocumentsClientError,
    DocumentsNotFoundError,
)


def test_client_does_not_import_hub_internals() -> None:
    src = inspect.getsource(documents_client)
    for line in src.splitlines():
        stripped = line.strip()
        if stripped.startswith(("import neurolegal.documents", "from neurolegal.documents")):
            pytest.fail(f"documents_client imports hub internals: {line!r}")


def _info_json(status: str = "processing") -> dict[str, Any]:
    return {
        "id": "d1",
        "owner_id": "default",
        "filename": "c.docx",
        "content_type": "application/octet-stream",
        "size": 10,
        "status": status,
        "parser": "docx",
        "page_count": None,
        "error": None,
        "created_at": datetime.now(UTC).isoformat(),
    }


def _patch(monkeypatch: pytest.MonkeyPatch, handler) -> None:
    real = httpx.AsyncClient

    def factory(**kwargs: Any) -> httpx.AsyncClient:
        kwargs.setdefault("transport", httpx.MockTransport(handler))
        return real(**kwargs)

    monkeypatch.setattr(documents_client.httpx, "AsyncClient", factory)


@pytest.mark.asyncio
async def test_upload_sends_multipart_and_owner_header(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/documents"
        assert request.headers["X-User-Id"] == "u1"
        assert b"c.docx" in request.content
        return httpx.Response(200, json=_info_json())

    _patch(monkeypatch, handler)
    client = DocumentsClient(base_url="http://hub.test")
    info = await client.upload(b"bytes", "c.docx", "application/octet-stream", owner_id="u1")
    assert info.id == "d1" and info.status == "processing"


@pytest.mark.asyncio
async def test_upload_does_not_replay_ambiguous_timeout(monkeypatch):
    """T-0143: POST /documents неидемпотентен. Read-timeout не доказывает,
    что сервис не создал запись, — повтор положил бы в библиотеку второй файл."""
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        raise httpx.ReadTimeout("timed out", request=request)

    _patch(monkeypatch, handler)
    client = DocumentsClient(base_url="http://hub.test")
    with pytest.raises(DocumentsClientError):
        await client.upload(b"bytes", "c.docx", "application/octet-stream", owner_id="u1")
    assert attempts == 1


@pytest.mark.asyncio
async def test_upload_retries_when_request_never_left(monkeypatch):
    """Отказ на установке соединения — запрос до сервиса не дошёл, повтор безопасен."""
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise httpx.ConnectError("connection refused", request=request)
        return httpx.Response(200, json=_info_json())

    _patch(monkeypatch, handler)
    client = DocumentsClient(base_url="http://hub.test")
    info = await client.upload(b"bytes", "c.docx", "application/octet-stream", owner_id="u1")
    assert info.id == "d1" and attempts == 2


@pytest.mark.asyncio
async def test_upload_sends_internal_token_when_configured(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["X-Internal-Token"] == "shared-secret"
        return httpx.Response(200, json=_info_json())

    _patch(monkeypatch, handler)
    client = DocumentsClient(base_url="http://hub.test", internal_token="shared-secret")
    await client.upload(b"bytes", "c.docx", "application/octet-stream", owner_id="u1")


@pytest.mark.asyncio
async def test_no_internal_token_header_when_unconfigured(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        assert "X-Internal-Token" not in request.headers
        return httpx.Response(200, json=_info_json())

    _patch(monkeypatch, handler)
    client = DocumentsClient(base_url="http://hub.test")
    await client.upload(b"bytes", "c.docx", "application/octet-stream", owner_id="u1")


@pytest.mark.asyncio
async def test_list_for_conversation_parses(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/conversations/conv-1/documents"
        assert request.headers["X-User-Id"] == "u1"
        return httpx.Response(200, json={"documents": [_info_json("ready")]})

    _patch(monkeypatch, handler)
    client = DocumentsClient(base_url="http://hub.test")
    docs = await client.list_for_conversation("conv-1", "u1")
    assert [d.status for d in docs] == ["ready"]


@pytest.mark.asyncio
async def test_get_content_parses(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/documents/d1/content"
        return httpx.Response(
            200,
            json={
                "id": "d1",
                "status": "ready",
                "full_text": "hello",
                "sections": [
                    {"number": "1", "title": "T", "text": "b", "level": 1, "start": 0, "end": 1}
                ],
            },
        )

    _patch(monkeypatch, handler)
    client = DocumentsClient(base_url="http://hub.test")
    content = await client.get_content("d1", "u1")
    assert content.sections[0].number == "1"


@pytest.mark.asyncio
async def test_download_location_reads_redirect_and_410(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["X-User-Id"] == "u1"
        if request.url.path == "/documents/live/download":
            return httpx.Response(307, headers={"location": "https://s3/presigned"})
        return httpx.Response(410)

    _patch(monkeypatch, handler)
    client = DocumentsClient(base_url="http://hub.test")
    assert await client.download_location("live", "u1") == "https://s3/presigned"
    assert await client.download_location("gone", "u1") is None


@pytest.mark.asyncio
async def test_get_info_sends_owner_header(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/documents/d1"
        assert request.headers["X-User-Id"] == "u1"
        return httpx.Response(200, json=_info_json())

    _patch(monkeypatch, handler)
    client = DocumentsClient(base_url="http://hub.test")
    info = await client.get_info("d1", "u1")
    assert info.id == "d1"


@pytest.mark.asyncio
async def test_http_error_becomes_client_error(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    _patch(monkeypatch, handler)
    client = DocumentsClient(base_url="http://hub.test")
    with pytest.raises(DocumentsClientError):
        await client.get_info("d1", "u1")


@pytest.mark.asyncio
async def test_get_info_404_becomes_not_found_error(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    _patch(monkeypatch, handler)
    client = DocumentsClient(base_url="http://hub.test")
    with pytest.raises(DocumentsNotFoundError):
        await client.get_info("missing", "u1")


@pytest.mark.asyncio
async def test_get_content_404_becomes_not_found_error(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    _patch(monkeypatch, handler)
    client = DocumentsClient(base_url="http://hub.test")
    with pytest.raises(DocumentsNotFoundError):
        await client.get_content("missing", "u1")


@pytest.mark.asyncio
async def test_download_location_404_becomes_not_found_error(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    _patch(monkeypatch, handler)
    client = DocumentsClient(base_url="http://hub.test")
    with pytest.raises(DocumentsNotFoundError):
        await client.download_location("missing", "u1")


@pytest.mark.asyncio
async def test_list_for_owner_sends_owner_header_and_parses(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/documents"
        assert request.headers["X-User-Id"] == "u1"
        return httpx.Response(
            200, json={"documents": [_info_json("ready"), _info_json("processing")]}
        )

    _patch(monkeypatch, handler)
    client = DocumentsClient(base_url="http://hub.test")
    docs = await client.list_for_owner("u1")
    assert [d.status for d in docs] == ["ready", "processing"]


@pytest.mark.asyncio
async def test_list_for_owner_custom_owner(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["X-User-Id"] == "acme"
        return httpx.Response(200, json={"documents": []})

    _patch(monkeypatch, handler)
    client = DocumentsClient(base_url="http://hub.test")
    assert await client.list_for_owner("acme") == []


@pytest.mark.asyncio
async def test_delete_sends_delete_and_succeeds_on_204(monkeypatch):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["path"] = request.url.path
        seen["user"] = request.headers.get("X-User-Id")
        return httpx.Response(204)

    _patch(monkeypatch, handler)
    client = DocumentsClient(base_url="http://hub.test")
    assert await client.delete("d1", "u1") is None
    assert seen == {"method": "DELETE", "path": "/documents/d1", "user": "u1"}


@pytest.mark.asyncio
async def test_delete_404_becomes_not_found_error(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    _patch(monkeypatch, handler)
    client = DocumentsClient(base_url="http://hub.test")
    with pytest.raises(DocumentsNotFoundError):
        await client.delete("missing", "u1")


@pytest.mark.asyncio
async def test_delete_500_becomes_client_error(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    _patch(monkeypatch, handler)
    client = DocumentsClient(base_url="http://hub.test")
    with pytest.raises(DocumentsClientError):
        await client.delete("d1", "u1")


@pytest.mark.asyncio
async def test_attach_sends_owner_header(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/documents/d1/attachments"
        assert request.headers["X-User-Id"] == "u1"
        return httpx.Response(200, json=_info_json())

    _patch(monkeypatch, handler)
    client = DocumentsClient(base_url="http://hub.test")
    info = await client.attach("d1", "conv-1", "u1")
    assert info.id == "d1"


@pytest.mark.asyncio
async def test_detach_sends_owner_header(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/documents/d1/attachments/conv-1"
        assert request.headers["X-User-Id"] == "u1"
        return httpx.Response(204)

    _patch(monkeypatch, handler)
    client = DocumentsClient(base_url="http://hub.test")
    await client.detach("d1", "conv-1", "u1")
