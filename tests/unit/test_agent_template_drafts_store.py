"""Черновики шаблонов в ConversationStore: bind/upsert/rendered/каскад."""

from collections.abc import AsyncIterator

import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from neurolegal.agent.store.conversation_store import ConversationStore
from neurolegal.agent.store.models import Base

USER_ID = "u1"


@pytest_asyncio.fixture
async def store() -> AsyncIterator[ConversationStore]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield ConversationStore(session)
    await engine.dispose()


async def _conv(store: ConversationStore) -> str:
    conv = await store.create_conversation(USER_ID)
    await store.commit()
    return conv


async def test_bind_creates_empty_draft_and_respects_existing(store: ConversationStore) -> None:
    conv = await _conv(store)
    await store.bind_template(conv, "arenda", "Аренда")
    draft = await store.get_template_draft(conv)
    assert draft is not None and draft.values == {} and draft.rendered_at is None

    # значения выживают при повторном bind того же шаблона
    await store.upsert_template_draft(
        conv, slug="arenda", title="Аренда", values={"fio": "И."}, sources={"fio": "user"}
    )
    await store.bind_template(conv, "arenda", "Аренда")
    draft = await store.get_template_draft(conv)
    assert draft is not None and draft.values == {"fio": "И."}

    # bind другого шаблона очищает черновик
    await store.bind_template(conv, "uslugi", "Услуги")
    draft = await store.get_template_draft(conv)
    assert draft is not None and draft.template_slug == "uslugi" and draft.values == {}


async def test_upsert_overwrites_and_resets_rendered(store: ConversationStore) -> None:
    conv = await _conv(store)
    await store.upsert_template_draft(
        conv, slug="arenda", title="Аренда", values={"a": "1"}, sources={"a": "user"}
    )
    await store.mark_template_rendered(conv)
    draft = await store.get_template_draft(conv)
    assert draft is not None and draft.rendered_at is not None

    # новый stage сбрасывает rendered_at — беседа снова в активном заполнении
    await store.upsert_template_draft(
        conv, slug="arenda", title="Аренда", values={"a": "2"}, sources={"a": "user"}
    )
    draft = await store.get_template_draft(conv)
    assert draft is not None and draft.values == {"a": "2"} and draft.rendered_at is None


async def test_delete_conversation_drops_draft(store: ConversationStore) -> None:
    conv = await _conv(store)
    await store.bind_template(conv, "arenda", "Аренда")
    await store.commit()
    assert await store.delete_conversation(conv, USER_ID)
    await store.commit()
    assert await store.get_template_draft(conv) is None
