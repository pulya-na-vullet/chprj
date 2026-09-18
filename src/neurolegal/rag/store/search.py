from collections.abc import Sequence

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from neurolegal.contracts import SearchedArticle, SearchedChunk
from neurolegal.core.config import settings
from neurolegal.core.domain import EMBEDDING_DIM

HYBRID_SEARCH_SQL = f"""
WITH params AS (
  SELECT CAST(:qvec AS vector({EMBEDDING_DIM})) AS qvec,
         CAST(:qtext AS text) AS qtext
),
act_filter AS (
  SELECT id FROM acts
  WHERE CAST(:all_acts AS bool) OR short_name = ANY(CAST(:acts AS text[]))
),
dense AS (
  SELECT c.id, c.article_id,
         1.0 / (60 + ROW_NUMBER() OVER (ORDER BY c.embedding <=> p.qvec)) AS rrf
  FROM chunks c, params p
  WHERE c.act_id IN (SELECT id FROM act_filter)
  ORDER BY c.embedding <=> p.qvec
  LIMIT 40
),
sparse AS (
  SELECT c.id, c.article_id,
         1.0 / (60 + ROW_NUMBER() OVER (
           ORDER BY ts_rank(c.search_vector, websearch_to_tsquery('russian', p.qtext)) DESC
         )) AS rrf
  FROM chunks c, params p
  WHERE c.act_id IN (SELECT id FROM act_filter)
    AND c.search_vector @@ websearch_to_tsquery('russian', p.qtext)
  ORDER BY ts_rank(c.search_vector, websearch_to_tsquery('russian', p.qtext)) DESC
  LIMIT 40
),
fused AS (
  SELECT id, article_id, SUM(rrf) AS score
  FROM (SELECT * FROM dense UNION ALL SELECT * FROM sparse) u
  GROUP BY id, article_id
),
top_articles AS (
  SELECT article_id, MAX(score) AS article_score
  FROM fused
  GROUP BY article_id
  HAVING MAX(score) >= :min_score
  ORDER BY article_score DESC
  LIMIT :limit
)
SELECT
  a.id::text       AS article_id,
  ac.short_name    AS act_short_name,
  ac.kind          AS act_kind,
  a.number,
  a.title,
  a.full_text,
  ta.article_score,
  json_agg(
    json_build_object(
      'chunk_id', f.id::text,
      'score', f.score,
      'path', c.path,
      'text', c.text
    ) ORDER BY f.score DESC
  ) AS matched_chunks
FROM top_articles ta
JOIN articles a ON a.id = ta.article_id
JOIN acts ac ON ac.id = a.act_id
JOIN fused f ON f.article_id = ta.article_id
JOIN chunks c ON c.id = f.id
GROUP BY a.id, ac.short_name, ac.kind, ta.article_score
ORDER BY ta.article_score DESC
"""


def _qvec_literal(vec: Sequence[float]) -> str:
    return "[" + ",".join(repr(float(x)) for x in vec) + "]"


async def hybrid_search(
    session: AsyncSession,
    query_vector: Sequence[float],
    query_text: str,
    acts: Sequence[str] | None,
    limit: int,
    min_score: float | None = None,
) -> list[SearchedArticle]:
    acts_list = list(acts) if acts else []
    all_acts = len(acts_list) == 0

    # The dense CTE applies the act filter AFTER the HNSW scan, which only
    # retrieves ~ef_search global candidates (pgvector default: 40) — a
    # selective act filter can starve the dense leg to zero rows. Widen the
    # scan for this transaction only. SET LOCAL takes no bind params; the
    # value is an int from validated settings.
    await session.execute(text(f"SET LOCAL hnsw.ef_search = {int(settings.hnsw_ef_search)}"))

    result = await session.execute(
        text(HYBRID_SEARCH_SQL),
        {
            "qvec": _qvec_literal(query_vector),
            "qtext": query_text,
            "acts": acts_list,
            "all_acts": all_acts,
            "limit": limit,
            "min_score": float(min_score) if min_score is not None else 0.0,
        },
    )
    rows = result.mappings().all()

    articles: list[SearchedArticle] = []
    for row in rows:
        matched = [SearchedChunk(**mc) for mc in row["matched_chunks"]]
        articles.append(
            SearchedArticle(
                article_id=row["article_id"],
                act_short_name=row["act_short_name"],
                act_kind=row["act_kind"],
                number=row["number"],
                title=row["title"],
                full_text=row["full_text"],
                matched_chunks=matched,
                score=float(row["article_score"]),
            )
        )
    return articles
