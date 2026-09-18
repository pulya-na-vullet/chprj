"""RAG admin proxy ↔ templates service, два реальных ASGI-приложения.

httpx.AsyncClient внутри rag/templates_client.py подменяется на клиент, чей
ASGITransport ведёт в настоящий templates-app (SQLite + in-memory blob) —
сетевого слоя нет, весь путь «вкладка → прокси → сервис → скан полей»
настоящий.
"""

from collections.abc import AsyncIterator
from io import BytesIO
from typing import Any

import httpx
import pytest
from docx import Document
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from neurolegal.rag.api.app import app as rag_app
from neurolegal.rag.api.deps import get_templates_client
from neurolegal.rag.templates_client import TemplatesClient
from neurolegal.templates.api.app import app as templates_app
from neurolegal.templates.api.deps import get_blob_store, get_store
from neurolegal.templates.store.blob import InMemoryTemplatesBlobStore
from neurolegal.templates.store.models import Base
from neurolegal.templates.store.template_store import TemplateStore

pytestmark = pytest.mark.api_with_mocks


def _docx(*names: str) -> bytes:
    doc = Document()
    for name in names:
        doc.add_paragraph(f"{{{{ {name} }}}}")
    out = BytesIO()
    doc.save(out)
    return out.getvalue()


@pytest.fixture
async def client(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[AsyncClient]:
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    blob = InMemoryTemplatesBlobStore()

    async def _store() -> AsyncIterator[TemplateStore]:
        async with maker() as session:
            yield TemplateStore(session)

    templates_app.dependency_overrides[get_store] = _store
    templates_app.dependency_overrides[get_blob_store] = lambda: blob

    real_async_client = httpx.AsyncClient

    def _asgi_client(**kwargs: Any) -> httpx.AsyncClient:
        kwargs.pop("transport", None)
        return real_async_client(
            transport=ASGITransport(app=templates_app), base_url="http://templates", **kwargs
        )

    # templates_client создаёт httpx.AsyncClient сам — заворачиваем клиент в ASGI
    monkeypatch.setattr("neurolegal.rag.templates_client.httpx.AsyncClient", _asgi_client)
    rag_app.dependency_overrides[get_templates_client] = lambda: TemplatesClient(
        base_url="http://templates"
    )

    async with real_async_client(transport=ASGITransport(app=rag_app), base_url="http://test") as c:
        yield c
    rag_app.dependency_overrides.clear()
    templates_app.dependency_overrides.clear()
    await engine.dispose()


async def test_upload_via_proxy_creates_template_with_scanned_fields(
    client: AsyncClient,
) -> None:
    response = await client.post(
        "/admin/templates",
        data={
            "slug": "arenda",
            "title": "Аренда",
            "category": "Договоры",
            "description": "Тест",
        },
        files={"file": ("arenda.docx", _docx("landlord_fio", "rent"))},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "draft"
    assert [f["name"] for f in body["fields"]] == ["landlord_fio", "rent"]

    listed = await client.get("/admin/templates")
    assert [t["slug"] for t in listed.json()["templates"]] == ["arenda"]


async def test_full_operator_cycle_via_proxy(client: AsyncClient) -> None:
    await client.post(
        "/admin/templates",
        data={"slug": "arenda", "title": "Аренда", "category": "Договоры", "description": ""},
        files={"file": ("arenda.docx", _docx("a", "b"))},
    )
    # publish
    patched = await client.patch("/admin/templates/arenda", json={"status": "published"})
    assert patched.status_code == 200 and patched.json()["status"] == "published"
    # замена файла возвращает дифф полей
    replaced = await client.put(
        "/admin/templates/arenda/file", files={"file": ("v2.docx", _docx("a", "c"))}
    )
    assert replaced.status_code == 200
    assert replaced.json()["added"] == ["c"]
    assert replaced.json()["orphaned"] == ["b"]
    # скачивание исходника
    downloaded = await client.get("/admin/templates/arenda/file")
    assert downloaded.status_code == 200 and downloaded.content[:2] == b"PK"
    # удаление
    deleted = await client.delete("/admin/templates/arenda")
    assert deleted.status_code == 204
    assert (await client.get("/admin/templates")).json()["templates"] == []


async def test_proxy_caps_upload_size_before_forwarding(client: AsyncClient) -> None:
    """Кап срабатывает на самом прокси — до пересылки в templates-сервис."""
    oversized = b"x" * (10 * 1024 * 1024 + 1)
    response = await client.post(
        "/admin/templates",
        data={"slug": "big", "title": "T", "category": "C", "description": ""},
        files={"file": ("big.docx", oversized)},
    )
    assert response.status_code == 422
    assert "10 МБ" in response.json()["detail"]


async def test_proxy_maps_conflict_and_missing(client: AsyncClient) -> None:
    form = {"slug": "dup", "title": "T", "category": "C", "description": ""}
    files = {"file": ("t.docx", _docx("x"))}
    assert (await client.post("/admin/templates", data=form, files=files)).status_code == 201
    dup = await client.post("/admin/templates", data=form, files=files)
    assert dup.status_code == 409
    missing = await client.patch("/admin/templates/missing", json={"title": "X"})
    assert missing.status_code == 404
    bad = await client.post(
        "/admin/templates",
        data=form | {"slug": "bad slug"},
        files={"file": ("t.docx", _docx("x"))},
    )
    assert bad.status_code == 422
