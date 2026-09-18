from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from neurolegal.contracts import ActsResponse, ActSummary
from neurolegal.rag.api.deps import db_session
from neurolegal.rag.store.acts import list_acts

router = APIRouter()


@router.get("/acts", response_model=ActsResponse)
async def acts(session: Annotated[AsyncSession, Depends(db_session)]) -> ActsResponse:
    entries = await list_acts(session)
    return ActsResponse(
        acts=[
            ActSummary(short_name=e.short_name, full_name=e.full_name, kind=e.kind) for e in entries
        ]
    )
