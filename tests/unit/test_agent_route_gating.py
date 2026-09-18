"""Every user-facing agent route requires `get_current_user` (T-0021).

No dependency_overrides here on purpose: `get_current_user` fails on the
missing-cookie check before any of its own sub-dependencies (DB session,
mail sender) perform I/O, so hitting the real app without a session cookie
is safe and DB-free — exactly what's being asserted.
"""

import io

import pytest
from fastapi.testclient import TestClient

from neurolegal.agent.api.app import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_chat_requires_auth(client: TestClient) -> None:
    resp = client.post("/chat", json={"session_id": None, "message": "вопрос"})
    assert resp.status_code == 401


def test_list_conversations_requires_auth(client: TestClient) -> None:
    assert client.get("/conversations").status_code == 401


def test_get_messages_requires_auth(client: TestClient) -> None:
    assert client.get("/conversations/c1/messages").status_code == 401


def test_delete_conversation_requires_auth(client: TestClient) -> None:
    assert client.delete("/conversations/c1").status_code == 401


def test_library_list_requires_auth(client: TestClient) -> None:
    assert client.get("/library/documents").status_code == 401


def test_library_upload_requires_auth(client: TestClient) -> None:
    files = {"file": ("c.docx", io.BytesIO(b"x"), "application/octet-stream")}
    assert client.post("/library/documents", files=files).status_code == 401


def test_library_delete_requires_auth(client: TestClient) -> None:
    assert client.delete("/library/documents/d1").status_code == 401


def test_library_attach_requires_auth(client: TestClient) -> None:
    resp = client.post("/library/documents/d1/attach", json={"session_id": None})
    assert resp.status_code == 401


def test_upload_document_requires_auth(client: TestClient) -> None:
    files = {"file": ("c.docx", io.BytesIO(b"x"), "application/octet-stream")}
    assert client.post("/documents", files=files).status_code == 401


def test_get_document_requires_auth(client: TestClient) -> None:
    assert client.get("/documents/d1").status_code == 401


def test_get_document_content_requires_auth(client: TestClient) -> None:
    assert client.get("/documents/d1/content").status_code == 401


def test_download_document_requires_auth(client: TestClient) -> None:
    assert client.get("/documents/d1/download").status_code == 401


def test_conversation_documents_requires_auth(client: TestClient) -> None:
    assert client.get("/conversations/c1/documents").status_code == 401


def test_acts_requires_auth(client: TestClient) -> None:
    assert client.get("/acts").status_code == 401


def test_sources_requires_auth(client: TestClient) -> None:
    assert client.get("/sources").status_code == 401


def test_source_articles_requires_auth(client: TestClient) -> None:
    assert client.get("/sources/gk-1/articles").status_code == 401


def test_article_requires_auth(client: TestClient) -> None:
    assert client.get("/sources/articles/abc").status_code == 401


# -- open routes: no auth required -----------------------------------------


def test_healthz_open(client: TestClient) -> None:
    assert client.get("/healthz").status_code == 200


def test_auth_me_open_but_unauthenticated(client: TestClient) -> None:
    # /auth/* itself must stay reachable without a cookie (it's how you get one).
    assert client.get("/auth/me").status_code == 401


def test_root_static_open(client: TestClient) -> None:
    assert client.get("/").status_code == 200
