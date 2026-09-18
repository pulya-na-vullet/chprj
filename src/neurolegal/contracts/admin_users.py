"""Operator user-management DTOs.

Served by the agent's internal `/admin/users*` endpoints (T-0022, design doc
§1.7) and re-shaped 1:1 by the RAG service's `/admin/users*` proxy — the
admin SPA only ever talks to RAG, never to the agent directly.

T-0026 dropped `email_verified` (every account is active at registration)
and made the PATCH a partial update: flip `is_active`, set a `new_password`
(operator password reset — the only reset path in the mail-less MVP), or
both.
"""

from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from neurolegal.contracts.auth import PASSWORD_MIN_LENGTH


class AdminUserOut(BaseModel):
    id: str
    email: str
    is_active: bool
    created_at: datetime
    conversation_count: int


class AdminUsersResponse(BaseModel):
    users: list[AdminUserOut]


class AdminUserPatchRequest(BaseModel):
    is_active: bool | None = None
    new_password: str | None = Field(None, min_length=PASSWORD_MIN_LENGTH)

    @model_validator(mode="after")
    def _require_some_change(self) -> "AdminUserPatchRequest":
        if self.is_active is None and self.new_password is None:
            raise ValueError("at least one of is_active / new_password is required")
        return self
