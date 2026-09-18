"""ASGI tests for the agent's internal /admin/users* endpoints (T-0022).

These routes are gated by X-Internal-Token, not get_current_user — they are
reached only by the RAG service's agent_client (server-to-server HTTP), never
directly by the browser. Mirrors the fixture/dispatch pattern in
tests/unit/test_agent_conversations_route.py (sync TestClient + a manual
event-loop run for async DB setup, to avoid nesting event loops).
"""

import asyncio
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from neurolegal.agent.api.app import app
from neurolegal.agent.auth.deps import get_auth_store
from neurolegal.agent.auth.store import AuthStore
from neurolegal.agent.store.conversation_store import ConversationStore
from neurolegal.agent.store.models import Base
from neurolegal.core.config import settings as core_settings
from neurolegal.core.security import verify_password


@pytest.fixture
def session() -> Iterator[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    async def _setup() -> AsyncSession:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        sm = async_sessionmaker(engine, expire_on_commit=False)
        return sm()

    s = asyncio.get_event_loop().run_until_complete(_setup())
    yield s
    asyncio.get_event_loop().run_until_complete(s.close())
    asyncio.get_event_loop().run_until_complete(engine.dispose())


def _client(session: AsyncSession) -> TestClient:
    app.dependency_overrides[get_auth_store] = lambda: AuthStore(session)
    return TestClient(app)


def test_list_users_empty(session: AsyncSession) -> None:
    try:
        resp = _client(session).get("/admin/users")
        assert resp.status_code == 200
        assert resp.json() == {"users": []}
    finally:
        app.dependency_overrides.clear()


async def _seed_two_users(session: AsyncSession) -> tuple[str, str]:
    auth = AuthStore(session)
    convs = ConversationStore(session)
    u1 = await auth.create_user(email="a@example.com", password_hash="h")
    await auth.commit()
    u2 = await auth.create_user(email="b@example.com", password_hash="h")
    await auth.commit()
    await convs.create_conversation(u1.id)
    await convs.create_conversation(u1.id)
    return u1.id, u2.id


def test_list_users_sorted_desc_with_conversation_counts(session: AsyncSession) -> None:
    asyncio.get_event_loop().run_until_complete(_seed_two_users(session))
    try:
        resp = _client(session).get("/admin/users")
        assert resp.status_code == 200
        body = resp.json()["users"]
        assert [u["email"] for u in body] == ["b@example.com", "a@example.com"]
        by_email = {u["email"]: u for u in body}
        assert by_email["a@example.com"]["conversation_count"] == 2
        assert by_email["b@example.com"]["conversation_count"] == 0
        assert by_email["a@example.com"]["is_active"] is True
        # T-0026: email_verified is gone from the operator DTO — every
        # account is active at registration, the column carried no signal.
        assert "email_verified" not in by_email["a@example.com"]
    finally:
        app.dependency_overrides.clear()


async def _seed_user_with_session(session: AsyncSession) -> tuple[str, str]:
    auth = AuthStore(session)
    user = await auth.create_user(email="c@example.com", password_hash="h")
    await auth.commit()
    await auth.create_session(
        user_id=user.id, token_hash="tok1", expires_at=datetime.now(UTC) + timedelta(days=1)
    )
    await auth.commit()
    return user.id, "tok1"


def test_patch_deactivate_deletes_all_sessions(session: AsyncSession) -> None:
    user_id, token_hash = asyncio.get_event_loop().run_until_complete(
        _seed_user_with_session(session)
    )
    try:
        resp = _client(session).patch(f"/admin/users/{user_id}", json={"is_active": False})
        assert resp.status_code == 200
        body = resp.json()
        assert body["is_active"] is False
        assert body["conversation_count"] == 0

        auth = AuthStore(session)
        remaining = asyncio.get_event_loop().run_until_complete(
            auth.get_session_by_hash(token_hash)
        )
        assert remaining is None
    finally:
        app.dependency_overrides.clear()


def test_patch_new_password_rehashes_and_kills_sessions(session: AsyncSession) -> None:
    """Operator password reset (T-0026): setting a new password re-hashes it
    and drops every session, without touching is_active."""
    user_id, token_hash = asyncio.get_event_loop().run_until_complete(
        _seed_user_with_session(session)
    )
    try:
        resp = _client(session).patch(
            f"/admin/users/{user_id}", json={"new_password": "operator-set-pw1"}
        )
        assert resp.status_code == 200
        assert resp.json()["is_active"] is True

        auth = AuthStore(session)
        user = asyncio.get_event_loop().run_until_complete(auth.get_user_by_id(user_id))
        assert user is not None
        assert user.password_hash != "h"
        assert verify_password("operator-set-pw1", user.password_hash)
        remaining = asyncio.get_event_loop().run_until_complete(
            auth.get_session_by_hash(token_hash)
        )
        assert remaining is None
    finally:
        app.dependency_overrides.clear()


def test_patch_empty_body_is_422(session: AsyncSession) -> None:
    user_id, _ = asyncio.get_event_loop().run_until_complete(_seed_user_with_session(session))
    try:
        resp = _client(session).patch(f"/admin/users/{user_id}", json={})
        assert resp.status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_patch_short_password_is_422(session: AsyncSession) -> None:
    user_id, _ = asyncio.get_event_loop().run_until_complete(_seed_user_with_session(session))
    try:
        resp = _client(session).patch(f"/admin/users/{user_id}", json={"new_password": "short12"})
        assert resp.status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_patch_unknown_user_is_404(session: AsyncSession) -> None:
    try:
        resp = _client(session).patch("/admin/users/does-not-exist", json={"is_active": False})
        assert resp.status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_no_internal_token_configured_is_open(session: AsyncSession) -> None:
    try:
        resp = _client(session).get("/admin/users")
        assert resp.status_code == 200
    finally:
        app.dependency_overrides.clear()


def test_internal_token_configured_rejects_missing_header(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(core_settings, "internal_token", "shared-secret")
    try:
        resp = _client(session).get("/admin/users")
        assert resp.status_code == 401
    finally:
        app.dependency_overrides.clear()


def test_internal_token_configured_rejects_wrong_value(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(core_settings, "internal_token", "shared-secret")
    try:
        resp = _client(session).get("/admin/users", headers={"X-Internal-Token": "wrong"})
        assert resp.status_code == 401
    finally:
        app.dependency_overrides.clear()


def test_internal_token_configured_accepts_matching_header(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(core_settings, "internal_token", "shared-secret")
    try:
        resp = _client(session).get("/admin/users", headers={"X-Internal-Token": "shared-secret"})
        assert resp.status_code == 200
    finally:
        app.dependency_overrides.clear()


def test_internal_token_gate_also_applies_to_patch(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    user_id, _ = asyncio.get_event_loop().run_until_complete(_seed_user_with_session(session))
    monkeypatch.setattr(core_settings, "internal_token", "shared-secret")
    try:
        resp = _client(session).patch(f"/admin/users/{user_id}", json={"is_active": False})
        assert resp.status_code == 401
    finally:
        app.dependency_overrides.clear()
