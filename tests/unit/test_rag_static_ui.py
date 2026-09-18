"""GET / on the RAG app serves the admin SPA shell; API routes win over static."""

from fastapi.testclient import TestClient

from neurolegal.rag.api.app import app


def test_root_serves_admin_html() -> None:
    with TestClient(app) as tc:
        resp = tc.get("/")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/html")
    assert "admin.js" in resp.text


def test_api_routes_matched_before_static() -> None:
    with TestClient(app) as tc:
        resp = tc.get("/search", params={"q": ""})
    assert resp.status_code == 422  # validation error from the /search route, not static
