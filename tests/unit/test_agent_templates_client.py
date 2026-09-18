"""Агентский HTTP-клиент templates-сервиса: парсинг, 404/422, ретраи.

Граница: клиент не импортирует neurolegal.templates.* (плюс общий AST-гард
в test_agent_boundary.py).
"""

import inspect
from typing import Any

import httpx
import pytest

from neurolegal.agent.tools import templates_client
from neurolegal.agent.tools.templates_client import (
    AgentTemplatesClient,
    TemplateRenderInvalidError,
    TemplatesNotFoundError,
)

DETAIL = {
    "slug": "arenda",
    "title": "Аренда",
    "category": "Договоры",
    "description": "",
    "field_count": 1,
    "fields": [{"name": "fio", "label": "ФИО", "hint": None, "kind": "text", "required": True}],
}


def test_client_does_not_import_templates_internals() -> None:
    src = inspect.getsource(templates_client)
    for line in src.splitlines():
        stripped = line.strip()
        if stripped.startswith(("import neurolegal.templates", "from neurolegal.templates")):
            pytest.fail(f"templates_client imports service internals: {line!r}")


def _patch(monkeypatch: pytest.MonkeyPatch, handler) -> None:  # type: ignore[no-untyped-def]
    real_client = httpx.AsyncClient

    def factory(**kwargs: Any) -> httpx.AsyncClient:
        kwargs.setdefault("transport", httpx.MockTransport(handler))
        return real_client(**kwargs)

    monkeypatch.setattr(templates_client.httpx, "AsyncClient", factory)


async def test_list_and_get_parse_contracts(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/templates":
            summary = {k: v for k, v in DETAIL.items() if k != "fields"}
            return httpx.Response(200, json={"templates": [summary]})
        assert request.url.path == "/templates/arenda"
        return httpx.Response(200, json=DETAIL)

    _patch(monkeypatch, handler)
    client = AgentTemplatesClient(base_url="http://tpl.test")
    templates = await client.list_templates()
    assert [t.slug for t in templates] == ["arenda"]
    detail = await client.get_template("arenda")
    assert detail.fields[0].name == "fio"


async def test_get_404_raises_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch(monkeypatch, lambda request: httpx.Response(404, json={"detail": "template not found"}))
    client = AgentTemplatesClient(base_url="http://tpl.test")
    with pytest.raises(TemplatesNotFoundError):
        await client.get_template("gone")


async def test_render_422_carries_structured_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    body = {"errors": [{"field": "fio", "code": "required", "message": "Обязательное поле"}]}
    _patch(monkeypatch, lambda request: httpx.Response(422, json=body))
    client = AgentTemplatesClient(base_url="http://tpl.test")
    with pytest.raises(TemplateRenderInvalidError) as exc_info:
        await client.render("arenda", {})
    assert exc_info.value.errors[0].field == "fio"
    assert exc_info.value.errors[0].code == "required"


async def test_render_returns_bytes_and_retries_transient(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 3:
            raise httpx.ConnectError("boom")
        assert request.url.path == "/templates/arenda/render"
        return httpx.Response(200, content=b"PK-bytes")

    _patch(monkeypatch, handler)
    client = AgentTemplatesClient(base_url="http://tpl.test")
    assert await client.render("arenda", {"fio": "И."}) == b"PK-bytes"
    assert calls["n"] == 3
