from collections.abc import AsyncGenerator

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from neurolegal.core.config import settings, to_asyncpg_url

pytestmark = pytest.mark.db_only


@pytest.fixture
async def engine() -> AsyncGenerator[AsyncEngine, None]:
    engine = create_async_engine(to_asyncpg_url(settings.database_url))
    yield engine
    await engine.dispose()


async def test_pgvector_extension(engine: AsyncEngine) -> None:
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT extname FROM pg_extension WHERE extname='vector'"))
        rows = result.fetchall()
    assert len(rows) == 1


async def test_all_tables_exist(engine: AsyncEngine) -> None:
    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                "SELECT tablename FROM pg_tables WHERE schemaname='public' "
                "AND tablename IN ('acts','structure_nodes','articles','chunks') "
                "ORDER BY tablename"
            )
        )
        names = [r[0] for r in result.fetchall()]
    assert names == ["acts", "articles", "chunks", "structure_nodes"]


async def test_search_vector_is_generated(engine: AsyncEngine) -> None:
    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                "SELECT is_generated, generation_expression FROM information_schema.columns "
                "WHERE table_name='chunks' AND column_name='search_vector'"
            )
        )
        row = result.fetchone()
    assert row is not None
    assert row[0] == "ALWAYS"
    assert "to_tsvector" in row[1] and "russian" in row[1]


async def test_hnsw_index_exists(engine: AsyncEngine) -> None:
    async with engine.connect() as conn:
        result = await conn.execute(
            text("SELECT indexname FROM pg_indexes WHERE indexname='chunks_embedding_hnsw'")
        )
        row = result.fetchone()
    assert row is not None


async def test_gin_index_exists(engine: AsyncEngine) -> None:
    async with engine.connect() as conn:
        result = await conn.execute(
            text("SELECT indexname FROM pg_indexes WHERE indexname='chunks_search_vector_gin'")
        )
        row = result.fetchone()
    assert row is not None
