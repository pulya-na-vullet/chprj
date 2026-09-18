"""ASGI tests for the RAG service's /admin/users* proxy (T-0022).

Thin proxy over neurolegal.rag.agent_client — the fake client below stands in for
the real HTTP hop, mirroring the dependency_overrides pattern used by
tests/integration/test_admin_agent_api.py.
"""

from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient

from neurolegal.contracts import AdminUserOut
from neurolegal.rag.agent_client import (
    AgentAuthMisconfiguredError,
    AgentClientError,
    AgentUserNotFoundError,
)
from neurolegal.rag.api.app import app
from neurolegal.rag.api.deps import get_agent_client

pytestmark = pytest.mark.asyncio


def _user(**overrides: object) -> AdminUserOut:
    base: dict[str, object] = {
        "id": "u1",
        "email": "a@example.com",
        "is_active": True,
        "created_at": datetime.now(UTC),
        "conversation_count": 2,
    }
    base.update(overrides)
    return AdminUserOut.model_validate(base)


class _FakeAgentClient:
    def __init__(
        self,
        users: list[AdminUserOut] | None = None,
        list_error: Exception | None = None,
        patch_result: AdminUserOut | None = None,
        patch_error: Exception | None = None,
    ) -> None:
        self._users = users or []
        self._list_error = list_error
        self._patch_result = patch_result
        self._patch_error = patch_error

    async def list_users(self) -> list[AdminUserOut]:
        if self._list_error:
            raise self._list_error
        return self._users

    async def patch_user(
        self, user_id: str, *, is_active: bool | None = None, new_password: str | None = None
    ) -> AdminUserOut:
        if self._patch_error:
            raise self._patch_error
        self.last_patch = {"user_id": user_id, "is_active": is_active, "new_password": new_password}
        assert self._patch_result is not None
        return self._patch_result


async def _client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_list_users_proxies_agent_response() -> None:
    app.dependency_overrides[get_agent_client] = lambda: _FakeAgentClient(users=[_user()])
    try:
        async with await _client() as c:
            resp = await c.get("/admin/users")
        assert resp.status_code == 200
        assert resp.json()["users"][0]["email"] == "a@example.com"
    finally:
        app.dependency_overrides.clear()


async def test_list_users_agent_unavailable_returns_502() -> None:
    app.dependency_overrides[get_agent_client] = lambda: _FakeAgentClient(
        list_error=AgentClientError("boom")
    )
    try:
        async with await _client() as c:
            resp = await c.get("/admin/users")
        assert resp.status_code == 502
        assert resp.json()["detail"] != "agent_auth_misconfigured"
    finally:
        app.dependency_overrides.clear()


async def test_list_users_agent_auth_misconfigured_is_distinguishable() -> None:
    """(c): a 401 from the agent (bad/missing internal token) is a config
    error on this service, not a generic "agent unavailable" outage — the
    proxy must not collapse the two into the same message."""
    app.dependency_overrides[get_agent_client] = lambda: _FakeAgentClient(
        list_error=AgentAuthMisconfiguredError("agent rejected internal token")
    )
    try:
        async with await _client() as c:
            resp = await c.get("/admin/users")
        assert resp.status_code == 502
        assert resp.json()["detail"] == "agent_auth_misconfigured"
    finally:
        app.dependency_overrides.clear()


async def test_patch_user_proxies_agent_response() -> None:
    app.dependency_overrides[get_agent_client] = lambda: _FakeAgentClient(
        patch_result=_user(is_active=False)
    )
    try:
        async with await _client() as c:
            resp = await c.patch("/admin/users/u1", json={"is_active": False})
        assert resp.status_code == 200
        assert resp.json()["is_active"] is False
    finally:
        app.dependency_overrides.clear()


async def test_patch_user_forwards_new_password() -> None:
    fake = _FakeAgentClient(patch_result=_user())
    app.dependency_overrides[get_agent_client] = lambda: fake
    try:
        async with await _client() as c:
            resp = await c.patch("/admin/users/u1", json={"new_password": "operator-set-pw1"})
        assert resp.status_code == 200
        assert fake.last_patch == {
            "user_id": "u1",
            "is_active": None,
            "new_password": "operator-set-pw1",
        }
    finally:
        app.dependency_overrides.clear()


async def test_patch_user_not_found_returns_404() -> None:
    app.dependency_overrides[get_agent_client] = lambda: _FakeAgentClient(
        patch_error=AgentUserNotFoundError("missing")
    )
    try:
        async with await _client() as c:
            resp = await c.patch("/admin/users/missing", json={"is_active": False})
        assert resp.status_code == 404
    finally:
        app.dependency_overrides.clear()


async def test_patch_user_agent_unavailable_returns_502() -> None:
    app.dependency_overrides[get_agent_client] = lambda: _FakeAgentClient(
        patch_error=AgentClientError("boom")
    )
    try:
        async with await _client() as c:
            resp = await c.patch("/admin/users/u1", json={"is_active": False})
        assert resp.status_code == 502
        assert resp.json()["detail"] != "agent_auth_misconfigured"
    finally:
        app.dependency_overrides.clear()


async def test_patch_user_agent_auth_misconfigured_is_distinguishable() -> None:
    app.dependency_overrides[get_agent_client] = lambda: _FakeAgentClient(
        patch_error=AgentAuthMisconfiguredError("agent rejected internal token")
    )
    try:
        async with await _client() as c:
            resp = await c.patch("/admin/users/u1", json={"is_active": False})
        assert resp.status_code == 502
        assert resp.json()["detail"] == "agent_auth_misconfigured"
    finally:
        app.dependency_overrides.clear()
