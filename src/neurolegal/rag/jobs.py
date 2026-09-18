"""In-memory ingest job manager for the admin API.

One job at a time: a concurrent start raises JobBusyError (the route maps it
to 409) — parallel ingest is unsafe because the bulk path drops the shared
search indexes. History lives in process memory (last `history_limit`) and is
lost on restart — acceptable for a single-operator local tool.
"""

from __future__ import annotations

import asyncio
import dataclasses
import logging
import uuid
from collections import OrderedDict
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import text

from neurolegal.rag.acquisition.corpus_store import build_corpus_store_or_none
from neurolegal.rag.acquisition.manifest import load_manifest
from neurolegal.rag.embedding import make_embedder
from neurolegal.rag.pipelines.factory import build_pipeline
from neurolegal.rag.pipelines.ingest import IngestResult, ProgressFn
from neurolegal.rag.store.admin import count_chunks
from neurolegal.rag.store.db import get_engine, get_sessionmaker
from neurolegal.rag.store.indexes import create_search_indexes, drop_search_indexes

logger = logging.getLogger(__name__)

#: Above this many vectors in `chunks`, per-row HNSW maintenance dominates
#: insert time — drop the search indexes first and recreate after (same rule
#: as CLI `--bulk`; see the operational notes in CLAUDE.md).
BULK_THRESHOLD = 30_000

#: Fixed key for the Postgres advisory lock that serializes ingest across
#: processes. The in-memory JobManager only guards one worker; with >1 uvicorn
#: worker two ingests could otherwise race on the shared search-index DDL
#: (bulk drop/recreate) and corrupt them. Arbitrary constant ("jura").
_INGEST_ADVISORY_LOCK_KEY = 0x6A757261

IngestRunner = Callable[[str, ProgressFn], Awaitable[IngestResult]]


class JobBusyError(RuntimeError):
    """A job is already running."""


@dataclass
class JobRecord:
    id: str
    code_id: str
    state: str = "running"
    stage: str = "starting"
    progress_done: int = 0
    progress_total: int = 0
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    finished_at: datetime | None = None
    error: str | None = None
    articles_count: int | None = None
    chunks_count: int | None = None

    def as_dict(self) -> dict[str, object]:
        return dataclasses.asdict(self)


class JobManager:
    def __init__(self, runner: IngestRunner, history_limit: int = 50) -> None:
        self._runner = runner
        self._history_limit = history_limit
        self._jobs: OrderedDict[str, JobRecord] = OrderedDict()
        self._active_task: asyncio.Task[None] | None = None
        self._active_id: str | None = None

    @property
    def active(self) -> JobRecord | None:
        return self._jobs.get(self._active_id) if self._active_id else None

    def get(self, job_id: str) -> JobRecord | None:
        return self._jobs.get(job_id)

    def list(self) -> list[JobRecord]:
        """Newest first."""
        return list(reversed(self._jobs.values()))

    def start(self, code_id: str) -> JobRecord:
        if self._active_id is not None:
            raise JobBusyError(f"job {self._active_id} is already running")
        job = JobRecord(id=uuid.uuid4().hex, code_id=code_id)
        self._jobs[job.id] = job
        while len(self._jobs) > self._history_limit:
            self._jobs.popitem(last=False)
        self._active_id = job.id
        self._active_task = asyncio.get_running_loop().create_task(self._run(job))
        return job

    def cancel(self, job_id: str) -> bool:
        if job_id != self._active_id or self._active_task is None:
            return False
        self._active_task.cancel()
        return True

    async def wait(self) -> None:
        """Await the active job, swallowing its outcome (tests / shutdown)."""
        if self._active_task is not None:
            await asyncio.wait([self._active_task])

    async def _run(self, job: JobRecord) -> None:
        def on_progress(stage: str, done: int, total: int) -> None:
            job.stage = stage
            job.progress_done = done
            job.progress_total = total

        try:
            result = await self._runner(job.code_id, on_progress)
            job.state = "succeeded"
            job.articles_count = result.articles_count
            job.chunks_count = result.chunks_count
        except asyncio.CancelledError:
            job.state = "cancelled"
        except Exception as exc:
            logger.exception("ingest_job_failed", extra={"code_id": job.code_id})
            job.state = "failed"
            job.error = f"{job.stage}: {exc}"
        finally:
            job.finished_at = datetime.now(UTC)
            self._active_id = None
            self._active_task = None


@asynccontextmanager
async def _ingest_advisory_lock() -> AsyncIterator[None]:
    """Cross-process mutex for ingest, held on a dedicated connection.

    On Postgres, take a session-scoped `pg_try_advisory_lock` so that even with
    more than one uvicorn worker only one ingest runs at a time (the shared
    HNSW/GIN drop-and-recreate is not safe to interleave). A second concurrent
    ingest fails to acquire and raises JobBusyError. On non-Postgres backends
    (SQLite unit tests) this is a no-op — those never run bulk index DDL.
    """
    engine = get_engine()
    if engine.dialect.name != "postgresql":
        yield
        return
    async with engine.connect() as conn:
        acquired = await conn.scalar(
            text("SELECT pg_try_advisory_lock(:key)"), {"key": _INGEST_ADVISORY_LOCK_KEY}
        )
        if not acquired:
            raise JobBusyError("another process is already running an ingest job")
        try:
            yield
        finally:
            await conn.execute(
                text("SELECT pg_advisory_unlock(:key)"), {"key": _INGEST_ADVISORY_LOCK_KEY}
            )


def make_ingest_runner(
    *, manifest_path: Path, bulk_threshold: int = BULK_THRESHOLD
) -> IngestRunner:
    """Production runner: fresh manifest per job, docx source, auto-bulk.

    Bulk mode is decided automatically by counting live vectors; the index
    recreate sits in `finally` so neither failure nor cancellation leaves the
    DB without search indexes. (After a task is cancelled, CancelledError is
    delivered once — awaits inside `finally` still run normally.) The whole run
    holds a cross-process advisory lock so a multi-worker deploy can't race two
    ingests on the shared index DDL.
    """

    async def run(code_id: str, on_progress: ProgressFn) -> IngestResult:
        async with _ingest_advisory_lock():
            manifest = load_manifest(manifest_path)
            session_factory = get_sessionmaker()
            # Без кредов используем только локальные docx_path — DocxAcquirer
            # объяснит это внятной ошибкой, если запись указывает на S3.
            pipeline = build_pipeline(
                "docx",
                manifest=manifest,
                embedder=make_embedder(),
                session_factory=session_factory,
                corpus_store=build_corpus_store_or_none(),
            )
            async with session_factory() as session:
                total = await count_chunks(session)
            bulk = total > bulk_threshold
            if bulk:
                on_progress("indexing", 0, 0)
                async with session_factory() as session:
                    await drop_search_indexes(session)
            try:
                return await pipeline.run(code_id, on_progress=on_progress)
            finally:
                if bulk:
                    on_progress("indexing", 0, 0)
                    async with session_factory() as session:
                        await create_search_indexes(session)

    return run
