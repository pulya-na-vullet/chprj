"""AuthStore repository over users/auth_sessions — SQLite in-memory.

Mirrors the fixture pattern in tests/unit/test_agent_conversation_store.py.
"""

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from neurolegal.agent.auth.store import AuthStore
from neurolegal.agent.store.conversation_store import ConversationStore
from neurolegal.agent.store.models import Base, UserRow


@pytest_asyncio.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
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
async def store(engine: AsyncEngine) -> AsyncIterator[AuthStore]:
    sm = async_sessionmaker(engine, expire_on_commit=False)
    async with sm() as session:
        yield AuthStore(session)


@pytest.mark.asyncio
async def test_create_and_get_user_by_email(store: AuthStore) -> None:
    user = await store.create_user(email="a@example.com", password_hash="h")
    await store.commit()
    fetched = await store.get_user_by_email("a@example.com")
    assert fetched is not None
    assert fetched.id == user.id
    assert await store.get_user_by_email("missing@example.com") is None


@pytest.mark.asyncio
async def test_get_user_by_id(store: AuthStore) -> None:
    user = await store.create_user(email="a@example.com", password_hash="h")
    await store.commit()
    assert (await store.get_user_by_id(user.id)).id == user.id  # type: ignore[union-attr]
    assert await store.get_user_by_id("missing") is None


@pytest.mark.asyncio
async def test_set_password(store: AuthStore) -> None:
    user = await store.create_user(email="a@example.com", password_hash="old")
    await store.commit()
    await store.set_password(user.id, "new")
    await store.commit()
    fetched = await store.get_user_by_id(user.id)
    assert fetched is not None
    assert fetched.password_hash == "new"


@pytest.mark.asyncio
async def test_create_user_with_email_verified_at(store: AuthStore) -> None:
    """T-0026: registration activates the account at creation time."""
    when = datetime.now(UTC)
    user = await store.create_user(email="a@example.com", password_hash="h", email_verified_at=when)
    await store.commit()
    fetched = await store.get_user_by_id(user.id)
    assert fetched is not None
    assert fetched.email_verified_at is not None


@pytest.mark.asyncio
async def test_create_get_delete_session(store: AuthStore) -> None:
    user = await store.create_user(email="a@example.com", password_hash="h")
    await store.commit()
    expires = datetime.now(UTC) + timedelta(days=30)
    session_row = await store.create_session(user_id=user.id, token_hash="s1", expires_at=expires)
    await store.commit()

    fetched = await store.get_session_by_hash("s1")
    assert fetched is not None
    assert fetched.id == session_row.id

    deleted = await store.delete_session_by_hash("s1")
    await store.commit()
    assert deleted is True
    assert await store.get_session_by_hash("s1") is None
    assert await store.delete_session_by_hash("s1") is False


@pytest.mark.asyncio
async def test_touch_session_updates_last_seen_and_expiry(store: AuthStore) -> None:
    user = await store.create_user(email="a@example.com", password_hash="h")
    await store.commit()
    expires = datetime.now(UTC) + timedelta(days=30)
    session_row = await store.create_session(user_id=user.id, token_hash="s2", expires_at=expires)
    await store.commit()

    new_last_seen = datetime.now(UTC)
    new_expires = new_last_seen + timedelta(days=30)
    await store.touch_session(session_row.id, last_seen_at=new_last_seen, expires_at=new_expires)
    await store.commit()

    fetched = await store.get_session_by_hash("s2")
    assert fetched is not None
    # SQLite round-trips DateTime(timezone=True) as naive; strip tzinfo on
    # both sides so the comparison works regardless of backend.
    assert fetched.expires_at.replace(tzinfo=None, microsecond=0) == new_expires.replace(
        tzinfo=None, microsecond=0
    )


@pytest.mark.asyncio
async def test_delete_sessions_for_user_removes_all(store: AuthStore) -> None:
    user = await store.create_user(email="a@example.com", password_hash="h")
    await store.commit()
    expires = datetime.now(UTC) + timedelta(days=30)
    await store.create_session(user_id=user.id, token_hash="sa", expires_at=expires)
    await store.create_session(user_id=user.id, token_hash="sb", expires_at=expires)
    await store.commit()

    await store.delete_sessions_for_user(user.id)
    await store.commit()

    assert await store.get_session_by_hash("sa") is None
    assert await store.get_session_by_hash("sb") is None


@pytest.mark.asyncio
async def test_set_active_flips_flag_and_unknown_id_returns_none(store: AuthStore) -> None:
    user = await store.create_user(email="a@example.com", password_hash="h")
    await store.commit()
    assert user.is_active is True

    updated = await store.set_active(user.id, False)
    await store.commit()
    assert updated is not None
    assert updated.is_active is False
    fetched = await store.get_user_by_id(user.id)
    assert fetched is not None
    assert fetched.is_active is False

    assert await store.set_active("missing-id", False) is None


@pytest.mark.asyncio
async def test_update_user_profile_sets_only_given_fields(store: AuthStore) -> None:
    user = await store.create_user(email="p@example.com", password_hash="h")
    await store.commit()

    updated = await store.update_user_profile(
        user.id, {"first_name": "Ася", "tasks": ["law_questions", "files"]}
    )
    await store.commit()
    assert updated is not None
    assert updated.first_name == "Ася"
    assert updated.tasks == ["law_questions", "files"]
    assert updated.last_name is None

    # второй частичный апдейт не трогает ранее заполненные поля
    await store.update_user_profile(user.id, {"last_name": "Иванова"})
    await store.commit()
    fetched = await store.get_user_by_id(user.id)
    assert fetched is not None
    assert fetched.first_name == "Ася"
    assert fetched.last_name == "Иванова"


@pytest.mark.asyncio
async def test_update_user_profile_unknown_user_returns_none(store: AuthStore) -> None:
    assert await store.update_user_profile("missing-id", {"first_name": "X"}) is None


@pytest.mark.asyncio
async def test_update_user_profile_rejects_non_profile_field(store: AuthStore) -> None:
    """Гард от mass-assignment: только профильные колонки, никаких email/is_active."""
    user = await store.create_user(email="p@example.com", password_hash="h")
    await store.commit()
    with pytest.raises(ValueError):
        await store.update_user_profile(user.id, {"email": "evil@example.com"})


@pytest.mark.asyncio
async def test_count_conversations_for_user(engine: AsyncEngine) -> None:
    sm = async_sessionmaker(engine, expire_on_commit=False)
    async with sm() as session:
        user = UserRow(email="a@example.com", password_hash="h")
        session.add(user)
        await session.flush()
        convs = ConversationStore(session)
        await convs.create_conversation(user.id)
        await convs.create_conversation(user.id)
        await session.commit()

        auth = AuthStore(session)
        assert await auth.count_conversations(user.id) == 2
        assert await auth.count_conversations("missing-id") == 0


@pytest.mark.asyncio
async def test_list_users_with_conversation_counts_orders_newest_first(
    engine: AsyncEngine,
) -> None:
    sm = async_sessionmaker(engine, expire_on_commit=False)
    async with sm() as session:
        base = datetime.now(UTC)
        older = UserRow(
            email="older@example.com", password_hash="h", created_at=base - timedelta(days=1)
        )
        newer = UserRow(email="newer@example.com", password_hash="h", created_at=base)
        session.add_all([older, newer])
        await session.flush()
        convs = ConversationStore(session)
        await convs.create_conversation(older.id)
        await convs.create_conversation(older.id)
        await convs.create_conversation(newer.id)
        await session.commit()

        auth = AuthStore(session)
        rows = await auth.list_users_with_conversation_counts()

    assert [u.email for u, _ in rows] == ["newer@example.com", "older@example.com"]
    counts = {u.email: count for u, count in rows}
    assert counts == {"newer@example.com": 1, "older@example.com": 2}


@pytest.mark.asyncio
async def test_list_users_with_conversation_counts_zero_for_no_conversations(
    store: AuthStore,
) -> None:
    await store.create_user(email="lonely@example.com", password_hash="h")
    await store.commit()
    rows = await store.list_users_with_conversation_counts()
    assert rows == [(rows[0][0], 0)]
