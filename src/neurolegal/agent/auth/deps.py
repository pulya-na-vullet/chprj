"""FastAPI dependency wiring for neurolegal.agent.auth.

Mirrors the pattern in `agent.api.deps`: a per-request DB session backs a
per-request store; the stateless rate limiter is a process-wide singleton
via `lru_cache`. Kept self-contained (only depends on `neurolegal.core`) so
`get_current_user` can be imported and reused by other routers without
pulling in the rest of the agent API wiring — T-0021 hangs it off the
remaining user-facing routes.
"""

from collections.abc import AsyncGenerator
from functools import lru_cache
from typing import Annotated

from fastapi import Cookie, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from neurolegal.agent.auth.limiter import RateLimiter
from neurolegal.agent.auth.service import AuthService
from neurolegal.agent.auth.store import AuthStore
from neurolegal.agent.store.models import UserRow
from neurolegal.core.db import session_dependency

SESSION_COOKIE_NAME = "neurolegal_session"


# Per-module DB-session seam — a distinct callable from rag/api/deps and
# agent/api/deps so each is its own `dependency_overrides` key (a test
# overriding one doesn't silently affect another). All delegate to the shared
# `session_dependency`.
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    async for session in session_dependency():
        yield session


def get_auth_store(session: Annotated[AsyncSession, Depends(db_session)]) -> AuthStore:
    return AuthStore(session)


@lru_cache(maxsize=1)
def get_rate_limiter() -> RateLimiter:
    return RateLimiter()


def get_auth_service(
    store: Annotated[AuthStore, Depends(get_auth_store)],
) -> AuthService:
    return AuthService(store=store)


async def get_current_user(
    service: Annotated[AuthService, Depends(get_auth_service)],
    session_token: Annotated[str | None, Cookie(alias=SESSION_COOKIE_NAME)] = None,
) -> UserRow:
    if session_token is None:
        raise HTTPException(status_code=401, detail="not_authenticated")
    user = await service.get_current_user(session_token)
    if user is None:
        raise HTTPException(status_code=401, detail="not_authenticated")
    return user
