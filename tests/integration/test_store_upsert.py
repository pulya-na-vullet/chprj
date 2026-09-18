from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from neurolegal.core.domain import Article, Chunk, LegalAct
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


@pytest.mark.asyncio(loop_scope="module")
async def test_upsert_act_idempotent(session: AsyncSession) -> None:
    act = LegalAct(
        id=uuid4(),
        kind="codex",
        short_name="ТК",
        full_name="Тестовый кодекс",
        source="test",
        source_doc_id="test-1",
        redaction="ред. 1",
        ingested_at=datetime.now(UTC),
    )
    aid_1 = await upsert_act(session, act)
    aid_2 = await upsert_act(session, act)
    assert aid_1 == aid_2

    row = await session.execute(text("SELECT kind FROM acts WHERE id = :aid"), {"aid": aid_1})
    assert row.scalar() == "codex"


@pytest.mark.asyncio(loop_scope="module")
async def test_upsert_act_identity_is_source_doc_id_not_source(session: AsyncSession) -> None:
    """Смена акваера (source) не должна задваивать акт (T-Task5b)."""
    act_v1 = LegalAct(
        id=uuid4(),
        kind="federal_law",
        short_name="ТестАкт",
        full_name="Тестовый акт v1",
        source="local-docx",
        source_doc_id="test-dup-act",
        redaction=None,
        ingested_at=datetime.now(UTC),
    )
    aid_1 = await upsert_act(session, act_v1)

    act_v2 = LegalAct(
        id=uuid4(),
        kind="federal_law",
        short_name="ТестАкт (обновлён)",
        full_name="Тестовый акт v1",
        source="s3-docx",
        source_doc_id="test-dup-act",
        redaction=None,
        ingested_at=datetime.now(UTC),
    )
    aid_2 = await upsert_act(session, act_v2)

    assert aid_1 == aid_2

    result = await session.execute(
        text("SELECT source, short_name FROM acts WHERE source_doc_id = :sid"),
        {"sid": "test-dup-act"},
    )
    rows = result.all()
    assert len(rows) == 1
    assert rows[0].source == "s3-docx"
    assert rows[0].short_name == "ТестАкт (обновлён)"


@pytest.mark.asyncio(loop_scope="module")
async def test_replace_act_content(session: AsyncSession) -> None:
    act = LegalAct(
        id=uuid4(),
        kind="codex",
        short_name="ТК2",
        full_name="Тестовый кодекс 2",
        source="test",
        source_doc_id="test-2",
        redaction=None,
        ingested_at=datetime.now(UTC),
    )
    act_id = await upsert_act(session, act)
    article_id = uuid4()
    article = Article(
        id=article_id,
        act_id=uuid4(),
        parent_node_id=None,
        number="1",
        title="Test",
        full_text="full text",
        ordinal=1,
    )
    chunk = Chunk(
        id=uuid4(),
        article_id=article_id,
        act_id=uuid4(),
        path="ст. 1",
        text="test chunk",
        ordinal=1,
        embedding=[0.1] * 1024,
        structure_path={"article": "1"},
    )
    await replace_act_content(session, act_id, [], [article], [chunk])
    await session.commit()

    result = await session.execute(
        text("SELECT COUNT(*) FROM chunks WHERE act_id = :aid"), {"aid": act_id}
    )
    assert result.scalar() == 1

    # Re-ingest должен заменить
    await replace_act_content(session, act_id, [], [article], [chunk])
    await session.commit()
    result = await session.execute(
        text("SELECT COUNT(*) FROM chunks WHERE act_id = :aid"), {"aid": act_id}
    )
    assert result.scalar() == 1
