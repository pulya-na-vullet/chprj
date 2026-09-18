"""Dependency wiring for the documents hub API."""

import secrets
from collections.abc import AsyncGenerator, Callable
from functools import lru_cache
from typing import Annotated

from fastapi import Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from neurolegal.core.config import settings as core_settings
from neurolegal.core.db import get_sessionmaker, session_dependency
from neurolegal.documents.config import settings
from neurolegal.documents.store.blob import BlobStore, build_blob_store
from neurolegal.documents.store.document_store import DocumentStore


async def db_session() -> AsyncGenerator[AsyncSession, None]:
    async for session in session_dependency():
        yield session


async def verify_internal_token(
    x_internal_token: Annotated[str | None, Header()] = None,
) -> None:
    """Gate every document route on the agent<->hub shared secret.

    A no-op when the operator hasn't configured NEUROLEGAL_INTERNAL_TOKEN
    (local dev default); once set, every request must present a matching
    X-Internal-Token (constant-time compare).
    """
    expected = core_settings.internal_token
    if expected is None:
        return
    if x_internal_token is None or not secrets.compare_digest(x_internal_token, expected):
        raise HTTPException(status_code=401, detail="invalid_internal_token")


def get_store(session: Annotated[AsyncSession, Depends(db_session)]) -> DocumentStore:
    return DocumentStore(session)


def get_session_factory() -> Callable[[], AsyncSession]:
    return get_sessionmaker()


@lru_cache(maxsize=1)
def get_blob_store() -> BlobStore:
    return build_blob_store(settings)
