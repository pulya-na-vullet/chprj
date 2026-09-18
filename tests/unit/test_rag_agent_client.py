"""Unit test for the RAG service's HTTP client to the agent (T-0022).

First (and so far only) rag→agent HTTP link, for the operator "users" tab —
RAG talks to the agent **only** through this client, never by importing
``neurolegal.agent.*``. Mirrors tests/unit/test_agent_rag_client.py.
"""

import inspect
from typing import Any

import httpx
import pytest

from neurolegal.rag import agent_client
from neurolegal.rag.agent_client import AgentClient, AgentClientError, AgentUserNotFoundError


def test_agent_client_does_not_import_agent_internals() -> None:
    """Boundary check: the client file mentions no ``neurolegal.agent.`` imports."""
    src = inspect.getsource(agent_client)
    for line in src.splitlines():
        stripped = line.strip()
        if stripped.startswith(("import neurolegal.agent", "from neurolegal.agent")):
            pytest.fail(f"agent_client imports agent internals: {line!r}")


def _patch(monkeypatch: pytest.MonkeyPatch, handler: Any) -> None:
    real_client = httpx.AsyncClient

    def factory(**kwargs: Any) -> httpx.AsyncClient:
        kwargs.setdefault("transport", httpx.MockTransport(handler))
        return real_client(**kwargs)

    monkeypatch.setattr(agent_client.httpx, "AsyncClient", factory)


def _user_json(**overrides: Any) -> dict[str, Any]:
    base = {
        "id": "u1",
        "email": "a@example.com",
        "is_active": True,
        "created_at": "2026-07-11T00:00:00Z",
        "conversation_count": 3,
    }
    base.update(overrides)
    return base


@pytest.mark.asyncio
async def test_list_users_returns_parsed_users(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/admin/users"
        return httpx.Response(200, json={"users": [_user_json()]})

    _patch(monkeypatch, handler)
    client = AgentClient(base_url="http://agent.test")
    users = await client.list_users()

    assert len(users) == 1
    assert users[0].email == "a@example.com"
    assert users[0].conversation_count == 3


@pytest.mark.asyncio
async def test_list_users_sends_internal_token_header_when_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["X-Internal-Token"] == "shared-secret"
        return httpx.Response(200, json={"users": []})

    _patch(monkeypatch, handler)
    client = AgentClient(base_url="http://agent.test", internal_token="shared-secret")
    await client.list_users()


@pytest.mark.asyncio
async def test_list_users_omits_header_when_not_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert "X-Internal-Token" not in request.headers
        return httpx.Response(200, json={"users": []})

    _patch(monkeypatch, handler)
    client = AgentClient(base_url="http://agent.test")
    await client.list_users()


@pytest.mark.asyncio
async def test_list_users_raises_agent_client_error_after_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("always down")

    _patch(monkeypatch, handler)
    client = AgentClient(base_url="http://agent.test")
    with pytest.raises(AgentClientError):
        await client.list_users()


@pytest.mark.asyncio
async def test_patch_user_sends_body_and_returns_parsed_user(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/admin/users/u1"
        assert request.method == "PATCH"
        import json as _json

        assert _json.loads(request.content) == {"is_active": False}
        return httpx.Response(200, json=_user_json(is_active=False))

    _patch(monkeypatch, handler)
    client = AgentClient(base_url="http://agent.test")
    user = await client.patch_user("u1", is_active=False)

    assert user.is_active is False


@pytest.mark.asyncio
async def test_patch_user_sends_only_provided_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    """Operator password reset: an is_active-less PATCH must not send
    `is_active: null` — the agent treats absent and null differently."""

    def handler(request: httpx.Request) -> httpx.Response:
        import json as _json

        assert _json.loads(request.content) == {"new_password": "operator-set-pw1"}
        return httpx.Response(200, json=_user_json())

    _patch(monkeypatch, handler)
    client = AgentClient(base_url="http://agent.test")
    user = await client.patch_user("u1", new_password="operator-set-pw1")

    assert user.email == "a@example.com"


@pytest.mark.asyncio
async def test_patch_user_404_raises_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"detail": "user_not_found"})

    _patch(monkeypatch, handler)
    client = AgentClient(base_url="http://agent.test")
    with pytest.raises(AgentUserNotFoundError):
        await client.patch_user("missing", is_active=False)


@pytest.mark.asyncio
async def test_patch_user_401_raises_agent_client_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """A misconfigured shared secret must surface as a generic client error
    (the route layer maps it to 502), not crash the proxy route."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"detail": "invalid_internal_token"})

    _patch(monkeypatch, handler)
    client = AgentClient(base_url="http://agent.test")
    with pytest.raises(AgentClientError):
        await client.patch_user("u1", is_active=False)
