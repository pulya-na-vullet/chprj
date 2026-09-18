from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from neurolegal.contracts import SEARCH_QUERY_MAX_CHARS, RetrieveRequest, SearchResponse
from neurolegal.core.config import settings
from neurolegal.rag.api.deps import db_session, get_retrieval_service
from neurolegal.rag.retrieval import RetrievalService
from neurolegal.rag.store.search import hybrid_search

router = APIRouter()


@router.get("/search", response_model=SearchResponse)
async def search(
    q: Annotated[str, Query(min_length=1, max_length=SEARCH_QUERY_MAX_CHARS)],
    svc: Annotated[RetrievalService, Depends(get_retrieval_service)],
    session: Annotated[AsyncSession, Depends(db_session)],
    acts: Annotated[list[str] | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 8,
    min_score: Annotated[float | None, Query(ge=0.0)] = None,
) -> SearchResponse:
    # Explicit value (including 0.0) overrides the deployment floor;
    # None / absent falls back to settings.rag_min_score.
    effective = min_score if min_score is not None else settings.rag_min_score
    articles = await svc.search(session, q, acts=acts, limit=limit, min_score=effective)
    return SearchResponse(articles=articles)


@router.post("/retrieve", response_model=SearchResponse)
async def retrieve(
    req: RetrieveRequest,
    session: Annotated[AsyncSession, Depends(db_session)],
) -> SearchResponse:
    effective = req.min_score if req.min_score is not None else settings.rag_min_score
    articles = await hybrid_search(
        session,
        query_vector=req.query_vector,
        query_text=req.query_text,
        acts=req.acts,
        limit=req.limit,
        min_score=effective,
    )
    return SearchResponse(articles=articles)
