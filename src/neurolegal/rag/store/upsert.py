from collections.abc import Sequence

from sqlalchemy import delete, insert
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from neurolegal.core.domain import Article, Chunk, LegalAct, StructureNode
from neurolegal.rag.store.models import ActRow, ArticleRow, ChunkRow, StructureNodeRow

# Bulk INSERT triggers HNSW + GIN index maintenance per row; on a growing
# index a 500-row batch can run for minutes and exceed Neon's connection
# timeout. Smaller batches keep each statement short while the whole replace
# still runs in one transaction.
_INSERT_BATCH = 100


async def upsert_act(session: AsyncSession, act: LegalAct) -> str:
    base = pg_insert(ActRow).values(
        id=str(act.id),
        kind=act.kind,
        short_name=act.short_name,
        full_name=act.full_name,
        source=act.source,
        source_doc_id=act.source_doc_id,
        redaction=act.redaction,
        ingested_at=act.ingested_at,
    )
    stmt = base.on_conflict_do_update(
        constraint="uq_acts_source_doc_id",
        set_=dict(
            kind=base.excluded.kind,
            short_name=base.excluded.short_name,
            full_name=base.excluded.full_name,
            source=base.excluded.source,
            redaction=base.excluded.redaction,
            ingested_at=base.excluded.ingested_at,
        ),
    ).returning(ActRow.id)
    result = await session.execute(stmt)
    return str(result.scalar_one())


async def replace_act_content(
    session: AsyncSession,
    act_id: str,
    structure_nodes: Sequence[StructureNode],
    articles: Sequence[Article],
    chunks_with_emb: Sequence[Chunk],
) -> None:
    await session.execute(delete(ArticleRow).where(ArticleRow.act_id == act_id))
    await session.execute(delete(StructureNodeRow).where(StructureNodeRow.act_id == act_id))

    if structure_nodes:
        await session.execute(
            insert(StructureNodeRow),
            [
                {
                    "id": str(n.id),
                    "act_id": act_id,
                    "parent_id": str(n.parent_id) if n.parent_id else None,
                    "type": n.type,
                    "number": n.number,
                    "title": n.title,
                    "ordinal": n.ordinal,
                }
                for n in structure_nodes
            ],
        )

    for i in range(0, len(articles), _INSERT_BATCH):
        article_batch = articles[i : i + _INSERT_BATCH]
        await session.execute(
            insert(ArticleRow),
            [
                {
                    "id": str(a.id),
                    "act_id": act_id,
                    "parent_node_id": str(a.parent_node_id) if a.parent_node_id else None,
                    "number": a.number,
                    "title": a.title,
                    "full_text": a.full_text,
                    "ordinal": a.ordinal,
                }
                for a in article_batch
            ],
        )

    for i in range(0, len(chunks_with_emb), _INSERT_BATCH):
        chunk_batch = chunks_with_emb[i : i + _INSERT_BATCH]
        await session.execute(
            insert(ChunkRow),
            [
                {
                    "id": str(c.id),
                    "article_id": str(c.article_id),
                    "act_id": act_id,
                    "path": c.path,
                    "part_number": c.part_number,
                    "point_number": c.point_number,
                    "sub_point_number": c.sub_point_number,
                    "text": c.text,
                    "ordinal": c.ordinal,
                    "embedding": c.embedding,
                    "structure_path": c.structure_path,
                }
                for c in chunk_batch
            ],
        )
