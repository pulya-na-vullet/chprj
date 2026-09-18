from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from neurolegal.contracts import SearchedArticle
from neurolegal.rag.embedding import Embedder
from neurolegal.rag.store.search import hybrid_search


class RetrievalService:
    def __init__(self, embedder: Embedder) -> None:
        self._embedder = embedder

    async def search(
        self,
        session: AsyncSession,
        query: str,
        acts: Sequence[str] | None = None,
        limit: int = 8,
        min_score: float | None = None,
    ) -> list[SearchedArticle]:
        vectors = await self._embedder.embed([query])
        return await hybrid_search(
            session,
            query_vector=vectors[0],
            query_text=query,
            acts=acts,
            limit=limit,
            min_score=min_score,
        )
