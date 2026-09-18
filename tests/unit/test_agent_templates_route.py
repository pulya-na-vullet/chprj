"""GET /templates на агенте: прокси витрины за get_current_user."""

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from neurolegal.agent.api.app import app
from neurolegal.agent.api.deps import get_templates_client
from neurolegal.agent.auth.deps import get_current_user
from neurolegal.agent.store.models import UserRow
from neurolegal.agent.tools.templates_client import TemplatesClientError
from neurolegal.contracts import TemplateSummary


def _fake_user() -> UserRow:
    return UserRow(
        id="u1",
        email="u1@example.com",
        password_hash="h",
        is_active=True,
        email_verified_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
    )


class _FakeClient:
    def __init__(self, fail: bool = False) -> None:
        self._fail = fail

    async def list_templates(self) -> list[TemplateSummary]:
        if self._fail:
            raise TemplatesClientError("down")
        return [
            TemplateSummary(
                slug="arenda", title="Аренда", category="Договоры", description="", field_count=2
            )
        ]


def test_templates_proxy_returns_published_list() -> None:
    app.dependency_overrides[get_templates_client] = lambda: _FakeClient()
    app.dependency_overrides[get_current_user] = _fake_user
    try:
        with TestClient(app) as tc:
            resp = tc.get("/templates")
        assert resp.status_code == 200
        assert [t["slug"] for t in resp.json()["templates"]] == ["arenda"]
    finally:
        app.dependency_overrides.clear()


def test_templates_proxy_maps_outage_to_503() -> None:
    app.dependency_overrides[get_templates_client] = lambda: _FakeClient(fail=True)
    app.dependency_overrides[get_current_user] = _fake_user
    try:
        with TestClient(app) as tc:
            resp = tc.get("/templates")
        assert resp.status_code == 503
    finally:
        app.dependency_overrides.clear()


def test_templates_proxy_requires_auth() -> None:
    app.dependency_overrides[get_templates_client] = lambda: _FakeClient()
    try:
        with TestClient(app) as tc:
            resp = tc.get("/templates")
        assert resp.status_code == 401
    finally:
        app.dependency_overrides.clear()
