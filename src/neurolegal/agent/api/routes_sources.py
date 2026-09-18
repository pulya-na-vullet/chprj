"""Agent-side proxy for the «Источники права» catalog (RAG /sources)."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from neurolegal.agent.api.deps import get_rag_client
from neurolegal.agent.auth.deps import get_current_user
from neurolegal.agent.store.models import UserRow
from neurolegal.agent.tools.rag_client import RagClient, RagClientError
from neurolegal.contracts import SourceArticleDetail, SourceArticlesResponse, SourcesResponse

router = APIRouter()

_Rag = Annotated[RagClient, Depends(get_rag_client)]
_User = Annotated[UserRow, Depends(get_current_user)]


@router.get("/sources", response_model=SourcesResponse)
async def sources(rag: _Rag, user: _User) -> SourcesResponse:
    try:
        return await rag.list_sources()
    except RagClientError as exc:
        raise HTTPException(status_code=503, detail="sources unavailable") from exc


@router.get("/sources/{source_doc_id}/articles", response_model=SourceArticlesResponse)
async def source_articles(source_doc_id: str, rag: _Rag, user: _User) -> SourceArticlesResponse:
    try:
        return await rag.source_articles(source_doc_id)
    except RagClientError as exc:
        raise HTTPException(status_code=503, detail="sources unavailable") from exc


@router.get("/sources/articles/{article_id}", response_model=SourceArticleDetail)
async def article(article_id: str, rag: _Rag, user: _User) -> SourceArticleDetail:
    try:
        return await rag.article_detail(article_id)
    except RagClientError as exc:
        raise HTTPException(status_code=503, detail="sources unavailable") from exc
