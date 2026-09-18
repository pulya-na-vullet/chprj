"""Admin documents routes: list / manifest edit / delete / upload / inspection."""

from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

import neurolegal.rag.api.routes_admin_documents as routes
from neurolegal.rag.acquisition.corpus_store import DOCX_CONTENT_TYPE, InMemoryCorpusStore
from neurolegal.rag.acquisition.manifest import ManifestEntry, load_manifest, save_manifest
from neurolegal.rag.api.deps import db_session, get_corpus_store, get_manifest_path
from neurolegal.rag.jobs import JobManager
from neurolegal.rag.pipelines.ingest import IngestResult
from neurolegal.rag.store.admin import ActDbStats, ArticleDetailEntry, ArticleListEntry, ChunkEntry

pytestmark = pytest.mark.api_with_mocks

MANIFEST_YAML = """\
- code_id: ГК-1
  kind: codex
  short_name: ГК РФ
  full_name: Гражданский кодекс (часть первая)
  docx_path: {docx}
"""


async def _noop_runner(code_id: str, on_progress: Any) -> IngestResult:
    return IngestResult(act_id="a", articles_count=0, chunks_count=0)


@pytest.fixture
def manifest_path(tmp_path: Path) -> Path:
    docx = tmp_path / "gk1.docx"
    docx.write_bytes(b"fake docx")
    path = tmp_path / "manifest.yaml"
    path.write_text(MANIFEST_YAML.format(docx=docx), "utf-8")
    return path


@pytest.fixture
def corpus_store() -> InMemoryCorpusStore:
    return InMemoryCorpusStore()


@pytest.fixture
def app(manifest_path: Path, corpus_store: InMemoryCorpusStore) -> FastAPI:
    test_app = FastAPI()
    test_app.include_router(routes.router)
    test_app.state.job_manager = JobManager(_noop_runner)

    async def fake_db() -> AsyncGenerator[Any, None]:
        yield AsyncMock()

    test_app.dependency_overrides[db_session] = fake_db
    test_app.dependency_overrides[get_manifest_path] = lambda: manifest_path
    test_app.dependency_overrides[get_corpus_store] = lambda: corpus_store
    return test_app


def _client(app: FastAPI) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.fixture
async def client(app: FastAPI) -> AsyncGenerator[AsyncClient, None]:
    async with _client(app) as c:
        yield c


_STATS = ActDbStats(
    act_id="a1",
    source_doc_id="gk-1",
    short_name="ГК РФ",
    full_name="Гражданский кодекс (часть первая)",
    kind="codex",
    ingested_at=datetime(2099, 1, 1, tzinfo=UTC),
    articles_count=3,
    chunks_count=12,
)


@pytest.mark.asyncio
async def test_documents_merges_manifest_and_db(
    app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(routes, "act_stats", AsyncMock(return_value=[_STATS]))
    monkeypatch.setattr(routes, "count_chunks", AsyncMock(return_value=12))
    monkeypatch.setattr(routes, "db_size_bytes", AsyncMock(return_value=12_582_912))
    async with _client(app) as client:
        resp = await client.get("/admin/documents")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_chunks"] == 12
    assert body["db_size_bytes"] == 12_582_912
    [doc] = body["documents"]
    assert doc["code_id"] == "ГК-1"
    assert doc["status"] == "ingested"
    assert doc["chunks_count"] == 12
    assert doc["file_exists"] is True


@pytest.mark.asyncio
async def test_update_manifest_rewrites_file(app: FastAPI, manifest_path: Path) -> None:
    payload = {
        "short_name": "ГК РФ (нов.)",
        "full_name": "Гражданский кодекс",
        "kind": "codex",
        "docx_path": str(manifest_path.parent / "gk1.docx"),
    }
    async with _client(app) as client:
        resp = await client.put("/admin/documents/ГК-1/manifest", json=payload)
        missing = await client.put("/admin/documents/НЕТ/manifest", json=payload)
    assert resp.status_code == 200
    assert missing.status_code == 404
    assert "ГК РФ (нов.)" in manifest_path.read_text("utf-8")


@pytest.mark.asyncio
async def test_delete_document_db_and_manifest(
    app: FastAPI, manifest_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    delete_mock = AsyncMock(return_value=True)
    monkeypatch.setattr(routes, "delete_act", delete_mock)
    async with _client(app) as client:
        resp = await client.request(
            "DELETE",
            "/admin/documents/ГК-1",
            json={"drop_manifest": True, "drop_file": False},
        )
    assert resp.status_code == 200
    delete_mock.assert_awaited_once()
    assert delete_mock.await_args.args[1] == "gk-1"
    assert "ГК-1" not in manifest_path.read_text("utf-8")


@pytest.mark.asyncio
async def test_upload_document_appends_manifest_and_saves_file(
    app: FastAPI, manifest_path: Path, corpus_store: InMemoryCorpusStore
) -> None:
    async with _client(app) as client:
        resp = await client.post(
            "/admin/documents",
            files={"file": ("uk.docx", b"PK fake docx", "application/octet-stream")},
            data={
                "code_id": "УК",
                "short_name": "УК РФ",
                "full_name": "Уголовный кодекс",
                "kind": "codex",
            },
        )
    assert resp.status_code == 201
    assert resp.json() == {"code_id": "УК", "job_id": None}
    assert corpus_store.objects["corpus/uk.docx"] == b"PK fake docx"
    entry = load_manifest(manifest_path).entries["УК"]
    assert entry.docx_s3_key == "corpus/uk.docx"
    assert entry.docx_path is None


@pytest.mark.asyncio
async def test_upload_rejects_bad_extension_and_duplicate(app: FastAPI) -> None:
    data = {
        "code_id": "ГК-1",  # дубль
        "short_name": "x",
        "full_name": "y",
        "kind": "codex",
    }
    async with _client(app) as client:
        dup = await client.post(
            "/admin/documents",
            files={"file": ("a.docx", b"x", "application/octet-stream")},
            data=data,
        )
        bad = await client.post(
            "/admin/documents",
            files={"file": ("a.pdf", b"x", "application/pdf")},
            data={**data, "code_id": "НОВЫЙ"},
        )
    assert dup.status_code == 422
    assert bad.status_code == 422


@pytest.mark.asyncio
async def test_articles_and_article_detail(app: FastAPI, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        routes,
        "list_articles",
        AsyncMock(
            return_value=[
                ArticleListEntry(
                    article_id="11111111-1111-1111-1111-111111111111",
                    number="1",
                    title="Т",
                    chunks_count=2,
                )
            ]
        ),
    )
    detail = ArticleDetailEntry(
        article_id="11111111-1111-1111-1111-111111111111",
        act_short_name="ГК РФ",
        number="1",
        title="Т",
        full_text="текст",
        chunks=[
            ChunkEntry(
                chunk_id="22222222-2222-2222-2222-222222222222",
                path="ст. 1",
                text="чанк",
                ordinal=1,
            )
        ],
    )
    monkeypatch.setattr(routes, "article_detail", AsyncMock(return_value=detail))
    async with _client(app) as client:
        listing = await client.get("/admin/documents/ГК-1/articles")
        one = await client.get("/admin/articles/11111111-1111-1111-1111-111111111111")
    assert listing.status_code == 200
    assert listing.json()["articles"][0]["number"] == "1"
    assert one.status_code == 200
    assert one.json()["chunks"][0]["path"] == "ст. 1"


@pytest.mark.asyncio
async def test_article_detail_404(app: FastAPI, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(routes, "article_detail", AsyncMock(return_value=None))
    async with _client(app) as client:
        resp = await client.get("/admin/articles/33333333-3333-3333-3333-333333333333")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_manifest_rejects_path_traversal(app: FastAPI, manifest_path: Path) -> None:
    """Absolute paths outside the docs dir and ../-escaping must be rejected."""
    original_text = manifest_path.read_text("utf-8")
    base = {
        "short_name": "ГК РФ",
        "full_name": "Гражданский кодекс",
        "kind": "codex",
    }
    async with _client(app) as client:
        # Absolute path outside the manifest directory
        resp_abs = await client.put(
            "/admin/documents/ГК-1/manifest",
            json={**base, "docx_path": "/tmp/evil.docx"},
        )
        # Relative path that escapes the directory
        resp_rel = await client.put(
            "/admin/documents/ГК-1/manifest",
            json={**base, "docx_path": "../../escape.docx"},
        )
    assert resp_abs.status_code == 422
    assert resp_rel.status_code == 422
    # Manifest must remain untouched on both failures
    assert manifest_path.read_text("utf-8") == original_text


@pytest.mark.asyncio
async def test_upload_rejects_filename_collision(
    app: FastAPI, corpus_store: InMemoryCorpusStore
) -> None:
    """Uploading a code_id that slugs to an already-existing S3 key must be rejected."""
    original_bytes = b"original corpus file"
    await corpus_store.put("corpus/uk.docx", original_bytes)

    async with _client(app) as client:
        # code_id "UK" (Cyrillic) slugifies to "uk", colliding with the existing object
        resp = await client.post(
            "/admin/documents",
            files={"file": ("uk.docx", b"new upload", "application/octet-stream")},
            data={
                "code_id": "УК",
                "short_name": "УК РФ",
                "full_name": "Уголовный кодекс",
                "kind": "codex",
            },
        )
    assert resp.status_code == 422
    # Original object must not be overwritten
    assert corpus_store.objects["corpus/uk.docx"] == original_bytes


@pytest.mark.asyncio
async def test_upload_puts_file_into_s3_and_writes_key(
    client: AsyncClient, corpus_store: InMemoryCorpusStore, manifest_path: Path
) -> None:
    response = await client.post(
        "/admin/documents",
        files={"file": ("gk.docx", b"PK\x03\x04", DOCX_CONTENT_TYPE)},
        data={
            "code_id": "ГК РФ",
            "short_name": "ГК РФ",
            "full_name": "Гражданский кодекс",
            "kind": "codex",
        },
    )
    assert response.status_code == 201
    # Ключ равен source_doc_id акта (T-0115): slugify_code_id молча выбрасывает
    # пробел, поэтому «ГК РФ» превращается в "gkrf", не в "gk-rf".
    assert corpus_store.objects["corpus/gkrf.docx"] == b"PK\x03\x04"
    entry = load_manifest(manifest_path).entries["ГК РФ"]
    assert entry.docx_s3_key == "corpus/gkrf.docx"
    assert entry.docx_path is None


@pytest.mark.asyncio
async def test_upload_rejects_existing_key(
    client: AsyncClient, corpus_store: InMemoryCorpusStore
) -> None:
    await corpus_store.put("corpus/gkrf.docx", b"old")
    response = await client.post(
        "/admin/documents",
        files={"file": ("gk.docx", b"new", DOCX_CONTENT_TYPE)},
        data={
            "code_id": "ГК РФ",
            "short_name": "ГК РФ",
            "full_name": "Гражданский кодекс",
            "kind": "codex",
        },
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_delete_with_drop_file_removes_s3_object(
    client: AsyncClient,
    corpus_store: InMemoryCorpusStore,
    manifest_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(routes, "delete_act", AsyncMock(return_value=True))
    await corpus_store.put("corpus/gk-rf.docx", b"payload")
    manifest = load_manifest(manifest_path)
    manifest.entries["ГК РФ"] = ManifestEntry(
        code_id="ГК РФ",
        kind="codex",
        short_name="ГК РФ",
        full_name="Гражданский кодекс",
        docx_s3_key="corpus/gk-rf.docx",
    )
    save_manifest(manifest, manifest_path)
    response = await client.request(
        "DELETE", "/admin/documents/ГК РФ", json={"drop_file": True, "drop_manifest": True}
    )
    assert response.status_code == 200
    assert "corpus/gk-rf.docx" not in corpus_store.objects


@pytest.mark.asyncio
async def test_manifest_update_accepts_s3_prefix(client: AsyncClient, manifest_path: Path) -> None:
    response = await client.put(
        "/admin/documents/ГК-1/manifest",
        json={
            "short_name": "ГК РФ",
            "full_name": "Гражданский кодекс",
            "kind": "codex",
            "docx_path": "s3:corpus/gk-rf.docx",
        },
    )
    assert response.status_code == 200
    entry = load_manifest(manifest_path).entries["ГК-1"]
    assert entry.docx_s3_key == "corpus/gk-rf.docx"
    assert entry.docx_path is None


def _s3_manifest(manifest_path: Path, key: str = "corpus/gk-rf.docx") -> None:
    manifest = load_manifest(manifest_path)
    manifest.entries["ГК-1"] = ManifestEntry(
        code_id="ГК-1",
        kind="codex",
        short_name="ГК РФ",
        full_name="Гражданский кодекс",
        docx_s3_key=key,
    )
    save_manifest(manifest, manifest_path)


@pytest.mark.asyncio
async def test_documents_file_path_roundtrips_back_to_s3(
    client: AsyncClient,
    manifest_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The admin form prefills from file_path and posts it back as docx_path.

    Without the `s3:` marker the entry silently migrates to a non-existent
    local path when the operator edits only short_name.
    """
    monkeypatch.setattr(routes, "act_stats", AsyncMock(return_value=[]))
    monkeypatch.setattr(routes, "count_chunks", AsyncMock(return_value=0))
    monkeypatch.setattr(routes, "db_size_bytes", AsyncMock(return_value=0))
    _s3_manifest(manifest_path)

    listing = await client.get("/admin/documents")
    [doc] = listing.json()["documents"]
    assert doc["file_path"] == "s3:corpus/gk-rf.docx"

    resp = await client.put(
        "/admin/documents/ГК-1/manifest",
        json={
            "short_name": "ГК РФ (нов.)",
            "full_name": "Гражданский кодекс",
            "kind": "codex",
            "docx_path": doc["file_path"],
        },
    )
    assert resp.status_code == 200
    entry = load_manifest(manifest_path).entries["ГК-1"]
    assert entry.docx_s3_key == "corpus/gk-rf.docx"
    assert entry.docx_path is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "key",
    [
        "owner/u1/d1/original.pdf",  # another user's file in the shared bucket
        "owner/u1/d1/original.docx",  # right suffix, outside the corpus prefix
        "corpus/../owner/u1/d1/original.docx",
        "/corpus/gk-rf.docx",
        "corpus/gk-rf.pdf",
    ],
)
async def test_manifest_update_rejects_key_outside_corpus_prefix(
    client: AsyncClient, manifest_path: Path, key: str
) -> None:
    """A crafted S3 key would be deleted verbatim by DELETE ?drop_file=true."""
    original_text = manifest_path.read_text("utf-8")
    resp = await client.put(
        "/admin/documents/ГК-1/manifest",
        json={
            "short_name": "ГК РФ",
            "full_name": "Гражданский кодекс",
            "kind": "codex",
            "docx_path": f"s3:{key}",
        },
    )
    assert resp.status_code == 422
    assert manifest_path.read_text("utf-8") == original_text


@pytest.mark.asyncio
async def test_documents_survives_s3_listing_failure(
    app: FastAPI, manifest_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """DB half of the matrix is still valid — an S3 outage must not 500."""
    monkeypatch.setattr(routes, "act_stats", AsyncMock(return_value=[]))
    monkeypatch.setattr(routes, "count_chunks", AsyncMock(return_value=0))
    monkeypatch.setattr(routes, "db_size_bytes", AsyncMock(return_value=0))
    _s3_manifest(manifest_path)

    broken = InMemoryCorpusStore()
    monkeypatch.setattr(
        broken, "list_prefix", AsyncMock(side_effect=RuntimeError("s3 is down")), raising=False
    )
    app.dependency_overrides[get_corpus_store] = lambda: broken

    async with _client(app) as client:
        resp = await client.get("/admin/documents")
    assert resp.status_code == 200
    [doc] = resp.json()["documents"]
    assert doc["file_exists"] is False
    assert doc["file_path"] == "s3:corpus/gk-rf.docx"


@pytest.mark.asyncio
async def test_documents_lists_prefix_once_not_per_entry(
    client: AsyncClient,
    corpus_store: InMemoryCorpusStore,
    manifest_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(routes, "act_stats", AsyncMock(return_value=[]))
    monkeypatch.setattr(routes, "count_chunks", AsyncMock(return_value=0))
    monkeypatch.setattr(routes, "db_size_bytes", AsyncMock(return_value=0))
    _s3_manifest(manifest_path)
    await corpus_store.put("corpus/gk-rf.docx", b"PK\x03\x04")
    head = AsyncMock(side_effect=AssertionError("head must not be used for the listing"))
    monkeypatch.setattr(corpus_store, "head", head, raising=False)

    resp = await client.get("/admin/documents")
    assert resp.status_code == 200
    [doc] = resp.json()["documents"]
    assert doc["file_exists"] is True
    assert doc["file_size"] == 4


@pytest.mark.asyncio
async def test_documents_without_s3_credentials_degrades(
    app: FastAPI, manifest_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(routes, "act_stats", AsyncMock(return_value=[]))
    monkeypatch.setattr(routes, "count_chunks", AsyncMock(return_value=0))
    monkeypatch.setattr(routes, "db_size_bytes", AsyncMock(return_value=0))
    _s3_manifest(manifest_path)
    app.dependency_overrides[get_corpus_store] = lambda: None

    async with _client(app) as client:
        resp = await client.get("/admin/documents")
    assert resp.status_code == 200
    [doc] = resp.json()["documents"]
    assert doc["file_exists"] is False


@pytest.mark.asyncio
async def test_upload_without_s3_credentials_returns_503(app: FastAPI) -> None:
    app.dependency_overrides[get_corpus_store] = lambda: None
    async with _client(app) as client:
        resp = await client.post(
            "/admin/documents",
            files={"file": ("uk.docx", b"x", DOCX_CONTENT_TYPE)},
            data={
                "code_id": "УК",
                "short_name": "УК РФ",
                "full_name": "Уголовный кодекс",
                "kind": "codex",
            },
        )
    assert resp.status_code == 503
    assert "S3" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_delete_with_drop_file_without_s3_returns_503(
    app: FastAPI, manifest_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """503 before delete_act — no half-done delete (rows gone, object kept)."""
    delete_mock = AsyncMock(return_value=True)
    monkeypatch.setattr(routes, "delete_act", delete_mock)
    _s3_manifest(manifest_path)
    app.dependency_overrides[get_corpus_store] = lambda: None

    async with _client(app) as client:
        resp = await client.request(
            "DELETE", "/admin/documents/ГК-1", json={"drop_file": True, "drop_manifest": True}
        )
    assert resp.status_code == 503
    delete_mock.assert_not_awaited()
    assert "ГК-1" in manifest_path.read_text("utf-8")
