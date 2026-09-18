"""GET /templates — proxies the templates service's published list for the
«Шаблоны» section of the SPA (браузер никогда не ходит на :8003 напрямую)."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from neurolegal.agent.api.deps import get_templates_client
from neurolegal.agent.auth.deps import get_current_user
from neurolegal.agent.store.models import UserRow
from neurolegal.agent.tools.templates_client import AgentTemplatesClient, TemplatesClientError
from neurolegal.contracts import TemplateListResponse

router = APIRouter()


@router.get("/templates", response_model=TemplateListResponse)
async def list_templates(
    client: Annotated[AgentTemplatesClient, Depends(get_templates_client)],
    user: Annotated[UserRow, Depends(get_current_user)],
) -> TemplateListResponse:
    try:
        templates = await client.list_templates()
    except TemplatesClientError as exc:
        raise HTTPException(status_code=503, detail="templates unavailable") from exc
    return TemplateListResponse(templates=templates)
