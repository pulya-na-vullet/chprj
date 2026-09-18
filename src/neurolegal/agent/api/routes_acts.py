"""GET /acts — proxies the RAG acts catalog for the source selector."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from neurolegal.agent.api.deps import get_rag_client
from neurolegal.agent.auth.deps import get_current_user
from neurolegal.agent.store.models import UserRow
from neurolegal.agent.tools.rag_client import RagClient, RagClientError
from neurolegal.contracts import ActsResponse

router = APIRouter()


@router.get("/acts", response_model=ActsResponse)
async def acts(
    rag: Annotated[RagClient, Depends(get_rag_client)],
    user: Annotated[UserRow, Depends(get_current_user)],
) -> ActsResponse:
    try:
        summaries = await rag.list_acts()
    except RagClientError as exc:
        raise HTTPException(status_code=503, detail="acts unavailable") from exc
    return ActsResponse(acts=summaries)
