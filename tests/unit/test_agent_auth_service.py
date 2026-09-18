"""AuthService business logic — SQLite in-memory store.

MVP without email verification (T-0026): register creates an active,
verified user and opens a session immediately; login never checks
verification. No mail is involved anywhere in the service.
"""

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from neurolegal.agent.auth import service as auth_service_module
from neurolegal.agent.auth.service import (
    SESSION_REFRESH_THRESHOLD,
    SESSION_TTL,
    AuthService,
    EmailTakenError,
    InvalidCredentialsError,
    UserNotFoundError,
)
from neurolegal.agent.auth.store import AuthStore
from neurolegal.agent.store.models import Base
from neurolegal.core.security import hash_token


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
async def service(engine: AsyncEngine) -> AsyncIterator[AuthService]:
    sm = async_sessionmaker(engine, expire_on_commit=False)
    async with sm() as session:
        yield AuthService(store=AuthStore(session))


@pytest.mark.asyncio
async def test_register_creates_active_verified_user_with_session(
    service: AuthService,
) -> None:
    result = await service.register("New@Example.com", "password123")

    assert result.user.email == "new@example.com"
    assert result.user.is_active is True
    assert result.user.email_verified_at is not None
    assert isinstance(result.session_token, str) and len(result.session_token) > 10

    # the session opened by register round-trips through get_current_user
    user = await service.get_current_user(result.session_token)
    assert user is not None
    assert user.email == "new@example.com"


@pytest.mark.asyncio
async def test_register_existing_email_raises_email_taken(service: AuthService) -> None:
    await service.register("dup@example.com", "password123")
    first_user = await service._store.get_user_by_email("dup@example.com")

    with pytest.raises(EmailTakenError):
        await service.register("dup@example.com", "different-password")

    second_user = await service._store.get_user_by_email("dup@example.com")
    assert second_user is not None
    assert first_user is not None
    assert second_user.id == first_user.id  # no new account


@pytest.mark.asyncio
async def test_register_concurrent_duplicate_email_raises_email_taken(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T-0028: register's check-then-act is not atomic. Simulate the race where
    the uniqueness check passes (another txn hadn't committed yet) but the
    INSERT then loses to the unique index — the IntegrityError must surface as
    EmailTakenError, not a 500, and the session must be left usable."""
    sm = async_sessionmaker(engine, expire_on_commit=False)
    async with sm() as seed_session:
        seed_store = AuthStore(seed_session)
        await seed_store.create_user(
            email="race@example.com",
            password_hash=auth_service_module.hash_password("password123"),
        )
        await seed_store.commit()

    async with sm() as session:
        store = AuthStore(session)
        svc = AuthService(store=store)

        async def racing_check(_email: str) -> None:
            return None  # the row isn't visible to this txn's check yet

        monkeypatch.setattr(store, "get_user_by_email", racing_check)

        with pytest.raises(EmailTakenError):
            await svc.register("race@example.com", "password123")

        # rollback left the session healthy — a follow-up query still works
        monkeypatch.undo()
        survivor = await store.get_user_by_email("race@example.com")
        assert survivor is not None


@pytest.mark.asyncio
async def test_login_unknown_email_raises_invalid_credentials(service: AuthService) -> None:
    with pytest.raises(InvalidCredentialsError):
        await service.login("nobody@example.com", "whatever")


@pytest.mark.asyncio
async def test_login_unknown_email_still_pays_argon2_cost(
    service: AuthService, monkeypatch: pytest.MonkeyPatch
) -> None:
    """I1: a missing account must not short-circuit past verify_password —
    otherwise response latency becomes an email-enumeration oracle."""
    calls: list[tuple[str, str]] = []
    original = auth_service_module.verify_password

    def spy(password: str, hashed: str) -> bool:
        calls.append((password, hashed))
        return original(password, hashed)

    monkeypatch.setattr(auth_service_module, "verify_password", spy)

    with pytest.raises(InvalidCredentialsError):
        await service.login("nobody@example.com", "whatever")

    assert len(calls) == 1
    assert calls[0][1] == auth_service_module._DUMMY_PASSWORD_HASH


@pytest.mark.asyncio
async def test_login_known_email_verifies_against_real_hash(
    service: AuthService, monkeypatch: pytest.MonkeyPatch
) -> None:
    await service.register("known@example.com", "password123")

    calls: list[tuple[str, str]] = []
    original = auth_service_module.verify_password

    def spy(password: str, hashed: str) -> bool:
        calls.append((password, hashed))
        return original(password, hashed)

    monkeypatch.setattr(auth_service_module, "verify_password", spy)

    await service.login("known@example.com", "password123")
    assert len(calls) == 1
    assert calls[0][1] != auth_service_module._DUMMY_PASSWORD_HASH


@pytest.mark.asyncio
async def test_login_wrong_password_raises_invalid_credentials(service: AuthService) -> None:
    await service.register("w@example.com", "correct-password")

    with pytest.raises(InvalidCredentialsError):
        await service.login("w@example.com", "wrong-password")


@pytest.mark.asyncio
async def test_login_ignores_email_verification_state(engine: AsyncEngine) -> None:
    """T-0026: verification is gone from the login path — a pre-scope-change
    user row with `email_verified_at IS NULL` must still be able to log in."""
    sm = async_sessionmaker(engine, expire_on_commit=False)
    async with sm() as session:
        store = AuthStore(session)
        svc = AuthService(store=store)
        await store.create_user(
            email="legacy@example.com",
            password_hash=auth_service_module.hash_password("password123"),
        )
        await store.commit()

        result = await svc.login("legacy@example.com", "password123")
        assert result.user.email == "legacy@example.com"


@pytest.mark.asyncio
async def test_login_inactive_user_raises_invalid_credentials(service: AuthService) -> None:
    await service.register("inactive@example.com", "password123")
    user = await service._store.get_user_by_email("inactive@example.com")
    assert user is not None
    user.is_active = False
    await service._store.commit()

    with pytest.raises(InvalidCredentialsError):
        await service.login("inactive@example.com", "password123")


@pytest.mark.asyncio
async def test_login_success_creates_session_and_returns_user(service: AuthService) -> None:
    await service.register("ok@example.com", "password123")

    result = await service.login("ok@example.com", "password123")
    assert result.user.email == "ok@example.com"
    assert isinstance(result.session_token, str) and len(result.session_token) > 10

    # the session round-trips through get_current_user
    user = await service.get_current_user(result.session_token)
    assert user is not None
    assert user.email == "ok@example.com"


@pytest.mark.asyncio
async def test_get_current_user_unknown_token_returns_none(service: AuthService) -> None:
    assert await service.get_current_user("garbage") is None


@pytest.mark.asyncio
async def test_get_current_user_expired_session_returns_none(engine: AsyncEngine) -> None:
    sm = async_sessionmaker(engine, expire_on_commit=False)
    async with sm() as session:
        store = AuthStore(session)
        svc = AuthService(store=store)
        user = await store.create_user(email="exp@example.com", password_hash="h")
        await store.commit()
        raw = "raw-session-token"
        await store.create_session(
            user_id=user.id,
            token_hash=hash_token(raw),
            expires_at=datetime.now(UTC) - timedelta(seconds=1),
        )
        await store.commit()
        assert await svc.get_current_user(raw) is None


@pytest.mark.asyncio
async def test_get_current_user_slides_expiry_after_threshold(engine: AsyncEngine) -> None:
    sm = async_sessionmaker(engine, expire_on_commit=False)
    async with sm() as session:
        store = AuthStore(session)
        svc = AuthService(store=store)
        user = await store.create_user(email="slide@example.com", password_hash="h")
        await store.commit()
        raw = "raw-slide-token"
        old_last_seen = datetime.now(UTC) - SESSION_REFRESH_THRESHOLD - timedelta(seconds=1)
        original_expiry = old_last_seen + SESSION_TTL
        session_row = await store.create_session(
            user_id=user.id, token_hash=hash_token(raw), expires_at=original_expiry
        )
        # backdate last_seen_at past the refresh threshold
        await store.touch_session(
            session_row.id, last_seen_at=old_last_seen, expires_at=original_expiry
        )
        await store.commit()

        fetched = await svc.get_current_user(raw)
        assert fetched is not None

        refreshed = await store.get_session_by_hash(hash_token(raw))
        assert refreshed is not None
        assert refreshed.expires_at.replace(tzinfo=None) > original_expiry.replace(tzinfo=None)


@pytest.mark.asyncio
async def test_get_current_user_does_not_slide_within_threshold(service: AuthService) -> None:
    result = await service.register("fresh@example.com", "password123")

    before = await service._store.get_session_by_hash(hash_token(result.session_token))
    assert before is not None
    await service.get_current_user(result.session_token)
    after = await service._store.get_session_by_hash(hash_token(result.session_token))
    assert after is not None
    assert before.expires_at == after.expires_at


@pytest.mark.asyncio
async def test_get_current_user_rejects_deactivated_user_with_live_session(
    service: AuthService,
) -> None:
    """Второй рубеж по is_active в самой сверке сессии (T-0101, пункт 4).

    Everywhere-logout живёт в `admin_patch_user`, но он не единственный путь
    снятия флага: операторский SQL, будущий CLI, гонка «логин ровно в момент
    деактивации». Поэтому деактивируем в обход сервиса — так проверяется
    именно проверка `not user.is_active` в `get_current_user`, не то, что
    сессии кто-то удалил заранее.
    """
    result = await service.register("deactivated@example.com", "password123")
    assert await service.get_current_user(result.session_token) is not None

    await service._store.set_active(result.user.id, False)
    await service._store.commit()
    # Сессия намеренно осталась живой.
    assert await service._store.get_session_by_hash(hash_token(result.session_token)) is not None

    assert await service.get_current_user(result.session_token) is None


@pytest.mark.asyncio
async def test_logout_removes_session(service: AuthService) -> None:
    result = await service.register("lo@example.com", "password123")

    await service.logout(result.session_token)
    assert await service.get_current_user(result.session_token) is None

    # logging out an already-gone session is a no-op, not an error
    await service.logout(result.session_token)


@pytest.mark.asyncio
async def test_admin_patch_deactivate_drops_all_sessions(service: AuthService) -> None:
    """T-0033: the everywhere-logout invariant now lives in the service, so a
    deactivation must drop every session regardless of the caller."""
    result = await service.register("d@example.com", "password123")
    user_id = result.user.id
    assert await service.get_current_user(result.session_token) is not None

    updated = await service.admin_patch_user(user_id, is_active=False)
    assert updated.is_active is False
    assert await service.get_current_user(result.session_token) is None


@pytest.mark.asyncio
async def test_admin_patch_new_password_rehashes_and_drops_sessions(service: AuthService) -> None:
    result = await service.register("p@example.com", "password123")
    user_id = result.user.id

    await service.admin_patch_user(user_id, new_password="operator-set-pw1")

    # old session gone, new password works, account stays active
    assert await service.get_current_user(result.session_token) is None
    login = await service.login("p@example.com", "operator-set-pw1")
    assert login.user.id == user_id


@pytest.mark.asyncio
async def test_admin_patch_activate_keeps_sessions(service: AuthService) -> None:
    """Activation is not a logout event — only deactivation and password change
    drop sessions, so an existing session survives an is_active=True patch."""
    result = await service.register("r@example.com", "password123")

    await service.admin_patch_user(result.user.id, is_active=True)
    assert await service.get_current_user(result.session_token) is not None


@pytest.mark.asyncio
async def test_admin_patch_unknown_user_raises(service: AuthService) -> None:
    with pytest.raises(UserNotFoundError):
        await service.admin_patch_user("does-not-exist", is_active=False)


def test_ttl_constants_are_sane() -> None:
    assert timedelta(days=30) == SESSION_TTL
    assert timedelta(days=1) == SESSION_REFRESH_THRESHOLD


@pytest.mark.asyncio
async def test_update_profile_partial_does_not_touch_other_fields(service: AuthService) -> None:
    result = await service.register("p@example.com", "password123")

    user = await service.update_profile(result.user.id, {"first_name": "Ася"})
    assert user.first_name == "Ася"
    assert user.onboarded_at is None  # без флага onboarded отметка не ставится

    user = await service.update_profile(result.user.id, {"last_name": "Иванова"})
    assert user.first_name == "Ася"
    assert user.last_name == "Иванова"


@pytest.mark.asyncio
async def test_update_profile_onboarded_sets_timestamp_idempotently(
    service: AuthService,
) -> None:
    result = await service.register("p@example.com", "password123")

    user = await service.update_profile(result.user.id, {}, onboarded=True)
    first_ts = user.onboarded_at
    assert first_ts is not None

    # повторный onboarded=true не перезаписывает отметку
    user = await service.update_profile(result.user.id, {"first_name": "Ася"}, onboarded=True)
    assert user.onboarded_at == first_ts
    assert user.first_name == "Ася"


@pytest.mark.asyncio
async def test_update_profile_unknown_user_raises(service: AuthService) -> None:
    with pytest.raises(UserNotFoundError):
        await service.update_profile("does-not-exist", {"first_name": "X"})


@pytest.mark.asyncio
async def test_update_profile_tour_completed_sets_timestamp_idempotently(
    service: AuthService,
) -> None:
    """T-0132: флаг tour_completed ставит tour_completed_at один раз и не
    зависит от onboarded (отметки независимые)."""
    result = await service.register("t@example.com", "password123")

    user = await service.update_profile(result.user.id, {}, tour_completed=True)
    first_ts = user.tour_completed_at
    assert first_ts is not None
    assert user.onboarded_at is None  # tour_completed не трогает onboarded_at

    user = await service.update_profile(result.user.id, {}, tour_completed=True)
    assert user.tour_completed_at == first_ts


@pytest.mark.asyncio
async def test_count_user_questions_across_conversations(service: AuthService) -> None:
    """T-0132: счётчик заданных вопросов — user-сообщения по всем беседам
    пользователя (для автоскрытия пилюли тура после трёх)."""
    from neurolegal.agent.store.conversation_store import ConversationStore

    result = await service.register("q@example.com", "password123")
    uid = result.user.id
    assert await service.count_user_questions(uid) == 0

    convs = ConversationStore(service._store._session)
    c1 = await convs.create_conversation(uid)
    c2 = await convs.create_conversation(uid)
    await convs.append_message(c1, uid, "user", "вопрос 1")
    await convs.append_message(c1, uid, "assistant", "ответ 1")
    await convs.append_message(c2, uid, "user", "вопрос 2")
    await convs.commit()

    assert await service.count_user_questions(uid) == 2
