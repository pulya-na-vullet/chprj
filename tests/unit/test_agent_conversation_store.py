import asyncio
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from neurolegal.agent.store.conversation_store import ConversationStore
from neurolegal.agent.store.models import Base, MessageRow

USER_A = "user-a"
USER_B = "user-b"


@pytest_asyncio.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    # Shared in-memory SQLite (StaticPool keeps the connection alive across
    # sessions so they all see the same schema/data).
    from sqlalchemy.pool import StaticPool

    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def store(engine: AsyncEngine) -> AsyncIterator[ConversationStore]:
    sm = async_sessionmaker(engine, expire_on_commit=False)
    async with sm() as session:
        yield ConversationStore(session)


@pytest.mark.asyncio
async def test_create_and_exists(store: ConversationStore) -> None:
    conv_id = await store.create_conversation(USER_A)
    await store.commit()
    assert await store.conversation_exists(conv_id, USER_A) is True
    assert await store.conversation_exists("missing", USER_A) is False


@pytest.mark.asyncio
async def test_append_assigns_sequential_ordinals(store: ConversationStore) -> None:
    conv_id = await store.create_conversation(USER_A)
    await store.append_message(conv_id, USER_A, "user", "вопрос 1")
    await store.append_message(
        conv_id, USER_A, "assistant", "ответ 1", citations=[{"act": "ВК РФ"}]
    )
    await store.append_message(conv_id, USER_A, "user", "вопрос 2")
    await store.commit()

    history = await store.load_history(conv_id, USER_A)
    assert [m.role for m in history] == ["user", "assistant", "user"]
    assert [m.content for m in history] == ["вопрос 1", "ответ 1", "вопрос 2"]
    assert history[1].citations == [{"act": "ВК РФ"}]
    assert history[0].citations is None


@pytest.mark.asyncio
async def test_append_returns_message_id(store: ConversationStore) -> None:
    conv_id = await store.create_conversation(USER_A)
    msg_id = await store.append_message(conv_id, USER_A, "user", "привет")
    assert isinstance(msg_id, str) and len(msg_id) == 36


@pytest.mark.asyncio
async def test_list_conversations_titles_from_first_message(store: ConversationStore) -> None:
    a = await store.create_conversation(USER_A)
    await store.append_message(a, USER_A, "user", "Как защитить логотип?")
    await store.append_message(a, USER_A, "assistant", "ответ")
    b = await store.create_conversation(USER_A)
    await store.append_message(b, USER_A, "user", "x" * 80)
    await store.commit()

    items = await store.list_conversations(USER_A)
    by_id = {c.id: c for c in items}
    assert by_id[a].title == "Как защитить логотип?"
    assert by_id[b].title == "x" * 60 + "…"
    # newest first
    assert next(c.id for c in items) == b


@pytest.mark.asyncio
async def test_list_conversations_empty_conversation_gets_placeholder_title(
    store: ConversationStore,
) -> None:
    await store.create_conversation(USER_A)
    await store.commit()
    items = await store.list_conversations(USER_A)
    assert items[0].title == "Новый чат"


@pytest.mark.asyncio
async def test_delete_conversation_removes_messages(store: ConversationStore) -> None:
    c = await store.create_conversation(USER_A)
    await store.append_message(c, USER_A, "user", "вопрос")
    await store.commit()

    assert await store.delete_conversation(c, USER_A) is True
    await store.commit()
    assert await store.conversation_exists(c, USER_A) is False
    assert await store.load_history(c, USER_A) == []
    assert await store.delete_conversation("missing", USER_A) is False


@pytest.mark.asyncio
async def test_load_history_exposes_created_at(store: ConversationStore) -> None:
    c = await store.create_conversation(USER_A)
    await store.append_message(c, USER_A, "user", "вопрос")
    await store.commit()
    msg = (await store.load_history(c, USER_A))[0]
    assert msg.created_at is not None


@pytest.mark.asyncio
async def test_list_conversations_orders_by_last_activity(store: ConversationStore) -> None:
    a = await store.create_conversation(USER_A)
    await store.append_message(a, USER_A, "user", "первый")
    b = await store.create_conversation(USER_A)
    await store.append_message(b, USER_A, "user", "второй")
    await store.commit()
    # b is newest so far
    assert (await store.list_conversations(USER_A))[0].id == b
    # new activity on a should push it to the top
    await store.append_message(a, USER_A, "user", "ещё про a")
    await store.commit()
    assert (await store.list_conversations(USER_A))[0].id == a


@pytest.mark.asyncio
async def test_append_and_load_web_sources(store: ConversationStore) -> None:
    conv_id = await store.create_conversation(USER_A)
    web_src = [{"url": "https://e.gov", "title": "T", "snippet": None}]
    await store.append_message(
        conv_id, USER_A, "assistant", "ответ", citations=None, web_sources=web_src
    )
    await store.commit()

    history = await store.load_history(conv_id, USER_A)
    assert len(history) == 1
    assert history[0].web_sources == web_src
    assert history[0].citations is None


@pytest.mark.asyncio
async def test_concurrent_appends_get_distinct_ordinals(
    engine: AsyncEngine,
) -> None:
    """Two appends in flight at once must not collide on (conversation_id, ordinal).

    The previous implementation read `count(*)` then inserted, which two
    concurrent turns can both observe as the same N. The atomic `next_ordinal`
    update closes that hole.

    Uses one session per task (SQLAlchemy sessions are not safe for concurrent
    use) so the concurrency exercised is genuine DB-level concurrency."""

    sm = async_sessionmaker(engine, expire_on_commit=False)
    async with sm() as setup_session:
        setup_store = ConversationStore(setup_session)
        conv_id = await setup_store.create_conversation(USER_A)
        await setup_store.commit()

    async def append(i: int) -> None:
        async with sm() as session:
            await ConversationStore(session).append_message(conv_id, USER_A, "user", f"msg-{i:02d}")
            await session.commit()

    await asyncio.gather(*(append(i) for i in range(8)))

    async with sm() as verify_session:
        history = await ConversationStore(verify_session).load_history(conv_id, USER_A)
        rows = (
            (
                await verify_session.execute(
                    select(MessageRow).where(MessageRow.conversation_id == conv_id)
                )
            )
            .scalars()
            .all()
        )
    assert len(history) == 8
    # Each ordinal is distinct → all 8 messages were persisted; the
    # (conversation_id, ordinal) unique constraint would have errored on a collision.
    ordinals = sorted(r.ordinal for r in rows)
    assert ordinals == list(range(8))
    contents = sorted(m.content for m in history)
    assert contents == [f"msg-{i:02d}" for i in range(8)]


# -- user scoping: cross-user isolation -----------------------------------


@pytest.mark.asyncio
async def test_create_conversation_sets_owner(store: ConversationStore) -> None:
    conv_id = await store.create_conversation(USER_A)
    await store.commit()
    assert await store.conversation_exists(conv_id, USER_A) is True
    assert await store.conversation_exists(conv_id, USER_B) is False


@pytest.mark.asyncio
async def test_list_conversations_only_returns_own(store: ConversationStore) -> None:
    a = await store.create_conversation(USER_A)
    b = await store.create_conversation(USER_B)
    await store.commit()
    assert [c.id for c in await store.list_conversations(USER_A)] == [a]
    assert [c.id for c in await store.list_conversations(USER_B)] == [b]


@pytest.mark.asyncio
async def test_load_history_of_other_users_conversation_is_empty(
    store: ConversationStore,
) -> None:
    conv_id = await store.create_conversation(USER_A)
    await store.append_message(conv_id, USER_A, "user", "вопрос")
    await store.commit()
    assert await store.load_history(conv_id, USER_B) == []
    assert await store.load_history(conv_id, USER_A) != []


@pytest.mark.asyncio
async def test_append_message_to_other_users_conversation_raises(
    store: ConversationStore,
) -> None:
    conv_id = await store.create_conversation(USER_A)
    await store.commit()
    with pytest.raises(LookupError):
        await store.append_message(conv_id, USER_B, "user", "чужой вопрос")


@pytest.mark.asyncio
async def test_delete_other_users_conversation_returns_false(
    store: ConversationStore,
) -> None:
    conv_id = await store.create_conversation(USER_A)
    await store.commit()
    assert await store.delete_conversation(conv_id, USER_B) is False
    assert await store.conversation_exists(conv_id, USER_A) is True


@pytest.mark.asyncio
async def test_append_message_stopped_flag(store: ConversationStore) -> None:
    conv_id = await store.create_conversation(USER_A)
    await store.commit()
    await store.append_message(conv_id, USER_A, "user", "вопрос")
    await store.append_message(conv_id, USER_A, "assistant", "частичный", stopped=True)
    await store.commit()

    history = await store.load_history(conv_id, USER_A)
    assert [m.stopped for m in history] == [False, True]


@pytest.mark.asyncio
async def test_preview_from_last_assistant_message(store: ConversationStore) -> None:
    """T-0014: превью = очищенный от markdown хвост последнего ответа."""
    a = await store.create_conversation(USER_A)
    await store.append_message(a, USER_A, "user", "вопрос")
    await store.append_message(a, USER_A, "assistant", "первый ответ")
    await store.append_message(a, USER_A, "user", "ещё вопрос")
    await store.append_message(
        a, USER_A, "assistant", "## Итог\nСогласно **ст. 395 ГК РФ** проценты\nначисляются."
    )
    await store.commit()

    items = await store.list_conversations(USER_A)
    assert items[0].preview == "Итог Согласно ст. 395 ГК РФ проценты начисляются."


@pytest.mark.asyncio
async def test_preview_truncated_to_120(store: ConversationStore) -> None:
    a = await store.create_conversation(USER_A)
    await store.append_message(a, USER_A, "user", "вопрос")
    await store.append_message(a, USER_A, "assistant", "я" * 200)
    await store.commit()
    preview = (await store.list_conversations(USER_A))[0].preview
    assert preview == "я" * 120 + "…"


@pytest.mark.asyncio
async def test_preview_review_takes_first_two_lines(store: ConversationStore) -> None:
    a = await store.create_conversation(USER_A)
    await store.append_message(a, USER_A, "user", "проверь договор")
    await store.append_message(
        a,
        USER_A,
        "assistant",
        "# Проверка по плейбуку Поставка\nРиски: high 2, medium 3, low 1\n— [high] Что-то",
        review={"document_id": "d1"},
    )
    await store.commit()
    preview = (await store.list_conversations(USER_A))[0].preview
    assert preview == "Проверка по плейбуку Поставка — Риски: high 2, medium 3, low 1"


@pytest.mark.asyncio
async def test_preview_stopped_prefix(store: ConversationStore) -> None:
    a = await store.create_conversation(USER_A)
    await store.append_message(a, USER_A, "user", "вопрос")
    await store.append_message(a, USER_A, "assistant", "частичный ответ", stopped=True)
    await store.commit()
    preview = (await store.list_conversations(USER_A))[0].preview
    assert preview == "Остановлено · частичный ответ"


@pytest.mark.asyncio
async def test_preview_none_without_assistant_answer(store: ConversationStore) -> None:
    a = await store.create_conversation(USER_A)
    await store.append_message(a, USER_A, "user", "вопрос без ответа")
    b = await store.create_conversation(USER_A)
    await store.commit()
    items = {c.id: c for c in await store.list_conversations(USER_A)}
    assert items[a].preview is None
    assert items[b].preview is None


# -- ask (T-0046) -----------------------------------------------------------


@pytest.mark.asyncio
async def test_append_and_load_ask(store: ConversationStore) -> None:
    conv_id = await store.create_conversation(USER_A)
    ask = {"kind": "review_role", "question": "Вы на стороне поставщика или покупателя?"}
    await store.append_message(conv_id, USER_A, "assistant", "уточните роль", ask=ask)
    await store.commit()

    history = await store.load_history(conv_id, USER_A)
    assert history[0].ask == ask


@pytest.mark.asyncio
async def test_append_without_ask_reads_back_none(store: ConversationStore) -> None:
    conv_id = await store.create_conversation(USER_A)
    await store.append_message(conv_id, USER_A, "assistant", "обычный ответ")
    await store.commit()

    history = await store.load_history(conv_id, USER_A)
    assert history[0].ask is None


@pytest.mark.asyncio
async def test_last_message_returns_latest_by_ordinal(store: ConversationStore) -> None:
    conv_id = await store.create_conversation(USER_A)
    await store.append_message(conv_id, USER_A, "user", "вопрос 1")
    await store.append_message(conv_id, USER_A, "assistant", "ответ 1")
    await store.append_message(conv_id, USER_A, "user", "вопрос 2")
    await store.commit()

    last = await store.last_message(conv_id, USER_A)
    assert last is not None
    assert last.content == "вопрос 2"


@pytest.mark.asyncio
async def test_last_message_wrong_owner_returns_none(store: ConversationStore) -> None:
    conv_id = await store.create_conversation(USER_A)
    await store.append_message(conv_id, USER_A, "user", "вопрос")
    await store.commit()

    assert await store.last_message(conv_id, USER_B) is None


@pytest.mark.asyncio
async def test_last_message_empty_conversation_returns_none(store: ConversationStore) -> None:
    conv_id = await store.create_conversation(USER_A)
    await store.commit()

    assert await store.last_message(conv_id, USER_A) is None


# -- T-0048: свод review-прогонов для GET /reviews ---------------------------

_REPORT = {
    "playbook_id": "supply_ru",
    "playbook_name": "Договор поставки",
    "document_id": "d1",
    "risks": [{"level": "high"}],
    "coverage": [],
    "disclaimer": "…",
    "role": "Покупатель",
    "summary": None,
}


@pytest.mark.asyncio
async def test_list_review_runs_returns_reports_and_failures_newest_first(
    store: ConversationStore,
) -> None:
    conv1 = await store.create_conversation(USER_A)
    await store.append_message(conv1, USER_A, "user", "проверь")
    m_done = await store.append_message(conv1, USER_A, "assistant", "отчёт", review=_REPORT)
    conv2 = await store.create_conversation(USER_A)
    await store.append_message(conv2, USER_A, "user", "проверь ещё")
    m_failed = await store.append_message(
        conv2,
        USER_A,
        "assistant",
        "не удалось",
        ask={"kind": "review_failed", "document_id": "d2", "playbook_id": "lease_ru"},
    )
    # обычные сообщения и вопрос роли в свод не попадают
    conv3 = await store.create_conversation(USER_A)
    await store.append_message(conv3, USER_A, "assistant", "обычный ответ")
    await store.append_message(
        conv3, USER_A, "assistant", "кто вы?", ask={"kind": "review_role", "question": "?"}
    )
    await store.commit()

    runs = await store.list_review_runs(USER_A)
    assert [(r.message_id, r.conversation_id) for r in runs] == [
        (m_failed, conv2),
        (m_done, conv1),
    ]
    assert runs[0].review is None and runs[0].ask is not None
    assert runs[1].review == _REPORT and runs[1].ask is None


@pytest.mark.asyncio
async def test_list_review_runs_scoped_to_owner(store: ConversationStore) -> None:
    conv = await store.create_conversation(USER_A)
    await store.append_message(conv, USER_A, "assistant", "отчёт", review=_REPORT)
    await store.commit()

    assert await store.list_review_runs(USER_B) == []


# -- T-0049: экспорт review-отчёта -----------------------------------------------


@pytest.mark.asyncio
async def test_get_review_report_returns_done_run(store: ConversationStore) -> None:
    conv = await store.create_conversation(USER_A)
    msg_id = await store.append_message(
        conv, USER_A, "assistant", "отчёт", review={"playbook_id": "supply_ru"}
    )
    await store.commit()

    run = await store.get_review_report(msg_id, USER_A)
    assert run is not None
    assert run.message_id == msg_id
    assert run.conversation_id == conv
    assert run.review == {"playbook_id": "supply_ru"}


@pytest.mark.asyncio
async def test_get_review_report_hides_foreign_and_non_review(
    store: ConversationStore,
) -> None:
    conv = await store.create_conversation(USER_A)
    plain_id = await store.append_message(conv, USER_A, "assistant", "просто ответ")
    review_id = await store.append_message(conv, USER_A, "assistant", "отчёт", review={"x": 1})
    failed_id = await store.append_message(
        conv, USER_A, "assistant", "", ask={"kind": "review_failed", "error": "boom"}
    )
    await store.commit()

    # JSON-'null' в review — это не отчёт (см. list_review_runs)
    assert await store.get_review_report(plain_id, USER_A) is None
    # сбойный прогон — не экспортируется
    assert await store.get_review_report(failed_id, USER_A) is None
    # чужой id неотличим от несуществующего
    assert await store.get_review_report(review_id, USER_B) is None
    assert await store.get_review_report("missing", USER_A) is None
