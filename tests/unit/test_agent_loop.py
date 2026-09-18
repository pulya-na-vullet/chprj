import asyncio
from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from neurolegal.agent.chat.agent import ChatAgent, ConversationNotFound
from neurolegal.agent.chat.answers import CAP_NOTE, NO_BASIS_NOTE, SEARCH_UNAVAILABLE_NOTE
from neurolegal.agent.chat.events import (
    CitationsEvent,
    DeltaEvent,
    DoneEvent,
    ReasoningEvent,
    ResetDeltaEvent,
    ToolCallEvent,
    ToolResultEvent,
)
from neurolegal.agent.chat.intent import Intent
from neurolegal.agent.llm.types import LLMEvent, ReasoningChunk, TextChunk, ToolCallRequest
from neurolegal.agent.store.conversation_store import ConversationStore
from neurolegal.agent.store.models import Base
from neurolegal.agent.tools.rag_client import RagClientError
from neurolegal.contracts import RagSearchSettings, SearchedArticle, ToolsSettings

USER_ID = "u1"


async def _collect(gen):  # type: ignore[no-untyped-def]
    return [e async for e in gen]


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
    """Replays a scripted list of event-lists, one per stream() call."""

    def __init__(self, scripted: list[list[LLMEvent]]) -> None:
        self._scripted = scripted
        self.calls = 0

    async def stream(self, messages, tools):  # type: ignore[no-untyped-def]
        events = self._scripted[self.calls]
        self.calls += 1
        for e in events:
            yield e


class _StopMidStreamLLM:
    """Ставит `stop` после заданного текстового чанка — имитация клика по стопу."""

    def __init__(self, stop: asyncio.Event, chunks: list[str], set_after: int) -> None:
        self._stop = stop
        self._chunks = chunks
        self._set_after = set_after

    async def stream(self, messages, tools):  # type: ignore[no-untyped-def]
        for i, text in enumerate(self._chunks):
            yield TextChunk(text=text)
            if i + 1 == self._set_after:
                self._stop.set()
                # даём циклу _iter_until_stop шанс увидеть событие
                await asyncio.sleep(0)


class _FakeRag:
    def __init__(self, articles: list[SearchedArticle]) -> None:
        self._articles = articles
        self.last_acts: list[str] | None = None
        self.last_min_score: float | None = None
        self.search_calls = 0

    async def search(self, query, *, acts=None, limit=8, min_score=None):  # type: ignore[no-untyped-def]
        self.search_calls += 1
        self.last_acts = acts
        self.last_min_score = min_score
        return self._articles


@pytest_asyncio.fixture
async def store() -> AsyncIterator[ConversationStore]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = async_sessionmaker(engine, expire_on_commit=False)
    async with sm() as session:
        yield ConversationStore(session)
    await engine.dispose()


@pytest.mark.asyncio
async def test_tool_call_then_answer(store: ConversationStore) -> None:
    conv_id = await store.create_conversation(USER_ID)
    await store.commit()
    llm = _FakeLLM(
        [
            [ToolCallRequest(id="c1", name="rag_search", arguments={"query": "налог"})],
            [TextChunk(text="Согласно "), TextChunk(text="ВК РФ ст. 3...")],
        ]
    )
    agent = ChatAgent(llm=llm, rag_client=_FakeRag([_article("3")]), store=store)

    events = [e async for e in agent.run(conv_id, "Что такое налог?", user_id=USER_ID)]

    assert any(isinstance(e, ToolCallEvent) for e in events)
    assert "".join(e.text for e in events if isinstance(e, DeltaEvent)) == (
        "Согласно ВК РФ ст. 3..."
    )
    citations = [e for e in events if isinstance(e, CitationsEvent)]
    assert len(citations) == 1
    assert citations[0].articles[0]["number"] == "3"
    assert isinstance(events[-1], DoneEvent)

    history = await store.load_history(conv_id, USER_ID)
    assert [m.role for m in history] == ["user", "assistant"]
    assert history[1].content == "Согласно ВК РФ ст. 3..."
    assert history[1].citations is not None


@pytest.mark.asyncio
async def test_direct_answer_without_tool(store: ConversationStore) -> None:
    conv_id = await store.create_conversation(USER_ID)
    await store.commit()
    llm = _FakeLLM([[TextChunk(text="В корпусе нет основания для ответа.")]])
    agent = ChatAgent(llm=llm, rag_client=_FakeRag([]), store=store)

    events = [e async for e in agent.run(conv_id, "Привет", user_id=USER_ID)]

    assert not any(isinstance(e, ToolCallEvent) for e in events)
    citations = [e for e in events if isinstance(e, CitationsEvent)]
    assert citations[0].articles == []
    assert isinstance(events[-1], DoneEvent)


@pytest.mark.asyncio
async def test_reasoning_streamed_but_not_persisted(store: ConversationStore) -> None:
    conv_id = await store.create_conversation(USER_ID)
    await store.commit()
    llm = _FakeLLM([[ReasoningChunk(text="Это приветствие. "), TextChunk(text="Привет!")]])
    agent = ChatAgent(llm=llm, rag_client=_FakeRag([]), store=store)

    events = [e async for e in agent.run(conv_id, "Привет", user_id=USER_ID)]

    # Reasoning surfaces as its own event, ahead of the visible answer.
    assert [e.text for e in events if isinstance(e, ReasoningEvent)] == ["Это приветствие. "]
    assert "".join(e.text for e in events if isinstance(e, DeltaEvent)) == "Привет!"

    # The stored answer must contain only the content, never the reasoning.
    history = await store.load_history(conv_id, USER_ID)
    assert history[1].content == "Привет!"


@pytest.mark.asyncio
async def test_max_tool_iterations_cap(store: ConversationStore) -> None:
    conv_id = await store.create_conversation(USER_ID)
    await store.commit()
    # Every LLM turn asks for another tool call — never a final answer.
    forever_tool = [[ToolCallRequest(id="c", name="rag_search", arguments={"query": "x"})]]
    llm = _FakeLLM(forever_tool * 10)
    agent = ChatAgent(
        llm=llm, rag_client=_FakeRag([_article("1")]), store=store, max_tool_iterations=3
    )

    events = [e async for e in agent.run(conv_id, "вопрос", user_id=USER_ID)]

    assert llm.calls == 3
    deltas = "".join(e.text for e in events if isinstance(e, DeltaEvent))
    assert "не удалось" in deltas.lower()
    assert isinstance(events[-1], DoneEvent)

    # T-0102, пункт 6: нота обязана попасть не только в SSE, но и в историю.
    # Тест смотрел только дельты, поэтому «нота ушла в поток, но в БД пустой
    # ответ» проходило незамеченным — в беседе оставался пустой пузырь.
    history = await store.load_history(conv_id, USER_ID)
    assert history[1].content == CAP_NOTE


@pytest.mark.asyncio
async def test_history_replayed_into_messages(store: ConversationStore) -> None:
    conv_id = await store.create_conversation(USER_ID)
    await store.append_message(conv_id, USER_ID, "user", "первый вопрос")
    await store.append_message(conv_id, USER_ID, "assistant", "первый ответ")
    await store.commit()
    captured: list[list[object]] = []

    class _CapturingLLM(_FakeLLM):
        async def stream(self, messages, tools):  # type: ignore[no-untyped-def]
            captured.append([m.role for m in messages])
            async for e in super().stream(messages, tools):
                yield e

    llm = _CapturingLLM([[TextChunk(text="второй ответ")]])
    agent = ChatAgent(llm=llm, rag_client=_FakeRag([]), store=store)
    _ = [e async for e in agent.run(conv_id, "второй вопрос", user_id=USER_ID)]

    # system + prior user/assistant + new user
    assert captured[0] == ["system", "user", "assistant", "user"]


@pytest.mark.asyncio
async def test_profile_note_appended_to_system_prompt(store: ConversationStore) -> None:
    """T-0128: профильный блок доезжает до системного сообщения, не
    вытесняя базовые правила (цитирование «ст. <номер> <акт>» остаётся)."""
    conv_id = await store.create_conversation(USER_ID)
    captured_system: list[str] = []

    class _CapturingLLM(_FakeLLM):
        async def stream(self, messages, tools):  # type: ignore[no-untyped-def]
            captured_system.append(messages[0].content)
            async for e in super().stream(messages, tools):
                yield e

    note = "О пользователе: Денис, использует сервис для бизнеса."
    llm = _CapturingLLM([[TextChunk(text="ответ")]])
    agent = ChatAgent(llm=llm, rag_client=_FakeRag([]), store=store)
    _ = [
        e
        async for e in agent.run(
            conv_id, "Каков срок исковой давности?", user_id=USER_ID, profile_note=note
        )
    ]

    assert note in captured_system[0]
    assert "ст. <номер> <акт>" in captured_system[0].lower()


@pytest.mark.asyncio
async def test_no_profile_note_leaves_system_prompt_unchanged(store: ConversationStore) -> None:
    conv_id = await store.create_conversation(USER_ID)
    captured_system: list[str] = []

    class _CapturingLLM(_FakeLLM):
        async def stream(self, messages, tools):  # type: ignore[no-untyped-def]
            captured_system.append(messages[0].content)
            async for e in super().stream(messages, tools):
                yield e

    llm = _CapturingLLM([[TextChunk(text="ответ")]])
    agent = ChatAgent(llm=llm, rag_client=_FakeRag([]), store=store)
    _ = [e async for e in agent.run(conv_id, "Каков срок исковой давности?", user_id=USER_ID)]

    assert "О пользователе" not in captured_system[0]


@pytest.mark.asyncio
async def test_unknown_conversation_raises(store: ConversationStore) -> None:
    agent = ChatAgent(llm=_FakeLLM([]), rag_client=_FakeRag([]), store=store)
    with pytest.raises(ConversationNotFound):
        await agent.ensure_conversation("does-not-exist", USER_ID)


@pytest.mark.asyncio
async def test_ensure_conversation_creates_new(store: ConversationStore) -> None:
    agent = ChatAgent(llm=_FakeLLM([]), rag_client=_FakeRag([]), store=store)
    conv_id, is_new = await agent.ensure_conversation(None, USER_ID)
    assert is_new is True
    assert await store.conversation_exists(conv_id, USER_ID)


@pytest.mark.asyncio
async def test_selected_acts_forced_onto_search(store: ConversationStore) -> None:
    conv_id = await store.create_conversation(USER_ID)
    await store.commit()
    llm = _FakeLLM(
        [
            [ToolCallRequest(id="c1", name="rag_search", arguments={"query": "налог"})],
            [TextChunk(text="ВК РФ ст. 3")],
        ]
    )
    rag = _FakeRag([_article("3")])
    agent = ChatAgent(llm=llm, rag_client=rag, store=store)

    _ = [e async for e in agent.run(conv_id, "вопрос", acts=["ГК РФ"], user_id=USER_ID)]

    assert rag.last_acts == ["ГК РФ"]


@pytest.mark.asyncio
async def test_tool_result_event_emitted_with_found_numbers(store: ConversationStore) -> None:
    conv_id = await store.create_conversation(USER_ID)
    await store.commit()
    llm = _FakeLLM(
        [
            [ToolCallRequest(id="c1", name="rag_search", arguments={"query": "налог"})],
            [TextChunk(text="ответ")],
        ]
    )
    agent = ChatAgent(llm=llm, rag_client=_FakeRag([_article("3"), _article("5")]), store=store)

    events = [e async for e in agent.run(conv_id, "вопрос", user_id=USER_ID)]

    results = [e for e in events if isinstance(e, ToolResultEvent)]
    assert len(results) == 1
    assert results[0].found == [
        {"act": "ВК РФ", "number": "3"},
        {"act": "ВК РФ", "number": "5"},
    ]


@pytest.mark.asyncio
async def test_citations_include_full_text(store: ConversationStore) -> None:
    conv_id = await store.create_conversation(USER_ID)
    await store.commit()
    llm = _FakeLLM(
        [
            [ToolCallRequest(id="c1", name="rag_search", arguments={"query": "q"})],
            [TextChunk(text="ответ")],
        ]
    )
    agent = ChatAgent(llm=llm, rag_client=_FakeRag([_article("3")]), store=store)

    events = [e async for e in agent.run(conv_id, "вопрос", user_id=USER_ID)]
    citations = next(e for e in events if isinstance(e, CitationsEvent))
    assert citations.articles[0]["full_text"] == "текст"


class _SequenceRag:
    """Отдаёт свою порцию статей на каждый вызов и записывает переданные acts.

    Нужен для сценария из ДВУХ поисков в одном ходе: и фильтр актов, и
    накопление цитат ломаются именно на втором вызове, но до T-0102 такого
    сценария не было ни одного.
    """

    def __init__(self, batches: list[list[SearchedArticle]]) -> None:
        self._batches = batches
        self.acts_per_call: list[list[str] | None] = []
        self.queries: list[str] = []

    async def search(self, query, *, acts=None, limit=8, min_score=None):  # type: ignore[no-untyped-def]
        self.acts_per_call.append(acts)
        self.queries.append(query)
        index = min(len(self.queries) - 1, len(self._batches) - 1)
        return self._batches[index]


class _CapturingLLM(_FakeLLM):
    """_FakeLLM, запоминающий выданный на каждый запрос набор инструментов."""

    def __init__(self, scripted):  # type: ignore[no-untyped-def]
        super().__init__(scripted)
        self.seen_tools: list[list[str]] = []

    async def stream(self, messages, tools):  # type: ignore[no-untyped-def]
        self.seen_tools.append([t.name for t in tools])
        async for e in super().stream(messages, tools):
            yield e


class _FakeRouter:
    def __init__(self, intent: Intent) -> None:
        self._intent = intent
        self.calls = 0

    def __call__(self, message: str) -> Intent:
        self.calls += 1
        return self._intent


@pytest.mark.asyncio
async def test_text_task_intent_skips_rag_and_citations(store: ConversationStore) -> None:
    conv_id = await store.create_conversation(USER_ID)
    await store.commit()
    rag = _FakeRag([_article("3")])
    llm = _FakeLLM([[TextChunk(text="Готовый текст")]])
    agent = ChatAgent(
        llm=llm,
        rag_client=rag,
        store=store,
        classify_intent=_FakeRouter(Intent.TEXT_TASK),
    )

    events = [e async for e in agent.run(conv_id, "Перефразируй: ...", user_id=USER_ID)]

    assert rag.search_calls == 0  # rag never invoked
    assert not any(isinstance(e, ToolCallEvent) for e in events)
    citations = [e for e in events if isinstance(e, CitationsEvent)]
    assert citations[0].articles == []


@pytest.mark.asyncio
async def test_smalltalk_intent_skips_rag_and_citations(store: ConversationStore) -> None:
    conv_id = await store.create_conversation(USER_ID)
    await store.commit()
    rag = _FakeRag([_article("3")])
    llm = _FakeLLM([[TextChunk(text="Привет! Я юридический ассистент.")]])
    agent = ChatAgent(
        llm=llm, rag_client=rag, store=store, classify_intent=_FakeRouter(Intent.SMALLTALK)
    )

    events = [e async for e in agent.run(conv_id, "Привет", user_id=USER_ID)]

    assert rag.search_calls == 0  # rag never invoked
    citations = [e for e in events if isinstance(e, CitationsEvent)]
    assert citations[0].articles == []


@pytest.mark.asyncio
async def test_smalltalk_gets_no_tools_at_all(store: ConversationStore) -> None:
    """Экспозиция инструментов, не факт их неиспользования (T-0102, пункт 3).

    Существующий test_smalltalk_intent_skips_rag_and_citations вакуумен:
    фейковый LLM в нём инструментов и не просит, поэтому мутация «smalltalk
    получает весь registry» проходила незамеченной. Здесь проверяется
    именно то, что модели ВЫДАЛИ на приветствие: пустой список.
    """
    conv_id = await store.create_conversation(USER_ID)
    await store.commit()
    llm = _CapturingLLM([[TextChunk(text="Привет!")]])
    agent = ChatAgent(
        llm=llm,
        rag_client=_FakeRag([_article("3")]),
        store=store,
        classify_intent=_FakeRouter(Intent.SMALLTALK),
    )

    await _collect(agent.run(conv_id, "Привет", user_id=USER_ID))

    # ни исследовательских тулзов, ни ask_user
    assert llm.seen_tools == [[]]


@pytest.mark.asyncio
async def test_legal_gets_the_research_tools(store: ConversationStore) -> None:
    """Обратная сторона того же инварианта: LEGAL обязан видеть rag_search."""
    conv_id = await store.create_conversation(USER_ID)
    await store.commit()
    llm = _CapturingLLM([[TextChunk(text="ответ")]])
    agent = ChatAgent(
        llm=llm,
        rag_client=_FakeRag([_article("3")]),
        store=store,
        classify_intent=_FakeRouter(Intent.LEGAL),
    )

    await _collect(agent.run(conv_id, "Что говорит ВК РФ?", user_id=USER_ID))

    assert "rag_search" in llm.seen_tools[0]


@pytest.mark.asyncio
async def test_two_searches_keep_acts_filter_and_accumulate_citations(
    store: ConversationStore,
) -> None:
    """Два УСПЕШНЫХ rag_search в разных итерациях одного хода (T-0102, п.4-5).

    Такого сценария в наборе не было ни одного, и на нём ломаются сразу два
    инварианта: фильтр актов проверялся только для первого поиска, и цитаты
    второго поиска затирали цитаты первого (если добавить articles_seen.clear()).
    """
    conv_id = await store.create_conversation(USER_ID)
    await store.commit()
    llm = _FakeLLM(
        [
            [ToolCallRequest(id="c1", name="rag_search", arguments={"query": "первый"})],
            [ToolCallRequest(id="c2", name="rag_search", arguments={"query": "второй"})],
            [TextChunk(text="ст. 3 и ст. 5 ВК РФ")],
        ]
    )
    rag = _SequenceRag([[_article("3")], [_article("5")]])
    agent = ChatAgent(llm=llm, rag_client=rag, store=store)

    events = await _collect(agent.run(conv_id, "вопрос", acts=["ГК РФ"], user_id=USER_ID))

    # Фильтр актов держится на КАЖДОМ поиске хода, не только на первом.
    assert rag.acts_per_call == [["ГК РФ"], ["ГК РФ"]]

    # Цитаты накапливаются: статья первого поиска не вытесняется вторым.
    citations = [e for e in events if isinstance(e, CitationsEvent)]
    assert sorted(c["number"] for c in citations[0].articles) == ["3", "5"]

    history = await store.load_history(conv_id, USER_ID)
    stored = history[1].citations or []
    assert sorted(str(c["number"]) for c in stored) == ["3", "5"]


@pytest.mark.asyncio
async def test_legal_intent_keeps_existing_behaviour(store: ConversationStore) -> None:
    conv_id = await store.create_conversation(USER_ID)
    await store.commit()
    llm = _FakeLLM(
        [
            [ToolCallRequest(id="c1", name="rag_search", arguments={"query": "налог"})],
            [TextChunk(text="ВК РФ ст. 3")],
        ]
    )
    agent = ChatAgent(
        llm=llm,
        rag_client=_FakeRag([_article("3")]),
        store=store,
        classify_intent=_FakeRouter(Intent.LEGAL),
    )

    events = [e async for e in agent.run(conv_id, "Что говорит ВК РФ?", user_id=USER_ID)]
    assert any(isinstance(e, ToolCallEvent) for e in events)


@pytest.mark.asyncio
async def test_reset_delta_emitted_when_text_precedes_tool_call(store: ConversationStore) -> None:
    conv_id = await store.create_conversation(USER_ID)
    await store.commit()
    # First LLM turn: streams visible text, THEN asks for a tool. The agent
    # must tell the frontend to discard that text before showing the tool result.
    llm = _FakeLLM(
        [
            [
                TextChunk(text="Сейчас поищу..."),
                ToolCallRequest(id="c1", name="rag_search", arguments={"query": "налог"}),
            ],
            [TextChunk(text="Финальный ответ")],
        ]
    )
    agent = ChatAgent(
        llm=llm,
        rag_client=_FakeRag([_article("3")]),
        store=store,
        classify_intent=_FakeRouter(Intent.LEGAL),
    )

    events = [e async for e in agent.run(conv_id, "вопрос", user_id=USER_ID)]

    delta_texts = [e for e in events if isinstance(e, DeltaEvent)]
    reset_idx = next(i for i, e in enumerate(events) if isinstance(e, ResetDeltaEvent))
    pre_reset = [e for e in events[:reset_idx] if isinstance(e, DeltaEvent)]
    post_reset = [e for e in events[reset_idx + 1 :] if isinstance(e, DeltaEvent)]
    assert [e.text for e in pre_reset] == ["Сейчас поищу..."]
    assert "".join(e.text for e in post_reset) == "Финальный ответ"
    assert len(delta_texts) == 2

    # Stored history must contain only the final answer.
    history = await store.load_history(conv_id, USER_ID)
    assert history[1].content == "Финальный ответ"


@pytest.mark.asyncio
async def test_legal_intent_no_rag_call_overrides_streamed_text(
    store: ConversationStore,
) -> None:
    """If the model ignores the system prompt and streams a direct legal answer
    without calling rag_search, the agent overrides it with NO_BASIS_NOTE.

    The frontend draft is cleared via reset_delta first so the user doesn't
    see the hallucinated answer flash on-screen."""

    conv_id = await store.create_conversation(USER_ID)
    await store.commit()
    # LLM streams text directly, never calls a tool.
    llm = _FakeLLM([[TextChunk(text="Согласно ст. 1 ГК РФ, гражданское право...")]])
    agent = ChatAgent(
        llm=llm,
        rag_client=_FakeRag([]),
        store=store,
        classify_intent=_FakeRouter(Intent.LEGAL),
    )

    events = [e async for e in agent.run(conv_id, "Что такое договор?", user_id=USER_ID)]

    # The discarded text appears as DeltaEvent, then ResetDeltaEvent, then
    # NO_BASIS_NOTE as the final DeltaEvent.
    deltas = [e for e in events if isinstance(e, DeltaEvent)]
    assert len(deltas) == 2
    reset_idx = next(i for i, e in enumerate(events) if isinstance(e, ResetDeltaEvent))
    pre = [e for e in events[:reset_idx] if isinstance(e, DeltaEvent)]
    post = [e for e in events[reset_idx + 1 :] if isinstance(e, DeltaEvent)]
    assert pre[0].text == "Согласно ст. 1 ГК РФ, гражданское право..."
    assert post[0].text == NO_BASIS_NOTE

    # Stored history contains only NO_BASIS_NOTE.
    history = await store.load_history(conv_id, USER_ID)
    assert history[1].content == NO_BASIS_NOTE

    # Citations are empty (no articles_seen).
    citations = next(e for e in events if isinstance(e, CitationsEvent))
    assert citations.articles == []


class _DownRag:
    """RAG client that always fails, as during an outage."""

    async def search(self, query, *, acts=None, limit=8, min_score=None):  # type: ignore[no-untyped-def]
        raise RagClientError("down")


@pytest.mark.asyncio
async def test_rag_outage_reports_search_unavailable_not_no_basis(
    store: ConversationStore,
) -> None:
    """A failed search must never be presented as 'no relevant norms exist'."""
    conv_id = await store.create_conversation(USER_ID)
    await store.commit()
    llm = _FakeLLM(
        [
            [ToolCallRequest(id="c1", name="rag_search", arguments={"query": "налог"})],
            [TextChunk(text="Не могу найти основание.")],
        ]
    )
    agent = ChatAgent(
        llm=llm,
        rag_client=_DownRag(),
        store=store,
        classify_intent=_FakeRouter(Intent.LEGAL),
    )

    events = [e async for e in agent.run(conv_id, "Что такое договор?", user_id=USER_ID)]

    deltas = [e.text for e in events if isinstance(e, DeltaEvent)]
    assert deltas[-1] == SEARCH_UNAVAILABLE_NOTE
    assert NO_BASIS_NOTE not in deltas
    history = await store.load_history(conv_id, USER_ID)
    assert history[1].content == SEARCH_UNAVAILABLE_NOTE


@pytest.mark.asyncio
async def test_rag_outage_on_iteration_cap_reports_search_unavailable(
    store: ConversationStore,
) -> None:
    conv_id = await store.create_conversation(USER_ID)
    await store.commit()
    forever_tool = [[ToolCallRequest(id="c", name="rag_search", arguments={"query": "x"})]]
    llm = _FakeLLM(forever_tool * 10)
    agent = ChatAgent(llm=llm, rag_client=_DownRag(), store=store, max_tool_iterations=3)

    events = [e async for e in agent.run(conv_id, "вопрос", user_id=USER_ID)]

    deltas = [e.text for e in events if isinstance(e, DeltaEvent)]
    assert deltas[-1] == SEARCH_UNAVAILABLE_NOTE


@pytest.mark.asyncio
async def test_agent_passes_none_min_score_when_setting_is_zero(
    store: ConversationStore,
) -> None:
    """RagSearchSettings.min_score=0.0 (the default) means "I have no floor
    configured" — the agent must send None so the RAG service can apply its
    own deployment setting. Sending 0.0 would silently override."""
    conv_id = await store.create_conversation(USER_ID)
    await store.commit()
    rag = _FakeRag([_article("3")])
    llm = _FakeLLM(
        [
            [ToolCallRequest(id="c1", name="rag_search", arguments={"query": "налог"})],
            [TextChunk(text="ответ")],
        ]
    )
    agent = ChatAgent(llm=llm, rag_client=rag, store=store)

    _ = [e async for e in agent.run(conv_id, "вопрос", user_id=USER_ID)]

    assert rag.last_min_score is None


@pytest.mark.asyncio
async def test_agent_passes_configured_min_score_when_set(
    store: ConversationStore,
) -> None:
    """When RagSearchSettings.min_score is configured non-zero, the agent ships
    it as an explicit override of the RAG-side default."""
    conv_id = await store.create_conversation(USER_ID)
    await store.commit()
    rag = _FakeRag([_article("3")])
    llm = _FakeLLM(
        [
            [ToolCallRequest(id="c1", name="rag_search", arguments={"query": "налог"})],
            [TextChunk(text="ответ")],
        ]
    )
    agent = ChatAgent(
        llm=llm,
        rag_client=rag,
        store=store,
        tools=ToolsSettings(rag_search=RagSearchSettings(min_score=0.07)),
    )

    _ = [e async for e in agent.run(conv_id, "вопрос", user_id=USER_ID)]

    assert rag.last_min_score == 0.07


@pytest.mark.asyncio
async def test_stop_mid_stream_persists_partial(store: ConversationStore) -> None:
    conv_id = await store.create_conversation(USER_ID)
    await store.commit()
    stop = asyncio.Event()
    llm = _StopMidStreamLLM(stop, ["Часть 1. ", "Часть 2. ", "Хвост не дойдёт."], set_after=2)
    agent = ChatAgent(llm=llm, rag_client=_FakeRag([]), store=store)

    events = [e async for e in agent.run(conv_id, "Привет", user_id=USER_ID, stop=stop)]

    done = events[-1]
    assert isinstance(done, DoneEvent)
    assert done.stopped is True
    history = await store.load_history(conv_id, USER_ID)
    assert history[-1].role == "assistant"
    assert history[-1].stopped is True
    assert history[-1].content.startswith("Часть 1. ")
    assert "Хвост" not in history[-1].content


@pytest.mark.asyncio
async def test_stop_before_any_text_persists_nothing(store: ConversationStore) -> None:
    conv_id = await store.create_conversation(USER_ID)
    await store.commit()
    stop = asyncio.Event()
    stop.set()  # стоп до первого чанка
    llm = _FakeLLM([[TextChunk(text="не должно дойти")]])
    agent = ChatAgent(llm=llm, rag_client=_FakeRag([]), store=store)

    events = [e async for e in agent.run(conv_id, "Привет", user_id=USER_ID, stop=stop)]

    done = events[-1]
    assert isinstance(done, DoneEvent)
    assert done.stopped is True
    assert done.message_id is None
    history = await store.load_history(conv_id, USER_ID)
    assert [m.role for m in history] == ["user"]  # только вопрос


@pytest.mark.asyncio
async def test_stop_skips_no_basis_override(store: ConversationStore) -> None:
    """LEGAL-ход без статей + стоп: частичный текст не заменяется нотой "нет основания"."""
    conv_id = await store.create_conversation(USER_ID)
    await store.commit()
    stop = asyncio.Event()
    llm = _StopMidStreamLLM(stop, ["Начало ответа. ", "Ещё."], set_after=1)
    agent = ChatAgent(
        llm=llm,
        rag_client=_FakeRag([]),
        store=store,
        classify_intent=lambda _: Intent.LEGAL,
    )

    _ = [e async for e in agent.run(conv_id, "Что говорит закон?", user_id=USER_ID, stop=stop)]

    history = await store.load_history(conv_id, USER_ID)
    assert history[-1].content.startswith("Начало ответа.")
    assert NO_BASIS_NOTE not in history[-1].content


@pytest.mark.asyncio
async def test_stop_during_tool_call(store: ConversationStore) -> None:
    """Стоп во время долгого tool-вызова: не ждать RAG, ничего не персистить."""
    conv_id = await store.create_conversation(USER_ID)
    await store.commit()
    stop = asyncio.Event()

    class _SlowRag:
        async def search(self, query, *, acts=None, limit=8, min_score=None):  # type: ignore[no-untyped-def]
            stop.set()
            await asyncio.sleep(30)  # стоп должен сработать раньше
            return []

    llm = _FakeLLM([[ToolCallRequest(id="c1", name="rag_search", arguments={"query": "x"})]])
    agent = ChatAgent(
        llm=llm, rag_client=_SlowRag(), store=store, classify_intent=lambda _: Intent.LEGAL
    )

    events = await asyncio.wait_for(
        _collect(agent.run(conv_id, "вопрос", user_id=USER_ID, stop=stop)), timeout=5
    )
    done = events[-1]
    assert isinstance(done, DoneEvent)
    assert done.stopped is True
    assert done.message_id is None


@pytest.mark.asyncio
async def test_iter_until_stop_survives_consumer_cancellation() -> None:
    """Обрыв клиента (sse-starlette cancel scope) отменяет потребителя, пока
    next_task ещё внутри генератора. finally обязан сначала погасить
    next_task и только потом aclose() — иначе RuntimeError
    «aclose(): asynchronous generator is already running» (наблюдалось
    вживую при disconnect во время LLM-вызова)."""
    from neurolegal.agent.chat.agent import _iter_until_stop

    stop = asyncio.Event()
    closed = asyncio.Event()

    async def slow_source() -> AsyncIterator[int]:
        try:
            await asyncio.sleep(30)
            yield 1
        finally:
            closed.set()

    async def consume() -> None:
        async for _ in _iter_until_stop(slow_source(), stop):
            pass

    task = asyncio.create_task(consume())
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert closed.is_set()  # источник корректно закрыт, без RuntimeError


@pytest.mark.asyncio
async def test_ask_user_call_terminates_turn_with_ask_event(store: ConversationStore) -> None:
    conv_id = await store.create_conversation(USER_ID)
    await store.commit()
    llm = _FakeLLM(
        [
            [
                ToolCallRequest(
                    id="a1",
                    name="ask_user",
                    arguments={"question": "Для кого письмо?", "options": ["Клиенту", "Суду"]},
                )
            ]
        ]
    )
    agent = ChatAgent(llm=llm, rag_client=_FakeRag([]), store=store)

    events = await _collect(agent.run(conv_id, "перепиши претензию", user_id=USER_ID))

    from neurolegal.agent.chat.events import AskEvent

    asks = [e for e in events if isinstance(e, AskEvent)]
    assert len(asks) == 1
    assert asks[0].kind == "ask_user"
    assert asks[0].options == ["Клиенту", "Суду"]
    # вопрос — не «инструмент» в ленте: ToolCallEvent не эмитится
    assert not any(isinstance(e, ToolCallEvent) for e in events)
    done = events[-1]
    assert isinstance(done, DoneEvent) and done.message_id is not None
    assert llm.calls == 1  # ход завершён, второй итерации нет

    history = await store.load_history(conv_id, USER_ID)
    assert history[-1].role == "assistant"
    assert history[-1].content == "Для кого письмо?"
    assert history[-1].ask == {
        "kind": "ask_user",
        "question": "Для кого письмо?",
        "options": ["Клиенту", "Суду"],
        "document_id": None,
        "playbook_id": None,
        "role": None,
        "error": None,
        "template": False,
    }


@pytest.mark.asyncio
async def test_ask_user_after_streamed_text_resets_draft(store: ConversationStore) -> None:
    conv_id = await store.create_conversation(USER_ID)
    await store.commit()
    llm = _FakeLLM(
        [
            [
                TextChunk(text="Сейчас уточню... "),
                ToolCallRequest(
                    id="a1", name="ask_user", arguments={"question": "Какой тон письма?"}
                ),
            ]
        ]
    )
    agent = ChatAgent(llm=llm, rag_client=_FakeRag([]), store=store)

    events = await _collect(agent.run(conv_id, "перепиши претензию", user_id=USER_ID))

    assert any(isinstance(e, ResetDeltaEvent) for e in events)
    history = await store.load_history(conv_id, USER_ID)
    assert history[-1].content == "Какой тон письма?"


@pytest.mark.asyncio
async def test_ask_user_invalid_args_returns_error_and_continues(store: ConversationStore) -> None:
    conv_id = await store.create_conversation(USER_ID)
    await store.commit()
    llm = _FakeLLM(
        [
            [ToolCallRequest(id="a1", name="ask_user", arguments={})],
            [TextChunk(text="Готовый текст")],
        ]
    )
    agent = ChatAgent(llm=llm, rag_client=_FakeRag([]), store=store)

    events = await _collect(agent.run(conv_id, "перепиши претензию", user_id=USER_ID))

    from neurolegal.agent.chat.events import AskEvent

    assert not any(isinstance(e, AskEvent) for e in events)
    assert llm.calls == 2  # ошибка ушла модели tool-результатом, цикл продолжился
    history = await store.load_history(conv_id, USER_ID)
    assert history[-1].content == "Готовый текст"


@pytest.mark.asyncio
async def test_ask_user_exposed_by_intent(store: ConversationStore) -> None:
    """LEGAL и TEXT_TASK видят тулзу и промпт-ноту; SMALLTALK — нет."""

    class _CapturingLLM(_FakeLLM):
        def __init__(self, scripted):  # type: ignore[no-untyped-def]
            super().__init__(scripted)
            self.seen_tools: list[list[str]] = []
            self.seen_system: list[str] = []

        async def stream(self, messages, tools):  # type: ignore[no-untyped-def]
            self.seen_tools.append([t.name for t in tools])
            self.seen_system.append(messages[0].content or "")
            async for e in super().stream(messages, tools):
                yield e

    for text, expected in [
        ("Какой штраф за парковку?", True),  # LEGAL
        ("перепиши: привет", True),  # TEXT_TASK
        ("Привет!", False),  # SMALLTALK
    ]:
        conv_id = await store.create_conversation(USER_ID)
        await store.commit()
        llm = _CapturingLLM([[TextChunk(text="ок")]])
        agent = ChatAgent(llm=llm, rag_client=_FakeRag([_article("1")]), store=store)
        await _collect(agent.run(conv_id, text, user_id=USER_ID))
        assert ("ask_user" in llm.seen_tools[0]) is expected, text
        assert ("ask_user" in llm.seen_system[0]) is expected, text


@pytest.mark.asyncio
async def test_pending_ask_user_does_not_trigger_review_interception(
    store: ConversationStore,
) -> None:
    """Ответ на ask_user — обычный следующий ход, не review-команда."""
    conv_id = await store.create_conversation(USER_ID)
    await store.append_message(
        conv_id,
        USER_ID,
        "assistant",
        "Для кого письмо?",
        ask={"kind": "ask_user", "question": "Для кого письмо?", "options": ["Клиенту"]},
    )
    await store.commit()
    llm = _FakeLLM([[TextChunk(text="Письмо для клиента: ...")]])
    agent = ChatAgent(llm=llm, rag_client=_FakeRag([]), store=store)

    events = await _collect(agent.run(conv_id, "перепиши для клиента", user_id=USER_ID))

    assert llm.calls == 1  # обычный ход: LLM вызван, run_review не перехватил
    assert isinstance(events[-1], DoneEvent)
    history = await store.load_history(conv_id, USER_ID)
    assert history[-1].content == "Письмо для клиента: ..."
