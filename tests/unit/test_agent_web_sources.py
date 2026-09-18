"""Tests for web_sources accumulation and emission in ChatAgent.

These tests verify:
1. When a tool handler returns web_sources, a WebSourcesEvent is emitted and
   the stored message carries web_sources.
2. Citations are emitted when legal-tool calls find articles.
3. Non-legal turns do not execute unexpected legal-tool calls.
"""

from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from neurolegal.agent.chat.agent import ChatAgent
from neurolegal.agent.chat.events import (
    CitationsEvent,
    WebSourcesEvent,
)
from neurolegal.agent.chat.intent import Intent
from neurolegal.agent.chat.tools.base import ToolContext, ToolOutcome
from neurolegal.agent.llm.types import LLMEvent, TextChunk, ToolCallRequest
from neurolegal.agent.store.conversation_store import ConversationStore
from neurolegal.agent.store.models import Base
from neurolegal.contracts import SearchedArticle, WebSource

USER_ID = "u1"

# ---------------------------------------------------------------------------
# Shared fakes (mirrors test_agent_loop.py style)
# ---------------------------------------------------------------------------


def _article(number: str) -> SearchedArticle:
    return SearchedArticle(
        article_id=str(uuid4()),
        act_short_name="ВК РФ",
        act_kind="codex",
        number=number,
        title="Заголовок",
        full_text="текст",
        matched_chunks=[],
        score=0.04,
    )


class _FakeLLM:
    def __init__(self, scripted: list[list[LLMEvent]]) -> None:
        self._scripted = scripted
        self.calls = 0

    async def stream(self, messages, tools):  # type: ignore[no-untyped-def]
        events = self._scripted[self.calls]
        self.calls += 1
        for e in events:
            yield e


class _FakeRag:
    def __init__(self, articles: list[SearchedArticle]) -> None:
        self._articles = articles
        self.search_calls = 0

    async def search(self, query, *, acts=None, limit=8, min_score=None):  # type: ignore[no-untyped-def]
        self.search_calls += 1
        return self._articles


class _FakeRouter:
    def __init__(self, intent: Intent) -> None:
        self._intent = intent

    def __call__(self, message: str) -> Intent:
        return self._intent


@pytest_asyncio.fixture
async def store() -> AsyncIterator[ConversationStore]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = async_sessionmaker(engine, expire_on_commit=False)
    async with sm() as session:
        yield ConversationStore(session)
    await engine.dispose()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_web_sources_event_emitted_and_persisted(
    store: ConversationStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When a tool handler returns web_sources, the agent must:
    - yield a WebSourcesEvent with those sources, and
    - persist them on the stored assistant message.
    """
    from neurolegal.agent.chat.tools import rag_search as rag_search_mod

    async def _stub_handle(arguments: dict[str, object], ctx: ToolContext) -> ToolOutcome:
        return ToolOutcome(
            tool_result="{}",
            web_sources=[WebSource(url="https://e.gov", title="Тестовый источник")],
        )

    # Patch before ChatAgent is constructed so build_registry captures the stub.
    monkeypatch.setattr(rag_search_mod, "handle_rag_search", _stub_handle)

    conv_id = await store.create_conversation(USER_ID)
    await store.commit()
    llm = _FakeLLM(
        [
            [ToolCallRequest(id="c1", name="rag_search", arguments={"query": "вопрос"})],
            [TextChunk(text="ответ")],
        ]
    )
    agent = ChatAgent(llm=llm, rag_client=_FakeRag([]), store=store)

    events = [e async for e in agent.run(conv_id, "вопрос", user_id=USER_ID)]

    # WebSourcesEvent must be emitted with the correct URL.
    web_events = [e for e in events if isinstance(e, WebSourcesEvent)]
    assert len(web_events) == 1
    assert web_events[0].sources[0]["url"] == "https://e.gov"
    assert web_events[0].sources[0]["title"] == "Тестовый источник"

    # The stored message must carry web_sources.
    history = await store.load_history(conv_id, USER_ID)
    assert history[1].web_sources is not None
    assert history[1].web_sources[0]["url"] == "https://e.gov"


@pytest.mark.asyncio
async def test_no_web_sources_event_when_none_returned(
    store: ConversationStore,
) -> None:
    """When no tool returns web_sources, no WebSourcesEvent is emitted."""
    conv_id = await store.create_conversation(USER_ID)
    await store.commit()
    llm = _FakeLLM(
        [
            [ToolCallRequest(id="c1", name="rag_search", arguments={"query": "налог"})],
            [TextChunk(text="ответ")],
        ]
    )
    agent = ChatAgent(llm=llm, rag_client=_FakeRag([_article("3")]), store=store)

    events = [e async for e in agent.run(conv_id, "вопрос", user_id=USER_ID)]

    assert not any(isinstance(e, WebSourcesEvent) for e in events)
    # But citations should still be present.
    citations = [e for e in events if isinstance(e, CitationsEvent)]
    assert len(citations) == 1
    assert citations[0].articles[0]["number"] == "3"


@pytest.mark.asyncio
async def test_non_legal_intent_does_not_execute_unexpected_rag_tool_call(
    store: ConversationStore,
) -> None:
    """Text tasks must not be able to create legal citations via RAG."""
    conv_id = await store.create_conversation(USER_ID)
    await store.commit()
    rag = _FakeRag([_article("3")])
    llm = _FakeLLM(
        [
            [ToolCallRequest(id="c1", name="rag_search", arguments={"query": "налог"})],
            [TextChunk(text="Готово")],
        ]
    )
    agent = ChatAgent(
        llm=llm,
        rag_client=rag,
        store=store,
        classify_intent=_FakeRouter(Intent.TEXT_TASK),
    )

    events = [e async for e in agent.run(conv_id, "Перефразируй: найди ст. 3", user_id=USER_ID)]

    assert rag.search_calls == 0
    citations = [e for e in events if isinstance(e, CitationsEvent)]
    assert len(citations) == 1
    assert citations[0].articles == []

    history = await store.load_history(conv_id, USER_ID)
    assert history[1].citations is None


@pytest.mark.asyncio
async def test_duplicate_web_sources_deduplicated_by_url(
    store: ConversationStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If two tool calls return the same URL, only one WebSource is stored."""
    from neurolegal.agent.chat.tools import rag_search as rag_search_mod

    call_count = 0

    async def _stub_handle(arguments: dict[str, object], ctx: ToolContext) -> ToolOutcome:
        nonlocal call_count
        call_count += 1
        return ToolOutcome(
            tool_result="{}",
            web_sources=[WebSource(url="https://e.gov", title=f"Call {call_count}")],
        )

    monkeypatch.setattr(rag_search_mod, "handle_rag_search", _stub_handle)

    conv_id = await store.create_conversation(USER_ID)
    await store.commit()
    # Two sequential tool calls both return the same URL.
    llm = _FakeLLM(
        [
            [
                ToolCallRequest(id="c1", name="rag_search", arguments={"query": "первый"}),
                ToolCallRequest(id="c2", name="rag_search", arguments={"query": "второй"}),
            ],
            [TextChunk(text="ответ")],
        ]
    )
    agent = ChatAgent(llm=llm, rag_client=_FakeRag([]), store=store)

    events = [e async for e in agent.run(conv_id, "вопрос", user_id=USER_ID)]

    web_events = [e for e in events if isinstance(e, WebSourcesEvent)]
    assert len(web_events) == 1
    # Second call overwrites the first (dict keyed by URL), so only one entry.
    assert len(web_events[0].sources) == 1
