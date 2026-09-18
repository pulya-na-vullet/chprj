import pytest
from httpx import ASGITransport, AsyncClient

from neurolegal.contracts import OpenRouterModel
from neurolegal.rag.api import routes_admin_agent
from neurolegal.rag.api.app import app

pytestmark = pytest.mark.api_with_mocks


async def _client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_get_settings_returns_defaults(tmp_path):
    from neurolegal.rag.api.deps import get_agent_settings_path

    settings_path = tmp_path / "agent_settings.yaml"
    app.dependency_overrides[get_agent_settings_path] = lambda: settings_path
    try:
        async with await _client() as c:
            resp = await c.get("/admin/agent/settings")
        assert resp.status_code == 200
        assert resp.json()["model"] == "qwen/qwen3.6-flash"
    finally:
        app.dependency_overrides.clear()


async def test_put_then_get_persists(tmp_path):
    from neurolegal.rag.api.deps import get_agent_settings_path

    settings_path = tmp_path / "agent_settings.yaml"
    app.dependency_overrides[get_agent_settings_path] = lambda: settings_path
    try:
        async with await _client() as c:
            body = {
                "model": "a/b",
                "generation": {"temperature": 0.3},
                "behavior": {"max_tool_iterations": 2, "tool_choice": "auto"},
                "tools": {"rag_search": {"enabled": True, "limit": 5, "min_score": 0.0}},
            }
            put = await c.put("/admin/agent/settings", json=body)
            assert put.status_code == 200
            got = await c.get("/admin/agent/settings")
        assert got.json()["model"] == "a/b"
        assert got.json()["tools"]["rag_search"]["limit"] == 5
    finally:
        app.dependency_overrides.clear()


async def test_get_models(monkeypatch):
    async def fake_fetch(**_):
        return [OpenRouterModel(id="a/b", name="A B", context_length=1000, supports_tools=True)]

    monkeypatch.setattr(routes_admin_agent, "fetch_models", fake_fetch)
    async with await _client() as c:
        resp = await c.get("/admin/agent/models")
    assert resp.status_code == 200
    assert resp.json()["models"][0]["id"] == "a/b"


async def test_get_defaults_returns_builtin_prompts():
    from neurolegal.core.agent_prompts import DEFAULT_SYSTEM_PROMPT_LEGAL

    async with await _client() as c:
        resp = await c.get("/admin/agent/defaults")
    assert resp.status_code == 200
    body = resp.json()
    assert body["system_prompt_legal"] == DEFAULT_SYSTEM_PROMPT_LEGAL
    assert "rag_search" in body["system_prompt_legal"]
    assert body["system_prompt_text"]
