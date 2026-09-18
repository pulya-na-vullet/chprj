"""Admin proxy for user management (T-0022).

Thin wrapper over `neurolegal.rag.agent_client` — the `users`/`auth_sessions`
tables are agent-owned; this router just forwards to the agent's internal
`/admin/users*` endpoints so the operator SPA has one place (the RAG admin
surface) to manage users. Mounted alongside the other admin routers under
`settings.admin_enabled`.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from neurolegal.contracts import AdminUserOut, AdminUserPatchRequest, AdminUsersResponse
from neurolegal.rag.agent_client import (
    AgentAuthMisconfiguredError,
    AgentClient,
    AgentClientError,
    AgentUserNotFoundError,
)
from neurolegal.rag.api.deps import get_agent_client

router = APIRouter(prefix="/admin/users", tags=["admin-users"])

_AgentClient = Annotated[AgentClient, Depends(get_agent_client)]


@router.get("", response_model=AdminUsersResponse)
async def list_users(client: _AgentClient) -> AdminUsersResponse:
    try:
        users = await client.list_users()
    except AgentAuthMisconfiguredError as exc:
        raise HTTPException(status_code=502, detail="agent_auth_misconfigured") from exc
    except AgentClientError as exc:
        raise HTTPException(status_code=502, detail=f"agent unavailable: {exc}") from exc
    return AdminUsersResponse(users=users)


@router.patch("/{user_id}", response_model=AdminUserOut)
async def patch_user(
    user_id: str, req: AdminUserPatchRequest, client: _AgentClient
) -> AdminUserOut:
    try:
        return await client.patch_user(
            user_id, is_active=req.is_active, new_password=req.new_password
        )
    except AgentUserNotFoundError as exc:
        raise HTTPException(status_code=404, detail="user_not_found") from exc
    except AgentAuthMisconfiguredError as exc:
        raise HTTPException(status_code=502, detail="agent_auth_misconfigured") from exc
    except AgentClientError as exc:
        raise HTTPException(status_code=502, detail=f"agent unavailable: {exc}") from exc
