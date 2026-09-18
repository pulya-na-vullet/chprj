from collections.abc import AsyncGenerator
from functools import lru_cache
from pathlib import Path

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from neurolegal.core.config import settings
from neurolegal.rag.acquisition.corpus_store import CorpusStore, build_corpus_store_or_none
from neurolegal.rag.agent_client import AgentClient
from neurolegal.rag.embedding import Embedder, make_embedder
from neurolegal.rag.jobs import JobManager
from neurolegal.rag.retrieval import RetrievalService
from neurolegal.rag.store.db import session_dependency
from neurolegal.rag.templates_client import TemplatesClient

# T-0013: короткий таймаут на эмбеддинг ЗАПРОСА (p99 наблюдался ~3 c при
# sort=latency). Подвисшее соединение обрезается за 15 c, и ретрай tenacity
# успевает за секунды — вместо 60-секундного дефолта, из-за которого один
# зависший запрос стоил пользователю минуту ожидания поиска.
QUERY_EMBED_TIMEOUT = 15.0


@lru_cache(maxsize=1)
def get_embedder() -> Embedder:
    return make_embedder(timeout=QUERY_EMBED_TIMEOUT)


@lru_cache(maxsize=1)
def get_agent_client() -> AgentClient:
    return AgentClient(base_url=settings.agent_base_url, internal_token=settings.internal_token)


@lru_cache(maxsize=1)
def get_templates_client() -> TemplatesClient:
    return TemplatesClient(
        base_url=settings.templates_base_url, internal_token=settings.internal_token
    )


@lru_cache(maxsize=1)
def get_retrieval_service() -> RetrievalService:
    return RetrievalService(get_embedder())


# Per-module DB-session seam. Deliberately a distinct callable from the other
# services' `db_session` wrappers (agent/api/deps, agent/auth/deps): each is its
# own `dependency_overrides` key, so a test overriding one doesn't silently
# affect another. They all delegate to the shared `session_dependency`.
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    async for session in session_dependency():
        yield session


def get_corpus_store() -> CorpusStore | None:
    """`None` without S3 credentials — the admin list still works (read-only)."""
    return build_corpus_store_or_none()


def get_manifest_path() -> Path:
    return Path("corpus/manifest.yaml")


def get_agent_settings_path() -> Path:
    return settings.agent_settings_path


def get_job_manager(request: Request) -> JobManager:
    manager = getattr(request.app.state, "job_manager", None)
    if manager is None:  # pragma: no cover - admin disabled / app misconfigured
        raise RuntimeError("job manager is not initialised")
    return manager  # type: ignore[no-any-return]
