from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from neurolegal.agent.api.app import app
from neurolegal.agent.api.deps import get_store
from neurolegal.agent.auth.deps import get_current_user
from neurolegal.agent.store.conversation_store import ConversationStore
from neurolegal.agent.store.models import Base, UserRow

USER_ID = "u1"
OTHER_USER_ID = "u2"


@pytest_asyncio.fixture
async def store() -> AsyncIterator[ConversationStore]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = async_sessionmaker(engine, expire_on_commit=False)
    async with sm() as session:
        yield ConversationStore(session)
    await engine.dispose()


def _make_user(user_id: str) -> UserRow:
    return UserRow(
        id=user_id,
        email=f"{user_id}@example.com",
        password_hash="h",
        is_active=True,
        email_verified_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
    )


def _fake_user() -> UserRow:
    return _make_user(USER_ID)


def _client(store: ConversationStore, *, as_user: str = USER_ID) -> TestClient:
    app.dependency_overrides[get_store] = lambda: store
    app.dependency_overrides[get_current_user] = lambda: _make_user(as_user)
    return TestClient(app)


_CITATION = {
    "act_short_name": "ГК РФ",
    "kind": "codex",
    "number": "1477",
    "title": "Товарный знак",
    "full_text": "Товарным знаком признается обозначение...",
    "score": 0.04,
}


async def _seed(store: ConversationStore) -> str:
    conv = await store.create_conversation(USER_ID)
    await store.append_message(conv, USER_ID, "user", "Как защитить логотип?")
    await store.append_message(conv, USER_ID, "assistant", "ответ", citations=[_CITATION])
    await store.commit()
    return conv


def test_list_conversations(store: ConversationStore) -> None:
    import asyncio

    conv = asyncio.get_event_loop().run_until_complete(_seed(store))
    try:
        resp = _client(store).get("/conversations")
        assert resp.status_code == 200
        items = resp.json()["conversations"]
        assert items[0]["id"] == conv
        assert items[0]["title"] == "Как защитить логотип?"
        # T-0014: превью = итог последнего ответа ассистента
        assert items[0]["preview"] == "ответ"
    finally:
        app.dependency_overrides.clear()


def test_get_messages(store: ConversationStore) -> None:
    import asyncio

    conv = asyncio.get_event_loop().run_until_complete(_seed(store))
    try:
        resp = _client(store).get(f"/conversations/{conv}/messages")
        assert resp.status_code == 200
        msgs = resp.json()["messages"]
        assert [m["role"] for m in msgs] == ["user", "assistant"]
        assert msgs[1]["citations"] == [_CITATION]
        assert msgs[0]["created_at"]
    finally:
        app.dependency_overrides.clear()


def test_get_messages_returns_web_sources(store: ConversationStore) -> None:
    import asyncio

    web_sources = [{"url": "https://e.gov", "title": "Новость", "snippet": "текст"}]

    async def _seed_web() -> str:
        conv = await store.create_conversation(USER_ID)
        await store.append_message(conv, USER_ID, "assistant", "ответ", web_sources=web_sources)
        await store.commit()
        return conv

    conv = asyncio.get_event_loop().run_until_complete(_seed_web())
    try:
        resp = _client(store).get(f"/conversations/{conv}/messages")
        assert resp.status_code == 200
        assert resp.json()["messages"][0]["web_sources"] == web_sources
    finally:
        app.dependency_overrides.clear()


def test_get_messages_includes_stopped_field(store: ConversationStore) -> None:
    import asyncio

    async def _seed_with_stopped() -> str:
        conv = await store.create_conversation(USER_ID)
        await store.append_message(conv, USER_ID, "user", "Вопрос?")
        await store.append_message(conv, USER_ID, "assistant", "Ответ", stopped=True)
        await store.commit()
        return conv

    conv = asyncio.get_event_loop().run_until_complete(_seed_with_stopped())
    try:
        resp = _client(store).get(f"/conversations/{conv}/messages")
        assert resp.status_code == 200
        msgs = resp.json()["messages"]
        assert msgs[0]["stopped"] is False  # user message, not stopped
        assert msgs[1]["stopped"] is True  # assistant message, stopped
    finally:
        app.dependency_overrides.clear()


def test_get_messages_includes_ask_field(store: ConversationStore) -> None:
    import asyncio

    ask = {"kind": "review_role", "question": "Вы на стороне поставщика или покупателя?"}

    async def _seed_with_ask() -> str:
        conv = await store.create_conversation(USER_ID)
        await store.append_message(conv, USER_ID, "user", "Проверь договор")
        await store.append_message(conv, USER_ID, "assistant", "уточните роль", ask=ask)
        await store.commit()
        return conv

    conv = asyncio.get_event_loop().run_until_complete(_seed_with_ask())
    try:
        resp = _client(store).get(f"/conversations/{conv}/messages")
        assert resp.status_code == 200
        msgs = resp.json()["messages"]
        assert msgs[0]["ask"] is None
        # MessageOut.ask validates through MessageAsk, which fills in the
        # model's other optional fields — compare only what we set.
        assert msgs[1]["ask"]["kind"] == ask["kind"]
        assert msgs[1]["ask"]["question"] == ask["question"]
    finally:
        app.dependency_overrides.clear()


def test_get_messages_unknown_404(store: ConversationStore) -> None:
    try:
        resp = _client(store).get("/conversations/nope/messages")
        assert resp.status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_delete_conversation(store: ConversationStore) -> None:
    import asyncio

    conv = asyncio.get_event_loop().run_until_complete(_seed(store))
    try:
        client = _client(store)
        assert client.delete(f"/conversations/{conv}").status_code == 204
        assert client.delete(f"/conversations/{conv}").status_code == 404
    finally:
        app.dependency_overrides.clear()


# -- cross-user isolation at the route level --------------------------------


def test_list_conversations_excludes_other_users(store: ConversationStore) -> None:
    import asyncio

    conv = asyncio.get_event_loop().run_until_complete(_seed(store))
    try:
        own = _client(store, as_user=USER_ID).get("/conversations")
        assert [c["id"] for c in own.json()["conversations"]] == [conv]

        other = _client(store, as_user=OTHER_USER_ID).get("/conversations")
        assert other.json()["conversations"] == []
    finally:
        app.dependency_overrides.clear()


def test_get_messages_of_other_users_conversation_is_404(store: ConversationStore) -> None:
    import asyncio

    conv = asyncio.get_event_loop().run_until_complete(_seed(store))
    try:
        resp = _client(store, as_user=OTHER_USER_ID).get(f"/conversations/{conv}/messages")
        assert resp.status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_delete_other_users_conversation_is_404(store: ConversationStore) -> None:
    import asyncio

    conv = asyncio.get_event_loop().run_until_complete(_seed(store))
    try:
        resp = _client(store, as_user=OTHER_USER_ID).delete(f"/conversations/{conv}")
        assert resp.status_code == 404
        # still there for the real owner
        assert (
            _client(store, as_user=USER_ID).get(f"/conversations/{conv}/messages").status_code
            == 200
        )
    finally:
        app.dependency_overrides.clear()
