from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from neurolegal.rag.api.deps import db_session

router = APIRouter()


@router.get("/healthz")
async def healthz(session: Annotated[AsyncSession, Depends(db_session)]) -> dict[str, str]:
    await session.execute(text("SELECT 1"))
    return {"status": "ok", "db": "ok"}
