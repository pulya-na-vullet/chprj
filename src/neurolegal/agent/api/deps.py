"""FastAPI dependency wiring for the agent API.

The LLM client and RagClient are process-wide singletons; the ConversationStore
is per-request because it wraps a per-request DB session.
"""

import secrets
from collections.abc import AsyncGenerator
from functools import lru_cache
from pathlib import Path
from typing import Annotated

from fastapi import Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from neurolegal.agent.chat.agent import ChatAgent
from neurolegal.agent.llm.client import ChatLLM, OpenRouterChatClient
from neurolegal.agent.review.playbook import Playbook, load_playbooks
from neurolegal.agent.store.conversation_store import ConversationStore
from neurolegal.agent.tools.documents_client import DocumentsClient
from neurolegal.agent.tools.rag_client import RagClient
from neurolegal.agent.tools.templates_client import AgentTemplatesClient
from neurolegal.contracts import AgentSettings
from neurolegal.core.agent_settings import load_agent_settings
from neurolegal.core.config import DEFAULT_REVIEW_CONCURRENCY, DEFAULT_REVIEW_MODEL, settings
from neurolegal.core.db import session_dependency

# T-0052: горячая перезагрузка настроек агента. Их пишет админ-карточка
# RAG-сервиса (agent_settings.yaml); агент раньше читал файл один раз
# (lru_cache) — смена «Модели/Параллельности проверки» молча требовала
# рестарта. Теперь файл перечитывается при изменении mtime; LLM-клиенты
# пересобираются только когда настройки реально сменились (кэш по identity
# объекта настроек — get_agent_settings возвращает один и тот же объект,
# пока файл не изменился).
_agent_settings_cache: tuple[float, AgentSettings] | None = None
_llm_cache: tuple[AgentSettings, ChatLLM] | None = None
_review_llm_cache: tuple[AgentSettings, ChatLLM] | None = None


def reset_settings_caches() -> None:
    """Обнуляет кэши настроек и LLM-клиентов (тестовый шов)."""
    global _agent_settings_cache, _llm_cache, _review_llm_cache
    _agent_settings_cache = None
    _llm_cache = None
    _review_llm_cache = None


def get_agent_settings() -> AgentSettings:
    global _agent_settings_cache
    try:
        mtime = Path(settings.agent_settings_path).stat().st_mtime
    except OSError:
        mtime = -1.0  # файла нет — кэшируем дефолты до появления файла
    cached = _agent_settings_cache
    if cached is not None and cached[0] == mtime:
        return cached[1]
    loaded = load_agent_settings(settings.agent_settings_path)
    _agent_settings_cache = (mtime, loaded)
    return loaded


def get_llm() -> ChatLLM:
    global _llm_cache
    s = get_agent_settings()
    if _llm_cache is not None and _llm_cache[0] is s:
        return _llm_cache[1]
    client: ChatLLM = OpenRouterChatClient(
        model=s.model,
        generation=s.generation,
        tool_choice=s.behavior.tool_choice,
    )
    _llm_cache = (s, client)
    return client


def effective_review_model() -> str:
    """Effective risk_review model: admin setting -> env `NEUROLEGAL_REVIEW_MODEL`
    -> built-in default. The review model is always defined."""
    s = get_agent_settings()
    return s.review.model or settings.review_model or DEFAULT_REVIEW_MODEL


def effective_review_concurrency() -> int:
    """Effective risk_review parallelism: admin setting -> env
    `NEUROLEGAL_REVIEW_CONCURRENCY` -> built-in default."""
    s = get_agent_settings()
    if s.review.concurrency is not None:
        return s.review.concurrency
    if settings.review_concurrency is not None:
        return settings.review_concurrency
    return DEFAULT_REVIEW_CONCURRENCY


def get_review_llm() -> ChatLLM:
    """Dedicated chat client for risk_review, on `effective_review_model()`.

    Always returns a client (T-0042) — the review model is always defined,
    even when neither the admin setting nor `NEUROLEGAL_REVIEW_MODEL` is set
    (falls back to `DEFAULT_REVIEW_MODEL`). Пересобирается при смене
    настроек (T-0052) — кэш по identity объекта настроек."""
    global _review_llm_cache
    s = get_agent_settings()
    if _review_llm_cache is not None and _review_llm_cache[0] is s:
        return _review_llm_cache[1]
    client: ChatLLM = OpenRouterChatClient(
        model=effective_review_model(),
        generation=s.generation,
        tool_choice=s.behavior.tool_choice,
    )
    _review_llm_cache = (s, client)
    return client


@lru_cache(maxsize=1)
def get_rag_client() -> RagClient:
    return RagClient(base_url=settings.rag_base_url)


# Per-module DB-session seam — a distinct callable from rag/api/deps and
# agent/auth/deps so each is its own `dependency_overrides` key (a test
# overriding one doesn't silently affect another). All delegate to the shared
# `session_dependency`.
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    async for session in session_dependency():
        yield session


async def verify_internal_token(
    x_internal_token: Annotated[str | None, Header()] = None,
) -> None:
    """Gate the internal `/admin/users*` routes on the agent<->RAG shared
    secret. Mirrors `neurolegal.documents.api.deps.verify_internal_token`:
    a no-op when NEUROLEGAL_INTERNAL_TOKEN isn't configured (local dev),
    otherwise every request must present a matching X-Internal-Token
    (constant-time compare). These routes are reached only by the RAG
    service's `agent_client` — never by the browser, so they deliberately
    don't sit behind `get_current_user`."""
    expected = settings.internal_token
    if expected is None:
        return
    if x_internal_token is None or not secrets.compare_digest(x_internal_token, expected):
        raise HTTPException(status_code=401, detail="invalid_internal_token")


def get_store(
    session: Annotated[AsyncSession, Depends(db_session)],
) -> ConversationStore:
    return ConversationStore(session)


@lru_cache(maxsize=1)
def get_documents_client() -> DocumentsClient:
    return DocumentsClient(
        base_url=settings.documents_base_url, internal_token=settings.internal_token
    )


@lru_cache(maxsize=1)
def get_templates_client() -> AgentTemplatesClient:
    return AgentTemplatesClient(base_url=settings.templates_base_url)


@lru_cache(maxsize=1)
def get_playbooks() -> dict[str, Playbook]:
    return load_playbooks(settings.playbooks_dir)


def get_chat_agent(
    store: Annotated[ConversationStore, Depends(get_store)],
    llm: Annotated[ChatLLM, Depends(get_llm)],
    rag_client: Annotated[RagClient, Depends(get_rag_client)],
) -> ChatAgent:
    s = get_agent_settings()
    return ChatAgent(
        llm=llm,
        rag_client=rag_client,
        store=store,
        behavior=s.behavior,
        tools=s.tools,
        tavily_api_key=settings.tavily_api_key,
        documents_client=get_documents_client(),
        playbooks=get_playbooks(),
        review_llm=get_review_llm(),
        review_concurrency=effective_review_concurrency(),
        templates_client=get_templates_client(),
    )
