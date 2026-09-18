"""Drop and recreate the search-side indexes on ``chunks``.

Incremental INSERTs into ``chunks`` trigger HNSW + GIN index maintenance per
row; on a populated index that maintenance dominates write time and trips
Neon's connection timeouts. Bulk-loading multiple acts is dramatically faster
when the indexes are dropped first and recreated once at the end.

Index DDL here must stay in sync with ``alembic/versions/0002_search_vector_indexes.py`` —
the migration is the source of truth at deploy time, this module is the
bulk-load equivalent at runtime.
"""

import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

_HNSW_NAME = "chunks_embedding_hnsw"
_GIN_NAME = "chunks_search_vector_gin"
_CREATE_HNSW = (
    f"CREATE INDEX {_HNSW_NAME} ON chunks USING hnsw (embedding vector_cosine_ops) "
    "WITH (m = 16, ef_construction = 64)"
)
_CREATE_GIN = f"CREATE INDEX {_GIN_NAME} ON chunks USING gin (search_vector)"


async def drop_search_indexes(session: AsyncSession) -> None:
    """Drop HNSW + GIN indexes if they exist. Idempotent."""
    logger.info("drop_search_indexes_start")
    await session.execute(text(f"DROP INDEX IF EXISTS {_HNSW_NAME}"))
    await session.execute(text(f"DROP INDEX IF EXISTS {_GIN_NAME}"))
    await session.commit()
    logger.info("drop_search_indexes_done")


async def create_search_indexes(session: AsyncSession) -> None:
    """Create HNSW + GIN indexes. Fails if they already exist."""
    logger.info("create_search_indexes_start")
    await session.execute(text(_CREATE_HNSW))
    await session.commit()
    await session.execute(text(_CREATE_GIN))
    await session.commit()
    logger.info("create_search_indexes_done")


async def inspect_search_indexes(session: AsyncSession) -> dict[str, bool]:
    """Return ``{index_name: present}`` for the HNSW + GIN search indexes.

    Queries ``pg_indexes`` so we never assert against SQLAlchemy metadata —
    the whole point is to surface drift between what migrations declared and
    what's live in Postgres (which a previous bulk-load drop_search_indexes
    might have removed without recreating).
    """
    result = await session.execute(
        text(
            "SELECT indexname FROM pg_indexes "
            "WHERE indexname IN (:hnsw, :gin) AND tablename = 'chunks'"
        ),
        {"hnsw": _HNSW_NAME, "gin": _GIN_NAME},
    )
    present = {row[0] for row in result}
    return {_HNSW_NAME: _HNSW_NAME in present, _GIN_NAME: _GIN_NAME in present}
