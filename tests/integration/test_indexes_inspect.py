"""Round-trip: inspect → drop → inspect → create → inspect.

Marker: db_only. Verifies inspect_search_indexes correctly reflects the
live state of the HNSW + GIN indexes against a real Postgres DB.
"""

from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from neurolegal.core.db import get_sessionmaker
from neurolegal.rag.store.indexes import (
    create_search_indexes,
    drop_search_indexes,
    inspect_search_indexes,
)

pytestmark = pytest.mark.db_only


@pytest_asyncio.fixture
async def session() -> AsyncGenerator[AsyncSession, None]:
    async with get_sessionmaker()() as s:
        yield s


@pytest.mark.asyncio
async def test_inspect_drop_create_round_trip(session: AsyncSession) -> None:
    # Initial state may be either fully present or partially dropped (drift);
    # we do not assert it. We assert the round-trip leaves both indexes present.
    initial = await inspect_search_indexes(session)
    assert set(initial.keys()) == {"chunks_embedding_hnsw", "chunks_search_vector_gin"}

    await drop_search_indexes(session)
    after_drop = await inspect_search_indexes(session)
    assert after_drop == {
        "chunks_embedding_hnsw": False,
        "chunks_search_vector_gin": False,
    }

    await create_search_indexes(session)
    after_create = await inspect_search_indexes(session)
    assert after_create == {
        "chunks_embedding_hnsw": True,
        "chunks_search_vector_gin": True,
    }
