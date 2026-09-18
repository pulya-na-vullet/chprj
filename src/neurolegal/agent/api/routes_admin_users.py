"""Operator user-management endpoints — internal only (T-0022).

Gated on `verify_internal_token`, never on `get_current_user`: these routes
are reached exclusively by the RAG service's `neurolegal.rag.agent_client`
(server-to-server HTTP, the RAG admin SPA's "Пользователи" tab), not by the
browser directly.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from neurolegal.agent.api.deps import verify_internal_token
from neurolegal.agent.auth.deps import get_auth_service, get_auth_store
from neurolegal.agent.auth.service import AuthService, UserNotFoundError
from neurolegal.agent.auth.store import AuthStore
from neurolegal.agent.store.models import UserRow
from neurolegal.contracts import AdminUserOut, AdminUserPatchRequest, AdminUsersResponse

router = APIRouter(
    prefix="/admin/users",
    tags=["admin-users"],
    dependencies=[Depends(verify_internal_token)],
)

_Store = Annotated[AuthStore, Depends(get_auth_store)]
_Service = Annotated[AuthService, Depends(get_auth_service)]


def _to_out(user: UserRow, conversation_count: int) -> AdminUserOut:
    return AdminUserOut(
        id=user.id,
        email=user.email,
        is_active=user.is_active,
        created_at=user.created_at,
        conversation_count=conversation_count,
    )


@router.get("", response_model=AdminUsersResponse)
async def list_users(store: _Store) -> AdminUsersResponse:
    rows = await store.list_users_with_conversation_counts()
    return AdminUsersResponse(users=[_to_out(user, count) for user, count in rows])


@router.patch("/{user_id}", response_model=AdminUserOut)
async def patch_user(
    user_id: str, req: AdminUserPatchRequest, service: _Service, store: _Store
) -> AdminUserOut:
    # The everywhere-logout invariant (deactivation / password change drops
    # every session) lives in AuthService (T-0033); the route just maps the
    # miss to 404 and reads the conversation count for the DTO.
    try:
        user = await service.admin_patch_user(
            user_id, is_active=req.is_active, new_password=req.new_password
        )
    except UserNotFoundError:
        raise HTTPException(status_code=404, detail="user_not_found") from None
    count = await store.count_conversations(user_id)
    return _to_out(user, count)
