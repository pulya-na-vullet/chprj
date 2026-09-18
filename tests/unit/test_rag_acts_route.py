"""GET /acts returns the distinct legislation acts (route shape, query stubbed)."""

import pytest
from fastapi.testclient import TestClient

import neurolegal.rag.api.routes_acts as routes_acts
from neurolegal.rag.api.app import app
from neurolegal.rag.api.deps import db_session
from neurolegal.rag.store.acts import ActCatalogEntry


async def _fake_session():  # type: ignore[no-untyped-def]
    yield None


def test_acts_endpoint_returns_distinct_acts(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_list_acts(session):  # type: ignore[no-untyped-def]
        return [
            ActCatalogEntry(short_name="ГК РФ", full_name="Гражданский кодекс", kind="codex"),
            ActCatalogEntry(short_name="КоАП РФ", full_name="Кодекс об адм. пр.", kind="codex"),
        ]

    monkeypatch.setattr(routes_acts, "list_acts", fake_list_acts)
    app.dependency_overrides[db_session] = _fake_session
    try:
        with TestClient(app) as tc:
            resp = tc.get("/acts")
        assert resp.status_code == 200
        acts = resp.json()["acts"]
        assert [a["short_name"] for a in acts] == ["ГК РФ", "КоАП РФ"]
        assert acts[0]["kind"] == "codex"
    finally:
        app.dependency_overrides.clear()
