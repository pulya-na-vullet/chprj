"""Origin allowlist middleware (CSRF defense-in-depth) on the agent app.

Default `NEUROLEGAL_PUBLIC_BASE_URL` in tests is http://127.0.0.1:8000 (see
core/config.py), so the allowlist is {that origin, localhost:5173,
127.0.0.1:5173} per the design doc's local-dev carve-out.
"""

from fastapi.testclient import TestClient

from neurolegal.agent.api.app import app


def test_mutating_request_with_disallowed_origin_is_rejected() -> None:
    client = TestClient(app)
    resp = client.post("/auth/logout", headers={"origin": "https://evil.example"})
    assert resp.status_code == 403
    assert resp.json()["detail"] == "invalid_origin"


def test_origin_that_merely_starts_with_ours_is_rejected() -> None:
    """Сверка Origin обязана быть точной, не префиксной (T-0101, пункт 7).

    `http://127.0.0.1:8000.evil.com` — валидный чужой домен, чей Origin
    длиннее нашего ровно на суффикс. Ослабление `not in` до `startswith`
    открывает CSRF именно через такой домен.
    """
    client = TestClient(app)
    resp = client.post("/auth/logout", headers={"origin": "http://127.0.0.1:8000.evil.com"})
    assert resp.status_code == 403
    assert resp.json()["detail"] == "invalid_origin"


def test_mutating_request_with_allowed_origin_passes_through() -> None:
    client = TestClient(app)
    resp = client.post("/auth/logout", headers={"origin": "http://127.0.0.1:8000"})
    assert resp.status_code == 204


def test_mutating_request_with_allowed_vite_dev_origin_passes_through() -> None:
    client = TestClient(app)
    resp = client.post("/auth/logout", headers={"origin": "http://localhost:5173"})
    assert resp.status_code == 204


def test_mutating_request_without_origin_header_passes_through() -> None:
    client = TestClient(app)
    resp = client.post("/auth/logout")
    assert resp.status_code == 204


def test_get_request_with_disallowed_origin_is_not_blocked() -> None:
    client = TestClient(app)
    resp = client.get("/healthz", headers={"origin": "https://evil.example"})
    assert resp.status_code == 200
