from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from neurolegal.contracts import SearchResponse
from neurolegal.rag.api.deps import db_session
from neurolegal.rag.store.admin import get_article_by_number

router = APIRouter()


@router.get("/article", response_model=SearchResponse)
async def article(
    act: Annotated[str, Query(min_length=1)],
    number: Annotated[str, Query(min_length=1)],
    session: Annotated[AsyncSession, Depends(db_session)],
) -> SearchResponse:
    found = await get_article_by_number(session, act, number)
    return SearchResponse(articles=[found] if found else [])
