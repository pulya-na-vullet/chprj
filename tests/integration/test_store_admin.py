from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from neurolegal.core.domain import Article, Chunk, LegalAct
from neurolegal.rag.store.admin import (
    act_stats,
    article_detail,
    count_chunks,
    db_size_bytes,
    delete_act,
    list_articles,
)
from neurolegal.rag.store.db import get_sessionmaker
from neurolegal.rag.store.upsert import replace_act_content, upsert_act

pytestmark = pytest.mark.db_only


@pytest_asyncio.fixture(loop_scope="module")
async def session() -> AsyncGenerator[AsyncSession, None]:
    async with get_sessionmaker()() as s:
        yield s
        await s.rollback()
        await s.execute(text("DELETE FROM acts WHERE source_doc_id LIKE 'test-%'"))
        await s.commit()


async def _seed(session: AsyncSession, sid: str) -> tuple[str, str]:
    """Insert an act with one article and two chunks; return (act_id, article_id)."""
    act = LegalAct(
        id=uuid4(),
        kind="codex",
        short_name="ТК-АДМ",
        full_name="Тестовый кодекс (админ)",
        source="test",
        source_doc_id=sid,
        ingested_at=datetime.now(UTC),
    )
    act_id = await upsert_act(session, act)
    article_id = uuid4()
    article = Article(
        id=article_id,
        act_id=uuid4(),
        number="1",
        title="Тест",
        full_text="полный текст",
        ordinal=1,
    )
    chunks = [
        Chunk(
            id=uuid4(),
            article_id=article_id,
            act_id=uuid4(),
            path=f"ст. 1 ч. {n}",
            text=f"чанк {n}",
            ordinal=n,
            embedding=[0.0] * 1024,
            structure_path={"article": "1"},
        )
        for n in (1, 2)
    ]
    await replace_act_content(session, act_id, [], [article], chunks)
    await session.commit()
    return act_id, str(article_id)


@pytest.mark.asyncio(loop_scope="module")
async def test_act_stats_counts(session: AsyncSession) -> None:
    await _seed(session, "test-admin-1")
    stats = [s for s in await act_stats(session) if s.source_doc_id == "test-admin-1"]
    assert len(stats) == 1
    assert stats[0].articles_count == 1
    assert stats[0].chunks_count == 2
    assert stats[0].short_name == "ТК-АДМ"


@pytest.mark.asyncio(loop_scope="module")
async def test_count_chunks_and_articles_listing(session: AsyncSession) -> None:
    _, article_id = await _seed(session, "test-admin-2")
    assert await count_chunks(session) >= 2

    items = await list_articles(session, "test-admin-2")
    assert [(i.number, i.chunks_count) for i in items] == [("1", 2)]

    detail = await article_detail(session, article_id)
    assert detail is not None
    assert detail.full_text == "полный текст"
    assert [c.ordinal for c in detail.chunks] == [1, 2]
    assert detail.act_short_name == "ТК-АДМ"

    assert await article_detail(session, str(uuid4())) is None


@pytest.mark.asyncio(loop_scope="module")
async def test_db_size_bytes_positive(session: AsyncSession) -> None:
    assert await db_size_bytes(session) > 0


@pytest.mark.asyncio(loop_scope="module")
async def test_delete_act_cascades(session: AsyncSession) -> None:
    await _seed(session, "test-admin-3")
    assert await delete_act(session, "test-admin-3") is True
    assert await delete_act(session, "test-admin-3") is False
    rows = await session.execute(
        text("SELECT count(*) FROM acts WHERE source_doc_id = 'test-admin-3'")
    )
    assert rows.scalar() == 0
