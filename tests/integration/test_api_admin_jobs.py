"""Admin job routes: start/poll/cancel/indexes + wiring into the RAG app."""

import asyncio
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

import neurolegal.rag.api.routes_admin_jobs as routes
from neurolegal.rag.api.deps import db_session, get_manifest_path
from neurolegal.rag.jobs import JobManager
from neurolegal.rag.pipelines.ingest import IngestResult

pytestmark = pytest.mark.api_with_mocks

MANIFEST_YAML = """\
- code_id: ГК-1
  kind: codex
  short_name: ГК РФ
  full_name: Гражданский кодекс (часть первая)
  docx_path: {docx}
"""


@pytest.fixture
def manifest_path(tmp_path: Path) -> Path:
    docx = tmp_path / "gk1.docx"
    docx.write_bytes(b"fake docx")
    path = tmp_path / "manifest.yaml"
    path.write_text(MANIFEST_YAML.format(docx=docx), "utf-8")
    return path


def _app(manifest_path: Path, manager: JobManager) -> FastAPI:
    test_app = FastAPI()
    test_app.include_router(routes.router)
    test_app.state.job_manager = manager

    async def fake_db() -> AsyncGenerator[Any, None]:
        yield AsyncMock()

    test_app.dependency_overrides[db_session] = fake_db
    test_app.dependency_overrides[get_manifest_path] = lambda: manifest_path
    return test_app


def _client(app: FastAPI) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.mark.asyncio
async def test_ingest_lifecycle_and_polling(manifest_path: Path) -> None:
    release = asyncio.Event()

    async def runner(code_id: str, on_progress: Any) -> IngestResult:
        on_progress("embedding", 2, 4)
        await release.wait()
        return IngestResult(act_id="a", articles_count=1, chunks_count=2)

    manager = JobManager(runner)
    async with _client(_app(manifest_path, manager)) as client:
        accepted = await client.post("/admin/ingest", json={"code_id": "ГК-1"})
        assert accepted.status_code == 202
        job_id = accepted.json()["job_id"]

        busy = await client.post("/admin/ingest", json={"code_id": "ГК-1"})
        assert busy.status_code == 409

        await asyncio.sleep(0)  # дать джобу прокрутиться до release.wait()
        polled = await client.get(f"/admin/jobs/{job_id}")
        assert polled.json()["state"] == "running"
        assert polled.json()["stage"] == "embedding"
        assert polled.json()["progress_done"] == 2

        release.set()
        await manager.wait()
        done = await client.get(f"/admin/jobs/{job_id}")
        assert done.json()["state"] == "succeeded"
        assert done.json()["chunks_count"] == 2

        listing = await client.get("/admin/jobs")
        assert [j["id"] for j in listing.json()["jobs"]] == [job_id]


@pytest.mark.asyncio
async def test_ingest_unknown_code_404_missing_file_422(
    manifest_path: Path, tmp_path: Path
) -> None:
    manager = JobManager(AsyncMock())
    async with _client(_app(manifest_path, manager)) as client:
        unknown = await client.post("/admin/ingest", json={"code_id": "НЕТ"})
        assert unknown.status_code == 404

        (manifest_path.parent / "gk1.docx").unlink()
        missing = await client.post("/admin/ingest", json={"code_id": "ГК-1"})
        assert missing.status_code == 422


@pytest.mark.asyncio
async def test_cancel_running_job(manifest_path: Path) -> None:
    started = asyncio.Event()

    async def runner(code_id: str, on_progress: Any) -> IngestResult:
        started.set()
        await asyncio.sleep(60)
        return IngestResult(act_id="a", articles_count=0, chunks_count=0)

    manager = JobManager(runner)
    async with _client(_app(manifest_path, manager)) as client:
        accepted = await client.post("/admin/ingest", json={"code_id": "ГК-1"})
        job_id = accepted.json()["job_id"]
        await started.wait()

        cancelled = await client.post(f"/admin/jobs/{job_id}/cancel")
        assert cancelled.status_code == 200
        await manager.wait()
        polled = await client.get(f"/admin/jobs/{job_id}")
        assert polled.json()["state"] == "cancelled"

        again = await client.post(f"/admin/jobs/{job_id}/cancel")
        assert again.status_code == 404


@pytest.mark.asyncio
async def test_jobs_404_and_indexes_status(manifest_path: Path) -> None:
    manager = JobManager(AsyncMock())
    app = _app(manifest_path, manager)
    inspect_mock = AsyncMock(
        return_value={"chunks_embedding_hnsw": True, "chunks_search_vector_gin": False}
    )
    async with _client(app) as client:
        missing = await client.get("/admin/jobs/nope")
        assert missing.status_code == 404

        original = routes.inspect_search_indexes
        routes.inspect_search_indexes = inspect_mock  # type: ignore[assignment]
        try:
            idx = await client.get("/admin/indexes")
        finally:
            routes.inspect_search_indexes = original  # type: ignore[assignment]
    assert idx.json() == {"hnsw": True, "gin": False}


def test_admin_routes_wired_into_rag_app() -> None:
    from neurolegal.rag.api.app import app as rag_app

    paths = {getattr(route, "path", None) for route in rag_app.routes}
    assert "/admin/documents" in paths
    assert "/admin/ingest" in paths
    assert "/admin/jobs" in paths
    assert "/admin/indexes" in paths
