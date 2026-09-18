"""JobManager: переходы состояний, занятость, отмена; runner: авто-bulk."""

import asyncio
from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import AsyncMock

import pytest

import neurolegal.rag.jobs as jobs_mod
from neurolegal.rag.jobs import JobBusyError, JobManager, make_ingest_runner
from neurolegal.rag.pipelines.ingest import IngestResult


async def _ok_runner(code_id: str, on_progress: Any) -> IngestResult:
    on_progress("embedding", 1, 4)
    await asyncio.sleep(0)
    return IngestResult(act_id="a1", articles_count=2, chunks_count=5)


async def _failing_runner(code_id: str, on_progress: Any) -> IngestResult:
    on_progress("parsing", 0, 0)
    raise ValueError("boom")


@pytest.mark.asyncio
async def test_job_succeeds_with_result_counts() -> None:
    jm = JobManager(_ok_runner)
    job = jm.start("ГК")
    assert job.state == "running"
    await jm.wait()
    assert job.state == "succeeded"
    assert job.stage == "embedding"
    assert (job.progress_done, job.progress_total) == (1, 4)
    assert (job.articles_count, job.chunks_count) == (2, 5)
    assert job.finished_at is not None
    assert jm.active is None


@pytest.mark.asyncio
async def test_second_start_raises_busy() -> None:
    started = asyncio.Event()
    release = asyncio.Event()

    async def slow(code_id: str, on_progress: Any) -> IngestResult:
        started.set()
        await release.wait()
        return IngestResult(act_id="a", articles_count=0, chunks_count=0)

    jm = JobManager(slow)
    jm.start("ГК")
    await started.wait()
    with pytest.raises(JobBusyError):
        jm.start("УК")
    release.set()
    await jm.wait()


@pytest.mark.asyncio
async def test_failure_captures_stage_and_error() -> None:
    jm = JobManager(_failing_runner)
    job = jm.start("ГК")
    await jm.wait()
    assert job.state == "failed"
    assert job.error == "parsing: boom"


@pytest.mark.asyncio
async def test_cancel_running_job() -> None:
    started = asyncio.Event()

    async def hang(code_id: str, on_progress: Any) -> IngestResult:
        started.set()
        await asyncio.sleep(60)
        return IngestResult(act_id="a", articles_count=0, chunks_count=0)

    jm = JobManager(hang)
    job = jm.start("ГК")
    await started.wait()
    assert jm.cancel(job.id) is True
    await jm.wait()
    assert job.state == "cancelled"
    assert jm.cancel(job.id) is False  # уже не running


@pytest.mark.asyncio
async def test_history_trimmed_newest_first() -> None:
    jm = JobManager(_ok_runner, history_limit=2)
    ids = []
    for code in ("ГК", "УК", "ВК"):
        ids.append(jm.start(code).id)
        await jm.wait()
    listed = jm.list()
    assert [j.id for j in listed] == [ids[2], ids[1]]


# --- make_ingest_runner: авто-bulk ---


@asynccontextmanager
async def _fake_session() -> Any:
    yield AsyncMock()


def _patch_runner_deps(
    monkeypatch: pytest.MonkeyPatch, calls: list[str], chunk_count: int, fail: bool = False
) -> None:
    class FakePipeline:
        async def run(self, code_id: str, on_progress: Any = None) -> IngestResult:
            calls.append("run")
            if fail:
                raise RuntimeError("ingest blew up")
            return IngestResult(act_id="a", articles_count=1, chunks_count=2)

    async def fake_drop(session: Any) -> None:
        calls.append("drop")

    async def fake_create(session: Any) -> None:
        calls.append("create")

    class _FakeDialect:
        name = "sqlite"  # routes _ingest_advisory_lock down the no-op branch

    class _FakeEngine:
        dialect = _FakeDialect()

    monkeypatch.setattr(jobs_mod, "load_manifest", lambda path: "MANIFEST")
    monkeypatch.setattr(jobs_mod, "make_embedder", lambda: "EMB")
    monkeypatch.setattr(jobs_mod, "get_engine", lambda: _FakeEngine())
    monkeypatch.setattr(jobs_mod, "get_sessionmaker", lambda: lambda: _fake_session())
    monkeypatch.setattr(jobs_mod, "count_chunks", AsyncMock(return_value=chunk_count))
    monkeypatch.setattr(jobs_mod, "drop_search_indexes", fake_drop)
    monkeypatch.setattr(jobs_mod, "create_search_indexes", fake_create)
    monkeypatch.setattr(jobs_mod, "build_pipeline", lambda *a, **k: FakePipeline())


@pytest.mark.asyncio
async def test_runner_bulk_above_threshold(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    _patch_runner_deps(monkeypatch, calls, chunk_count=50_000)
    runner = make_ingest_runner(manifest_path=None)  # type: ignore[arg-type]
    await runner("ГК", lambda s, d, t: None)
    assert calls == ["drop", "run", "create"]


@pytest.mark.asyncio
async def test_runner_no_bulk_below_threshold(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    _patch_runner_deps(monkeypatch, calls, chunk_count=100)
    runner = make_ingest_runner(manifest_path=None)  # type: ignore[arg-type]
    await runner("ГК", lambda s, d, t: None)
    assert calls == ["run"]


@pytest.mark.asyncio
async def test_runner_recreates_indexes_on_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    _patch_runner_deps(monkeypatch, calls, chunk_count=50_000, fail=True)
    runner = make_ingest_runner(manifest_path=None)  # type: ignore[arg-type]
    with pytest.raises(RuntimeError, match="ingest blew up"):
        await runner("ГК", lambda s, d, t: None)
    assert calls == ["drop", "run", "create"]
