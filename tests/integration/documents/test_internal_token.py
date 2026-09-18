"""Hub-side X-Internal-Token enforcement + the X-User-Id-is-required contract
(T-0021, design doc 2026-07-11-auth-design §1.6)."""

import io

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from neurolegal.core.config import settings as core_settings
from neurolegal.documents.api import deps
from neurolegal.documents.api.app import app
from neurolegal.documents.store.blob import InMemoryBlobStore
from neurolegal.documents.store.models import Base

pytestmark = pytest.mark.api_with_mocks


@pytest.fixture
async def client():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    blob = InMemoryBlobStore()

    async def _db_session():
        async with maker() as s:
            yield s

    app.dependency_overrides[deps.db_session] = _db_session
    app.dependency_overrides[deps.get_blob_store] = lambda: blob
    app.dependency_overrides[deps.get_session_factory] = lambda: maker
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()
    await engine.dispose()


def _files():
    return {"file": ("c.docx", io.BytesIO(b"not-really-docx-but-unused"), "text/plain")}


async def test_no_internal_token_configured_request_passes(client):
    # internal_token is unset by default — the check is a no-op.
    resp = await client.get("/documents", headers={"X-User-Id": "u1"})
    assert resp.status_code == 200


async def test_missing_x_user_id_is_422(client):
    resp = await client.get("/documents")
    assert resp.status_code == 422


async def test_missing_x_user_id_on_upload_is_422(client):
    resp = await client.post("/documents", files=_files())
    assert resp.status_code == 422


async def test_internal_token_configured_rejects_missing_header(client, monkeypatch):
    monkeypatch.setattr(core_settings, "internal_token", "shared-secret")
    resp = await client.get("/documents", headers={"X-User-Id": "u1"})
    assert resp.status_code == 401


async def test_internal_token_configured_rejects_wrong_value(client, monkeypatch):
    monkeypatch.setattr(core_settings, "internal_token", "shared-secret")
    resp = await client.get("/documents", headers={"X-User-Id": "u1", "X-Internal-Token": "wrong"})
    assert resp.status_code == 401


async def test_internal_token_configured_accepts_matching_header(client, monkeypatch):
    monkeypatch.setattr(core_settings, "internal_token", "shared-secret")
    resp = await client.get(
        "/documents", headers={"X-User-Id": "u1", "X-Internal-Token": "shared-secret"}
    )
    assert resp.status_code == 200


async def test_internal_token_check_applies_to_download_route_too(client, monkeypatch):
    """Not just upload/list — every route under documents_router is gated."""
    monkeypatch.setattr(core_settings, "internal_token", "shared-secret")
    resp = await client.get("/documents/whatever/download", follow_redirects=False)
    assert resp.status_code == 401


async def test_healthz_is_never_gated_by_internal_token(client, monkeypatch):
    monkeypatch.setattr(core_settings, "internal_token", "shared-secret")
    resp = await client.get("/healthz")
    assert resp.status_code == 200
