"""IngestPipeline.run reports stage progress through on_progress."""

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from neurolegal.core.domain import (
    Article,
    ArticlePoint,
    LegalAct,
    RawDocument,
    StructuredDoc,
)
from neurolegal.rag.pipelines.ingest import IngestPipeline


def _structured() -> StructuredDoc:
    act = LegalAct(
        id=uuid4(),
        kind="codex",
        short_name="ТК",
        full_name="Тестовый кодекс",
        source="test",
        source_doc_id="test-progress",
        ingested_at=datetime.now(UTC),
    )
    articles = [
        Article(
            id=uuid4(),
            act_id=act.id,
            number=str(n),
            title=f"Статья {n}",
            full_text=f"Текст статьи {n}",
            ordinal=n,
            points=[ArticlePoint(number="1", text=f"Пункт статьи {n}")],
        )
        for n in range(1, 4)
    ]
    return StructuredDoc(act=act, structure_nodes=[], articles=articles)


class _FakeAcquirer:
    async def fetch(self, code_id: str) -> RawDocument:
        return RawDocument(
            source="test",
            source_doc_id="test-progress",
            fetched_at=datetime.now(UTC),
            content_type="application/octet-stream",
            body_bytes=b"x",
        )


class _FakeParser:
    def parse(self, raw: RawDocument) -> StructuredDoc:
        return _structured()


class _FakeEmbedder:
    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [[0.0] * 1024 for _ in texts]


@asynccontextmanager
async def _fake_session() -> Any:
    yield AsyncMock()


@pytest.mark.asyncio
async def test_run_reports_stages_and_embedding_batches() -> None:
    pipeline = IngestPipeline(
        acquirer=_FakeAcquirer(),  # type: ignore[arg-type]
        parser=_FakeParser(),  # type: ignore[arg-type]
        embedder=_FakeEmbedder(),  # type: ignore[arg-type]
        session_factory=lambda: _fake_session(),
        embed_batch_size=2,
    )
    events: list[tuple[str, int, int]] = []

    with (
        patch("neurolegal.rag.pipelines.ingest.upsert_act", AsyncMock(return_value="act-1")),
        patch("neurolegal.rag.pipelines.ingest.replace_act_content", AsyncMock()),
    ):
        result = await pipeline.run("ТК", on_progress=lambda s, d, t: events.append((s, d, t)))

    assert result.articles_count == 3
    stages = [e[0] for e in events]
    assert stages[:3] == ["acquiring", "parsing", "chunking"]
    assert stages[-1] == "persisting"
    # 3 articles → 3 chunks, batch size 2 → 2 batches: (0,2), (1,2), (2,2)
    embed_events = [e for e in events if e[0] == "embedding"]
    assert embed_events == [("embedding", 0, 2), ("embedding", 1, 2), ("embedding", 2, 2)]


@pytest.mark.asyncio
async def test_run_without_callback_still_works() -> None:
    pipeline = IngestPipeline(
        acquirer=_FakeAcquirer(),  # type: ignore[arg-type]
        parser=_FakeParser(),  # type: ignore[arg-type]
        embedder=_FakeEmbedder(),  # type: ignore[arg-type]
        session_factory=lambda: _fake_session(),
    )
    with (
        patch("neurolegal.rag.pipelines.ingest.upsert_act", AsyncMock(return_value="act-1")),
        patch("neurolegal.rag.pipelines.ingest.replace_act_content", AsyncMock()),
    ):
        result = await pipeline.run("ТК")
    assert result.chunks_count == 3
