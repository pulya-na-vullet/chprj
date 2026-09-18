import logging
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from neurolegal.core.domain import Chunk
from neurolegal.rag.acquisition import Acquirer
from neurolegal.rag.chunking import ChunkStrategy, chunk_article
from neurolegal.rag.embedding import Embedder
from neurolegal.rag.parsing import Parser
from neurolegal.rag.store.upsert import replace_act_content, upsert_act

logger = logging.getLogger(__name__)


@dataclass
class IngestResult:
    act_id: str
    articles_count: int
    chunks_count: int


SessionFactory = Callable[[], AbstractAsyncContextManager[AsyncSession]]

# (stage, done, total) — total is 0 for stages without granular progress.
ProgressFn = Callable[[str, int, int], None]


class IngestPipeline:
    def __init__(
        self,
        acquirer: Acquirer,
        parser: Parser,
        embedder: Embedder,
        session_factory: SessionFactory,
        embed_batch_size: int = 64,
        chunk_strategy: ChunkStrategy = ChunkStrategy.PER_POINT,
    ) -> None:
        self._acquirer = acquirer
        self._parser = parser
        self._embedder = embedder
        self._session_factory = session_factory
        self._embed_batch_size = embed_batch_size
        self._chunk_strategy = chunk_strategy

    async def run(self, code_id: str, on_progress: ProgressFn | None = None) -> IngestResult:
        def _report(stage: str, done: int = 0, total: int = 0) -> None:
            if on_progress is not None:
                on_progress(stage, done, total)

        logger.info("ingest_start", extra={"code_id": code_id})

        _report("acquiring")
        raw = await self._acquirer.fetch(code_id)
        logger.info("ingest_acquired", extra={"code_id": code_id, "bytes": len(raw.body_bytes)})

        _report("parsing")
        structured = self._parser.parse(raw)
        logger.info(
            "ingest_parsed",
            extra={
                "code_id": code_id,
                "articles": len(structured.articles),
                "structure_nodes": len(structured.structure_nodes),
            },
        )

        _report("chunking")
        all_chunks: list[Chunk] = []
        for art in structured.articles:
            all_chunks.extend(
                chunk_article(
                    art,
                    strategy=self._chunk_strategy,
                    act_short_name=structured.act.short_name,
                )
            )

        logger.info("ingest_chunked", extra={"code_id": code_id, "chunks": len(all_chunks)})

        total_batches = (len(all_chunks) + self._embed_batch_size - 1) // self._embed_batch_size
        _report("embedding", 0, total_batches)
        for batch_idx, i in enumerate(range(0, len(all_chunks), self._embed_batch_size)):
            batch = all_chunks[i : i + self._embed_batch_size]
            vectors = await self._embedder.embed([c.text for c in batch])
            for chunk, vec in zip(batch, vectors, strict=True):
                chunk.embedding = vec
            _report("embedding", batch_idx + 1, total_batches)

        logger.info("ingest_embedded", extra={"code_id": code_id})

        _report("persisting")
        async with self._session_factory() as session:
            persisted_act_id = await upsert_act(session, structured.act)
            await replace_act_content(
                session,
                persisted_act_id,
                structured.structure_nodes,
                structured.articles,
                all_chunks,
            )
            await session.commit()

        logger.info("ingest_done", extra={"code_id": code_id, "act_id": persisted_act_id})
        return IngestResult(
            act_id=persisted_act_id,
            articles_count=len(structured.articles),
            chunks_count=len(all_chunks),
        )
