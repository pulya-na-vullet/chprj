"""Agent document proxy routes over a fake DocumentsClient (no hub, no DB rows).

Overrides get_documents_client + get_store via dependency_overrides.
"""

import io
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from neurolegal.agent.api.app import app
from neurolegal.agent.api.deps import get_documents_client, get_store
from neurolegal.agent.auth.deps import get_current_user
from neurolegal.agent.store.models import UserRow
from neurolegal.agent.tools.documents_client import DocumentsClientError, DocumentsNotFoundError
from neurolegal.contracts import HubDocumentContent, HubDocumentInfo, HubSection

USER_ID = "u1"
ALIEN_ID = "u2"
#: Документ, существующий в сервисе документов, но чужой для текущего пользователя.
ALIEN_DOC = "d-alien"


def _info(
    doc_id: str = "d1", status: str = "processing", owner_id: str = USER_ID
) -> HubDocumentInfo:
    return HubDocumentInfo(
        id=doc_id,
        owner_id=owner_id,
        filename="c.docx",
        content_type="application/octet-stream",
        size=10,
        status=status,
        parser="docx",
        page_count=None,
        error=None,
        created_at=datetime.now(UTC),
    )


class _FakeDocsClient:
    """Фейк клиента документов (T-0101, пункт 2).

    Раньше владелец сверялся `assert user_id == USER_ID` ВНУТРИ фейка —
    то есть мок проверял сам себя, и тесты про это ничего не знали. Подмена
    `user.id` на константу `"default"` в роутах при этом проходила: фейк
    отдавал данные независимо от того, кого ему передали.

    Теперь фейк только моделирует контракт сервиса документов (строка
    видна лишь владельцу) и ЗАПИСЫВАЕТ переданный user_id в `calls`; владельца
    сверяют ассерты самих тестов.
    """

    def __init__(self) -> None:
        self.attached: list[tuple[str, str]] = []
        self.deleted: list[str] = []
        #: (имя метода, значение user_id/owner_id, которое передал роут)
        self.calls: list[tuple[str, str]] = []

    def _record(self, method: str, user_id: str) -> None:
        self.calls.append((method, user_id))

    @staticmethod
    def _owner_of(document_id: str) -> str:
        return ALIEN_ID if document_id == ALIEN_DOC else USER_ID

    def _missing_for(self, document_id: str, user_id: str) -> bool:
        """Как в сервисе документов: чужая строка читается как несуществующая."""
        return document_id == "missing" or self._owner_of(document_id) != user_id

    async def upload(self, data, filename, content_type, *, owner_id):
        self._record("upload", owner_id)
        return _info()

    async def attach(self, document_id, conversation_id, user_id):
        self._record("attach", user_id)
        if self._missing_for(document_id, user_id):
            raise DocumentsNotFoundError(f"document not found: {document_id}")
        self.attached.append((document_id, conversation_id))
        return _info()

    async def get_info(self, document_id, user_id):
        self._record("get_info", user_id)
        if self._missing_for(document_id, user_id):
            raise DocumentsNotFoundError(f"document not found: {document_id}")
        return _info(document_id, "ready")

    async def list_for_conversation(self, conversation_id, user_id):
        self._record("list_for_conversation", user_id)
        return [_info("d1", "ready")] if user_id == USER_ID else []

    async def download_location(self, document_id, user_id):
        self._record("download_location", user_id)
        if self._missing_for(document_id, user_id):
            raise DocumentsNotFoundError(f"document not found: {document_id}")
        return "https://s3/presigned" if document_id == "live" else None

    async def list_for_owner(self, owner_id):
        self._record("list_for_owner", owner_id)
        if owner_id != USER_ID:
            return [_info("d-theirs", "ready", owner_id)]
        return [_info("d1", "ready"), _info("d2", "processing")]

    async def delete(self, document_id, user_id):
        self._record("delete", user_id)
        if self._missing_for(document_id, user_id):
            raise DocumentsNotFoundError(f"document not found: {document_id}")
        self.deleted.append(document_id)

    async def get_content(self, document_id, user_id):
        self._record("get_content", user_id)
        if self._missing_for(document_id, user_id):
            raise DocumentsNotFoundError(f"document not found: {document_id}")
        return HubDocumentContent(
            id=document_id,
            status="ready",
            full_text="Полный текст документа.",
            sections=[
                HubSection(
                    number="1", title="Предмет", text="Тело статьи.", level=1, start=0, end=1
                )
            ],
        )


class _FakeConvStore:
    async def create_conversation(self, user_id):
        return "conv-new"

    async def conversation_exists(self, session_id, user_id):
        return session_id == "conv-existing"

    async def commit(self):
        pass


def _fake_user() -> UserRow:
    return UserRow(
        id=USER_ID,
        email="u1@example.com",
        password_hash="h",
        is_active=True,
        email_verified_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
    )


@pytest_asyncio.fixture
async def client():
    docs = _FakeDocsClient()
    app.dependency_overrides[get_documents_client] = lambda: docs
    app.dependency_overrides[get_store] = lambda: _FakeConvStore()
    app.dependency_overrides[get_current_user] = _fake_user
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c, docs
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_upload_creates_conversation_attaches_and_wraps(client):
    c, docs = client
    files = {"file": ("c.docx", io.BytesIO(b"bytes"), "application/octet-stream")}
    resp = await c.post("/documents", files=files)
    assert resp.status_code == 200
    body = resp.json()
    assert body["session_id"] == "conv-new"
    assert body["document"]["status"] == "processing"
    assert docs.attached == [("d1", "conv-new")]
    assert docs.calls == [("upload", USER_ID), ("attach", USER_ID)]


@pytest.mark.asyncio
async def test_upload_unknown_session_is_404(client):
    c, _ = client
    files = {"file": ("c.docx", io.BytesIO(b"bytes"), "application/octet-stream")}
    resp = await c.post("/documents", files=files, data={"session_id": "nope"})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_bad_suffix_is_422(client):
    c, _ = client
    files = {"file": ("note.txt", io.BytesIO(b"x"), "text/plain")}
    resp = await c.post("/documents", files=files)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_conversation_documents_list(client):
    c, docs = client
    resp = await c.get("/conversations/conv-1/documents")
    assert resp.status_code == 200
    assert resp.json()["documents"][0]["id"] == "d1"
    # Скоуп по владельцу берётся из сессии, не из константы.
    assert docs.calls == [("list_for_conversation", USER_ID)]


@pytest.mark.asyncio
async def test_download_redirect_and_gone(client):
    c, _ = client
    live = await c.get("/documents/live/download")
    assert live.status_code == 307
    assert live.headers["location"] == "https://s3/presigned"
    gone = await c.get("/documents/gone/download")
    assert gone.status_code == 410


@pytest.mark.asyncio
async def test_get_document_unknown_id_is_404(client):
    c, _ = client
    resp = await c.get("/documents/missing")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_download_unknown_id_is_404(client):
    c, _ = client
    resp = await c.get("/documents/missing/download")
    assert resp.status_code == 404


class _OutageDocsClient:
    async def list_for_owner(self, owner_id):
        raise DocumentsClientError("hub down")

    async def upload(self, data, filename, content_type, *, owner_id):
        raise DocumentsClientError("hub down")

    async def delete(self, document_id, user_id):
        raise DocumentsClientError("hub down")

    async def get_content(self, document_id, user_id):
        raise DocumentsClientError("hub down")


@pytest_asyncio.fixture
async def outage_client():
    app.dependency_overrides[get_documents_client] = lambda: _OutageDocsClient()
    app.dependency_overrides[get_store] = lambda: _FakeConvStore()
    app.dependency_overrides[get_current_user] = _fake_user
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_library_list(client):
    c, docs = client
    resp = await c.get("/library/documents")
    assert resp.status_code == 200
    assert [d["id"] for d in resp.json()["documents"]] == ["d1", "d2"]
    assert docs.calls == [("list_for_owner", USER_ID)]


@pytest.mark.asyncio
async def test_library_list_hub_outage_is_502(outage_client):
    resp = await outage_client.get("/library/documents")
    assert resp.status_code == 502


@pytest.mark.asyncio
async def test_library_upload_returns_info_and_does_not_attach(client):
    c, docs = client
    files = {"file": ("c.docx", io.BytesIO(b"bytes"), "application/octet-stream")}
    resp = await c.post("/library/documents", files=files)
    assert resp.status_code == 200
    assert resp.json()["status"] == "processing"
    assert docs.attached == []  # library upload must NOT attach to a conversation
    assert docs.calls == [("upload", USER_ID)]


@pytest.mark.asyncio
async def test_library_upload_bad_suffix_is_422(client):
    c, _ = client
    files = {"file": ("note.txt", io.BytesIO(b"x"), "text/plain")}
    resp = await c.post("/library/documents", files=files)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_library_upload_hub_outage_is_502(outage_client):
    files = {"file": ("c.docx", io.BytesIO(b"bytes"), "application/octet-stream")}
    resp = await outage_client.post("/library/documents", files=files)
    assert resp.status_code == 502


@pytest.mark.asyncio
async def test_library_delete_returns_204(client):
    c, docs = client
    resp = await c.delete("/library/documents/d1")
    assert resp.status_code == 204
    assert docs.deleted == ["d1"]
    assert docs.calls == [("delete", USER_ID)]


@pytest.mark.asyncio
async def test_library_delete_missing_is_404(client):
    c, _ = client
    resp = await c.delete("/library/documents/missing")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_library_delete_hub_outage_is_502(outage_client):
    resp = await outage_client.delete("/library/documents/d1")
    assert resp.status_code == 502


@pytest.mark.asyncio
async def test_library_attach_creates_conversation_scoped_to_owner(client):
    """Merge guard (design phase2 + auth): attach must run as the session
    user — каждый вызов уносит id текущего пользователя, и новая беседа
    принадлежит ему."""
    c, docs = client
    resp = await c.post("/library/documents/d1/attach", json={"session_id": None})
    assert resp.status_code == 200
    body = resp.json()
    assert body["session_id"] == "conv-new"
    assert docs.attached == [("d1", "conv-new")]
    assert docs.calls == [("get_info", USER_ID), ("attach", USER_ID)]


@pytest.mark.asyncio
async def test_library_attach_to_existing_conversation(client):
    c, docs = client
    resp = await c.post("/library/documents/d1/attach", json={"session_id": "conv-existing"})
    assert resp.status_code == 200
    assert resp.json()["session_id"] == "conv-existing"
    assert docs.attached == [("d1", "conv-existing")]


@pytest.mark.asyncio
async def test_library_attach_unknown_conversation_is_404(client):
    c, _ = client
    resp = await c.post("/library/documents/d1/attach", json={"session_id": "conv-alien"})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_library_attach_missing_document_is_404(client):
    c, _ = client
    resp = await c.post("/library/documents/missing/attach", json={"session_id": None})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_document_content_ready(client):
    c, docs = client
    resp = await c.get("/documents/d1/content")
    assert resp.status_code == 200
    body = resp.json()
    assert body["full_text"] == "Полный текст документа."
    assert body["sections"][0]["number"] == "1"
    assert docs.calls == [("get_content", USER_ID)]


@pytest.mark.asyncio
async def test_document_content_missing_is_404(client):
    c, _ = client
    resp = await c.get("/documents/missing/content")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_document_content_hub_outage_is_502(outage_client):
    resp = await outage_client.get("/documents/d1/content")
    assert resp.status_code == 502


# -- cross-tenant: чужой документ читается как несуществующий (T-0101, п.2) --


@pytest.mark.asyncio
async def test_alien_document_info_is_404(client):
    c, docs = client
    resp = await c.get(f"/documents/{ALIEN_DOC}")
    assert resp.status_code == 404
    assert docs.calls == [("get_info", USER_ID)]


@pytest.mark.asyncio
async def test_alien_document_content_is_404(client):
    """Текст чужого договора — самая дорогая утечка из трёх: `/content`
    отдаёт полное тело документа, не только карточку."""
    c, docs = client
    resp = await c.get(f"/documents/{ALIEN_DOC}/content")
    assert resp.status_code == 404
    assert docs.calls == [("get_content", USER_ID)]


@pytest.mark.asyncio
async def test_alien_document_download_is_404(client):
    c, _ = client
    assert (await c.get(f"/documents/{ALIEN_DOC}/download")).status_code == 404


@pytest.mark.asyncio
async def test_alien_document_delete_is_404(client):
    c, docs = client
    resp = await c.delete(f"/library/documents/{ALIEN_DOC}")
    assert resp.status_code == 404
    assert docs.deleted == []


@pytest.mark.asyncio
async def test_alien_document_attach_is_404(client):
    c, docs = client
    resp = await c.post(f"/library/documents/{ALIEN_DOC}/attach", json={"session_id": None})
    assert resp.status_code == 404
    assert docs.attached == []
