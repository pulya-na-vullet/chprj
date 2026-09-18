from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import text

from neurolegal.core.domain import EMBEDDING_DIM, Article, LegalAct, RawDocument, StructuredDoc
from neurolegal.rag.pipelines import IngestPipeline
from neurolegal.rag.store.db import get_sessionmaker

pytestmark = pytest.mark.db_only


class FakeAcquirer:
    async def fetch(self, code_id: str) -> RawDocument:
        return RawDocument(
            source="test",
            source_doc_id="test-pipeline",
            fetched_at=datetime.now(UTC),
            content_type="text/html",
            body_bytes=b"<html/>",
        )


class FakeParser:
    def parse(self, raw: RawDocument) -> StructuredDoc:
        act = LegalAct(
            id=uuid4(),
            kind="codex",
            short_name="ТП",
            full_name="Тест-кодекс pipeline",
            source="test",
            source_doc_id="test-pipeline",
            redaction=None,
            ingested_at=datetime.now(UTC),
        )
        articles = [
            Article(
                id=uuid4(),
                act_id=act.id,
                parent_node_id=None,
                number="1",
                title="Один",
                full_text="1. Первый пункт. 2. Второй пункт.",
                ordinal=1,
            ),
        ]
        return StructuredDoc(act=act, structure_nodes=[], articles=articles)


@pytest_asyncio.fixture(loop_scope="module")
async def session_cleanup() -> AsyncGenerator[None, None]:
    yield
    async with get_sessionmaker()() as s:
        await s.execute(text("DELETE FROM acts WHERE source_doc_id = 'test-pipeline'"))
        await s.commit()


@pytest.mark.asyncio(loop_scope="module")
async def test_pipeline_writes_chunks_with_embeddings(session_cleanup: None) -> None:
    fake_embedder = AsyncMock()
    fake_embedder.embed = AsyncMock(return_value=[[0.1] * EMBEDDING_DIM, [0.2] * EMBEDDING_DIM])

    pipeline = IngestPipeline(
        acquirer=FakeAcquirer(),
        parser=FakeParser(),
        embedder=fake_embedder,
        session_factory=lambda: get_sessionmaker()(),
    )
    result = await pipeline.run("test-pipeline")

    assert result.articles_count == 1
    assert result.chunks_count == 2

    async with get_sessionmaker()() as session:
        row = await session.execute(
            text("SELECT count(*) FROM chunks WHERE act_id = :aid"),
            {"aid": result.act_id},
        )
        assert row.scalar() == 2
