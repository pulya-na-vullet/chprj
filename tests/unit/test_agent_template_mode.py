"""Шаблонный режим ChatAgent: вход из витрины, привязка беседы, деградация.

Реальный ConversationStore поверх SQLite; LLM и templates-клиент — фейки.
"""

from collections.abc import AsyncIterator

import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from neurolegal.agent.chat.agent import ChatAgent
from neurolegal.agent.store.conversation_store import ConversationStore
from neurolegal.agent.store.models import Base
from neurolegal.agent.tools.templates_client import TemplatesClientError, TemplatesNotFoundError
from neurolegal.contracts import TemplateDetail, TemplateField

USER_ID = "u1"

DETAIL = TemplateDetail(
    slug="arenda-kvartiry",
    title="Аренда квартиры",
    category="Договоры",
    description="",
    field_count=2,
    fields=[
        TemplateField(name="landlord_fio", label="Арендодатель", hint="ФИО полностью"),
        TemplateField(name="rent", label="Плата", kind="money", required=False),
    ],
)


class _AskLLM:
    """Первый вызов — ask_user tool call; терминален, второго не будет."""

    async def stream(self, messages, tools):  # type: ignore[no-untyped-def]
        from neurolegal.agent.llm.types import ToolCallRequest

        yield ToolCallRequest(
            id="tc1",
            name="ask_user",
            arguments={"question": "Чьи реквизиты взять?", "options": ["Выбрать из «Файлов»"]},
        )


class _StageThenAskLLM:
    """Основной путь шаблонного флоу: сначала stage_template, следующим ходом
    ask_user — ровно так модель инструктирует note самой тулзы."""

    async def stream(self, messages, tools):  # type: ignore[no-untyped-def]
        from neurolegal.agent.llm.types import ToolCallRequest

        staged = any(m.name == "stage_template" for m in messages if m.role == "tool")
        if staged:
            yield ToolCallRequest(
                id="tc2",
                name="ask_user",
                arguments={"question": "Всё верно?", "options": ["Да, формируем"]},
            )
            return
        yield ToolCallRequest(
            id="tc1",
            name="stage_template",
            arguments={
                "template_slug": DETAIL.slug,
                "values": {"landlord_fio": "Иванов Иван Иванович"},
                "sources": {"landlord_fio": "user"},
            },
        )


class _CapLLM:
    """Запоминает system-промпт и спецификацию тулзов каждого вызова."""

    def __init__(self) -> None:
        self.system_prompts: list[str] = []
        self.tool_names: list[list[str]] = []

    async def stream(self, messages, tools):  # type: ignore[no-untyped-def]
        self.system_prompts.append(messages[0].content)
        self.tool_names.append([t.name for t in tools])
        from neurolegal.agent.llm.types import TextChunk

        yield TextChunk(text="ок")


class _FakeTemplatesClient:
    def __init__(self, fail_with: Exception | None = None) -> None:
        self.fail_with = fail_with

    async def get_template(self, slug: str) -> TemplateDetail:
        if self.fail_with:
            raise self.fail_with
        if slug != DETAIL.slug:
            raise TemplatesNotFoundError(slug)
        return DETAIL

    async def list_templates(self):  # type: ignore[no-untyped-def]
        return []

    async def render(self, slug, values):  # type: ignore[no-untyped-def]
        raise AssertionError("render не должен вызываться в этих тестах")


@pytest_asyncio.fixture
async def store() -> AsyncIterator[ConversationStore]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield ConversationStore(session)
    await engine.dispose()


def _agent(store: ConversationStore, llm: _CapLLM, client: _FakeTemplatesClient) -> ChatAgent:
    return ChatAgent(
        llm=llm,  # type: ignore[arg-type]
        rag_client=object(),  # type: ignore[arg-type]
        store=store,
        templates_client=client,  # type: ignore[arg-type]
    )


async def _run(agent: ChatAgent, conv: str, message: str, slug: str | None = None) -> None:
    async for _ in agent.run(conv, message, user_id=USER_ID, template_slug=slug):
        pass


async def test_template_slug_binds_conversation_and_exposes_tools(
    store: ConversationStore,
) -> None:
    llm = _CapLLM()
    agent = _agent(store, llm, _FakeTemplatesClient())
    conv = await store.create_conversation(USER_ID)
    await store.commit()

    await _run(agent, conv, "Хочу заполнить шаблон", slug=DETAIL.slug)

    prompt = llm.system_prompts[0]
    assert "Аренда квартиры" in prompt
    assert "landlord_fio" in prompt and "ФИО полностью" in prompt
    assert set(llm.tool_names[0]) == {
        "list_templates",
        "stage_template",
        "render_template",
        "ask_user",
    }
    draft = await store.get_template_draft(conv)
    assert draft is not None and draft.template_slug == DETAIL.slug
    assert draft.values == {}


async def test_active_draft_keeps_conversation_in_template_mode(
    store: ConversationStore,
) -> None:
    llm = _CapLLM()
    agent = _agent(store, llm, _FakeTemplatesClient())
    conv = await store.create_conversation(USER_ID)
    await store.commit()
    await store.bind_template(conv, DETAIL.slug, DETAIL.title)
    await store.commit()

    # обычное сообщение без слага и без legal-маркеров остаётся в шаблонном режиме
    await _run(agent, conv, "Иванов Иван Иванович")
    assert "stage_template" in llm.tool_names[0]
    assert "rag_search" not in llm.tool_names[0]


async def test_service_outage_degrades_to_honest_note(store: ConversationStore) -> None:
    llm = _CapLLM()
    agent = _agent(store, llm, _FakeTemplatesClient(fail_with=TemplatesClientError("down")))
    conv = await store.create_conversation(USER_ID)
    await store.commit()

    await _run(agent, conv, "Составь договор аренды", slug=DETAIL.slug)

    assert "недоступен" in llm.system_prompts[0]
    assert await store.get_template_draft(conv) is None  # привязка не создана


async def test_unpublished_template_gets_honest_note(store: ConversationStore) -> None:
    llm = _CapLLM()
    agent = _agent(store, llm, _FakeTemplatesClient())
    conv = await store.create_conversation(USER_ID)
    await store.commit()

    await _run(agent, conv, "Заполни", slug="unpublished-slug")

    assert "недоступен" in llm.system_prompts[0] or "снят" in llm.system_prompts[0]


async def test_template_ask_carries_template_flag(store: ConversationStore) -> None:
    from neurolegal.agent.chat.events import AskEvent

    agent = _agent(store, _AskLLM(), _FakeTemplatesClient())  # type: ignore[arg-type]
    conv = await store.create_conversation(USER_ID)
    await store.commit()

    events = [
        e async for e in agent.run(conv, "Заполним", user_id=USER_ID, template_slug=DETAIL.slug)
    ]
    ask = next(e for e in events if isinstance(e, AskEvent))
    assert ask.template is True
    assert ask.data["template"] is True
    # и на персистентном сообщении — переживает перезагрузку истории
    history = await store.load_history(conv, USER_ID)
    assert history[-1].ask is not None and history[-1].ask["template"] is True


async def test_stage_then_ask_persists_summary_card(store: ConversationStore) -> None:
    """T-0143: ask_user терминален — карточка сводки, показанная в этом же
    ходе, обязана уехать на сохранённое сообщение, иначе после перезагрузки
    истории пользователь видит вопрос без сводки, которую подтверждает."""
    from neurolegal.agent.chat.events import TemplateDraftEvent

    agent = _agent(store, _StageThenAskLLM(), _FakeTemplatesClient())  # type: ignore[arg-type]
    conv = await store.create_conversation(USER_ID)
    await store.commit()

    events = [
        e async for e in agent.run(conv, "Заполним", user_id=USER_ID, template_slug=DETAIL.slug)
    ]
    assert any(isinstance(e, TemplateDraftEvent) for e in events)

    history = await store.load_history(conv, USER_ID)
    last = history[-1]
    assert last.ask is not None and last.ask["template"] is True
    assert last.template_draft is not None
    assert last.template_draft["template"] == {"slug": DETAIL.slug, "title": DETAIL.title}


async def test_non_template_ask_has_no_template_flag(store: ConversationStore) -> None:
    from neurolegal.agent.chat.events import AskEvent

    agent = _agent(store, _AskLLM(), _FakeTemplatesClient())  # type: ignore[arg-type]
    conv = await store.create_conversation(USER_ID)
    await store.commit()

    # обычный юридический ход (без слага и черновика)
    events = [e async for e in agent.run(conv, "Какая ответственность по 152-ФЗ?", user_id=USER_ID)]
    ask = next(e for e in events if isinstance(e, AskEvent))
    assert ask.template is False
    history = await store.load_history(conv, USER_ID)
    assert history[-1].ask is not None and history[-1].ask["template"] is False
