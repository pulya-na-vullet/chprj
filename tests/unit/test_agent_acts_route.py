from datetime import UTC, datetime

from fastapi.testclient import TestClient

from neurolegal.agent.api.app import app
from neurolegal.agent.api.deps import get_rag_client
from neurolegal.agent.auth.deps import get_current_user
from neurolegal.agent.store.models import UserRow
from neurolegal.agent.tools.rag_client import RagClientError
from neurolegal.contracts import ActSummary


class _FakeRag:
    def __init__(self, *, fail: bool = False) -> None:
        self._fail = fail

    async def list_acts(self):  # type: ignore[no-untyped-def]
        if self._fail:
            raise RagClientError("down")
        return [ActSummary(short_name="ГК РФ", full_name="Гражданский кодекс", kind="codex")]


def _fake_user() -> UserRow:
    return UserRow(
        id="u1",
        email="u1@example.com",
        password_hash="h",
        is_active=True,
        email_verified_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
    )


def test_acts_proxied() -> None:
    app.dependency_overrides[get_rag_client] = lambda: _FakeRag()
    app.dependency_overrides[get_current_user] = _fake_user
    try:
        with TestClient(app) as tc:
            resp = tc.get("/acts")
        assert resp.status_code == 200
        assert resp.json()["acts"][0]["short_name"] == "ГК РФ"
    finally:
        app.dependency_overrides.clear()


def test_acts_returns_503_when_rag_down() -> None:
    app.dependency_overrides[get_rag_client] = lambda: _FakeRag(fail=True)
    app.dependency_overrides[get_current_user] = _fake_user
    try:
        with TestClient(app) as tc:
            resp = tc.get("/acts")
        assert resp.status_code == 503
    finally:
        app.dependency_overrides.clear()
