"""Dependency wiring for the templates service API."""

import secrets
from collections.abc import AsyncGenerator
from functools import lru_cache
from typing import Annotated

from fastapi import Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from neurolegal.core.config import settings as core_settings
from neurolegal.core.db import session_dependency
from neurolegal.templates.config import settings
from neurolegal.templates.store.blob import TemplatesBlobStore, build_templates_blob_store
from neurolegal.templates.store.template_store import TemplateStore


async def verify_internal_token(
    x_internal_token: Annotated[str | None, Header()] = None,
) -> None:
    """Gate the operator routes on the shared internal secret.

    A no-op when the operator hasn't configured NEUROLEGAL_INTERNAL_TOKEN
    (local dev default); once set, every request must present a matching
    X-Internal-Token (constant-time compare). Same contract as the hub's.
    """
    expected = core_settings.internal_token
    if expected is None:
        return
    if x_internal_token is None or not secrets.compare_digest(x_internal_token, expected):
        raise HTTPException(status_code=401, detail="invalid_internal_token")


async def db_session() -> AsyncGenerator[AsyncSession, None]:
    async for session in session_dependency():
        yield session


def get_store(session: Annotated[AsyncSession, Depends(db_session)]) -> TemplateStore:
    return TemplateStore(session)


@lru_cache(maxsize=1)
def get_blob_store() -> TemplatesBlobStore | None:
    """`None` without S3 credentials — list/detail keep working, render 503s."""
    return build_templates_blob_store(settings)
