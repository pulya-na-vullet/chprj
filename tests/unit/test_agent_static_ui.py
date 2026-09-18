"""GET / serves the static test-UI HTML shell."""

from fastapi.testclient import TestClient

from neurolegal.agent.api.app import app


def test_root_serves_html_ui() -> None:
    with TestClient(app) as tc:
        resp = tc.get("/")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/html")
    assert '<div id="root"></div>' in resp.text or "<title>" in resp.text


def test_healthz_still_works_after_static_mount() -> None:
    with TestClient(app) as tc:
        resp = tc.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
