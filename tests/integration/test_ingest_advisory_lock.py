"""Cross-process ingest advisory lock (T-0032) against real Postgres.

The in-memory JobManager only serializes one worker; `_ingest_advisory_lock`
adds a Postgres session-scoped lock so a second concurrent ingest (another
uvicorn worker) can't race the shared index DDL. Verifies mutual exclusion and
that the lock is released on exit so a later ingest can proceed.
"""

import pytest

from neurolegal.rag.jobs import JobBusyError, _ingest_advisory_lock

pytestmark = pytest.mark.db_only


@pytest.mark.asyncio
async def test_second_concurrent_lock_raises_job_busy() -> None:
    async with _ingest_advisory_lock():
        with pytest.raises(JobBusyError):
            async with _ingest_advisory_lock():
                pass


@pytest.mark.asyncio
async def test_lock_is_released_after_exit() -> None:
    async with _ingest_advisory_lock():
        pass
    # a fresh acquisition after the first released must succeed
    async with _ingest_advisory_lock():
        pass
