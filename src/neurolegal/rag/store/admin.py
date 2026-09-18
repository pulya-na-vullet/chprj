"""Admin-surface DB queries: per-act stats, inspection, deletion.

Plain SQL like the rest of store/ — these power the /admin/* routes only.
"""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from neurolegal.contracts import SearchedArticle, SearchedChunk


@dataclass
class ActDbStats:
    act_id: str
    source_doc_id: str
    short_name: str
    full_name: str
    kind: str
    ingested_at: datetime
    articles_count: int
    chunks_count: int


@dataclass
class ArticleListEntry:
    article_id: str
    number: str
    title: str | None
    chunks_count: int


@dataclass
class ChunkEntry:
    chunk_id: str
    path: str
    text: str
    ordinal: int


@dataclass
class ArticleDetailEntry:
    article_id: str
    act_short_name: str
    number: str
    title: str | None
    full_text: str
    chunks: list[ChunkEntry]


_ACT_STATS_SQL = text(
    """
    SELECT a.id, a.source_doc_id, a.short_name, a.full_name, a.kind, a.ingested_at,
           (SELECT count(*) FROM articles ar WHERE ar.act_id = a.id) AS articles_count,
           (SELECT count(*) FROM chunks c WHERE c.act_id = a.id) AS chunks_count
    FROM acts a
    ORDER BY a.short_name, a.full_name
    """
)


async def act_stats(session: AsyncSession) -> list[ActDbStats]:
    result = await session.execute(_ACT_STATS_SQL)
    return [
        ActDbStats(
            act_id=str(row.id),
            source_doc_id=row.source_doc_id,
            short_name=row.short_name,
            full_name=row.full_name,
            kind=row.kind,
            ingested_at=row.ingested_at,
            articles_count=row.articles_count,
            chunks_count=row.chunks_count,
        )
        for row in result
    ]


async def count_chunks(session: AsyncSession) -> int:
    result = await session.execute(text("SELECT count(*) FROM chunks"))
    return int(result.scalar_one())


async def db_size_bytes(session: AsyncSession) -> int:
    """On-disk size of the current database (tables + indexes + toast)."""
    result = await session.execute(text("SELECT pg_database_size(current_database())"))
    return int(result.scalar_one())


async def delete_act(session: AsyncSession, source_doc_id: str) -> bool:
    """Delete the act (FK cascades clear nodes/articles/chunks). True if found."""
    result = await session.execute(
        text("DELETE FROM acts WHERE source_doc_id = :sid RETURNING id"),
        {"sid": source_doc_id},
    )
    deleted = result.first() is not None
    await session.commit()
    return deleted


_LIST_ARTICLES_SQL = text(
    """
    SELECT ar.id, ar.number, ar.title, count(c.id) AS chunks_count
    FROM articles ar
    JOIN acts a ON a.id = ar.act_id
    LEFT JOIN chunks c ON c.article_id = ar.id
    WHERE a.source_doc_id = :sid
    GROUP BY ar.id, ar.number, ar.title, ar.ordinal
    ORDER BY ar.ordinal
    """
)


async def list_articles(session: AsyncSession, source_doc_id: str) -> list[ArticleListEntry]:
    result = await session.execute(_LIST_ARTICLES_SQL, {"sid": source_doc_id})
    return [
        ArticleListEntry(
            article_id=str(row.id),
            number=row.number,
            title=row.title,
            chunks_count=row.chunks_count,
        )
        for row in result
    ]


_GET_ARTICLE_BY_NUMBER_SQL = text(
    """
    SELECT
      a.id::text        AS article_id,
      ac.short_name     AS act_short_name,
      ac.kind           AS act_kind,
      a.number,
      a.title,
      a.full_text,
      COALESCE(
        json_agg(
          json_build_object(
            'chunk_id', c.id::text,
            'score', 0.0,
            'path', c.path,
            'text', c.text
          ) ORDER BY c.ordinal
        ) FILTER (WHERE c.id IS NOT NULL),
        '[]'::json
      ) AS matched_chunks
    FROM articles a
    JOIN acts ac ON ac.id = a.act_id
    LEFT JOIN chunks c ON c.article_id = a.id
    WHERE ac.short_name = :act_short_name
      AND a.number = :number
    GROUP BY a.id, ac.short_name, ac.kind
    """
)


async def get_article_by_number(
    session: AsyncSession, act_short_name: str, number: str
) -> SearchedArticle | None:
    """Exact lookup of a single article by act short name and article number.

    Returns a fully-populated SearchedArticle (score=0.0; matched_chunks
    contains all article chunks ordered by ordinal), or None if not found.
    """
    result = await session.execute(
        _GET_ARTICLE_BY_NUMBER_SQL,
        {"act_short_name": act_short_name, "number": number},
    )
    row = result.mappings().first()
    if row is None:
        return None
    matched = [SearchedChunk(**mc) for mc in row["matched_chunks"]]
    return SearchedArticle(
        article_id=row["article_id"],
        act_short_name=row["act_short_name"],
        act_kind=row["act_kind"],
        number=row["number"],
        title=row["title"],
        full_text=row["full_text"],
        matched_chunks=matched,
        score=0.0,
    )


async def article_detail(session: AsyncSession, article_id: str) -> ArticleDetailEntry | None:
    head = await session.execute(
        text(
            """
            SELECT ar.id, ar.number, ar.title, ar.full_text, a.short_name
            FROM articles ar JOIN acts a ON a.id = ar.act_id
            WHERE ar.id = :aid
            """
        ),
        {"aid": article_id},
    )
    row = head.first()
    if row is None:
        return None
    chunks = await session.execute(
        text("SELECT id, path, text, ordinal FROM chunks WHERE article_id = :aid ORDER BY ordinal"),
        {"aid": article_id},
    )
    return ArticleDetailEntry(
        article_id=str(row.id),
        act_short_name=row.short_name,
        number=row.number,
        title=row.title,
        full_text=row.full_text,
        chunks=[
            ChunkEntry(chunk_id=str(c.id), path=c.path, text=c.text, ordinal=c.ordinal)
            for c in chunks
        ],
    )
