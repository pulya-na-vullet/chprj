"""/auth/* ASGI route tests — dependency_overrides swap in an in-memory
AuthService/AuthStore, mirroring the pattern in
tests/unit/test_agent_conversations_route.py and test_agent_chat_route.py.

MVP without email verification (T-0026): register answers like login —
MeResponse + session cookie; the mail-based routes (verify-email /
resend-verification / request-password-reset / reset-password) are gone.
"""

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from neurolegal.agent.api.app import app
from neurolegal.agent.auth.deps import SESSION_COOKIE_NAME, get_auth_service, get_rate_limiter
from neurolegal.agent.auth.limiter import RateLimiter
from neurolegal.agent.auth.service import AuthService
from neurolegal.agent.auth.store import AuthStore
from neurolegal.agent.store.models import Base
from neurolegal.core.config import settings


def _cookie_attrs(set_cookie_header: str) -> set[str]:
    """Атрибуты Set-Cookie в нижнем регистре. Сверять флаг подстрокой нельзя —
    значение куки случайное и может содержать что угодно."""
    return {part.strip().lower() for part in set_cookie_header.split(";")}


@pytest_asyncio.fixture
async def service() -> AsyncIterator[AuthService]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = async_sessionmaker(engine, expire_on_commit=False)
    async with sm() as session:
        yield AuthService(store=AuthStore(session))
    await engine.dispose()


def _client(service: AuthService) -> TestClient:
    app.dependency_overrides[get_auth_service] = lambda: service
    limiter = RateLimiter()
    app.dependency_overrides[get_rate_limiter] = lambda: limiter
    return TestClient(app)


def test_register_logs_in_immediately(service: AuthService) -> None:
    try:
        client = _client(service)

        resp = client.post(
            "/auth/register", json={"email": "Full@Example.com", "password": "password123"}
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["email"] == "full@example.com"
        assert isinstance(body["id"], str)
        assert SESSION_COOKIE_NAME in resp.cookies
        cookie_header = resp.headers.get("set-cookie", "")
        assert "HttpOnly" in cookie_header
        assert "samesite=lax" in cookie_header.lower()

        # the register cookie is a live session — no separate login step
        resp = client.get("/auth/me")
        assert resp.status_code == 200
        assert resp.json()["email"] == "full@example.com"

        resp = client.post("/auth/logout")
        assert resp.status_code == 204

        resp = client.get("/auth/me")
        assert resp.status_code == 401
    finally:
        app.dependency_overrides.clear()


def test_register_existing_email_returns_409(service: AuthService) -> None:
    try:
        client = _client(service)
        client.post("/auth/register", json={"email": "dup@example.com", "password": "password123"})
        resp = client.post(
            "/auth/register", json={"email": "dup@example.com", "password": "other-password"}
        )
        assert resp.status_code == 409
        assert resp.json()["detail"] == "email_taken"
        assert SESSION_COOKIE_NAME not in resp.cookies
    finally:
        app.dependency_overrides.clear()


def test_login_works_right_after_register(service: AuthService) -> None:
    try:
        client = _client(service)
        client.post("/auth/register", json={"email": "l@example.com", "password": "password123"})
        client.post("/auth/logout")

        resp = client.post(
            "/auth/login", json={"email": "l@example.com", "password": "password123"}
        )
        assert resp.status_code == 200
        assert resp.json()["email"] == "l@example.com"
        assert SESSION_COOKIE_NAME in resp.cookies
    finally:
        app.dependency_overrides.clear()


def test_login_invalid_credentials_returns_401(service: AuthService) -> None:
    try:
        client = _client(service)
        resp = client.post(
            "/auth/login", json={"email": "nobody@example.com", "password": "whatever"}
        )
        assert resp.status_code == 401
        assert resp.json()["detail"] == "invalid_credentials"
    finally:
        app.dependency_overrides.clear()


def test_mail_flow_routes_are_gone(service: AuthService) -> None:
    """T-0026 removed the mail-based flows; the routes must not linger as
    dead endpoints. Unknown paths answer 404, or 405 when they fall through
    to the SPA static mount on `/` (which only serves GET)."""
    try:
        client = _client(service)
        gone = (404, 405)
        assert client.get("/auth/verify-email?token=x").status_code in gone
        assert (
            client.post("/auth/resend-verification", json={"email": "x@example.com"}).status_code
            in gone
        )
        assert (
            client.post("/auth/request-password-reset", json={"email": "x@example.com"}).status_code
            in gone
        )
        assert (
            client.post(
                "/auth/reset-password", json={"token": "x", "password": "password123"}
            ).status_code
            in gone
        )
    finally:
        app.dependency_overrides.clear()


def test_me_without_cookie_returns_401(service: AuthService) -> None:
    try:
        client = _client(service)
        resp = client.get("/auth/me")
        assert resp.status_code == 401
    finally:
        app.dependency_overrides.clear()


def test_logout_without_cookie_returns_204(service: AuthService) -> None:
    try:
        client = _client(service)
        resp = client.post("/auth/logout")
        assert resp.status_code == 204
    finally:
        app.dependency_overrides.clear()


def test_login_rate_limited_per_ip(service: AuthService) -> None:
    try:
        client = _client(service)
        # Distinct emails so only the per-IP budget (10/5min) is exercised —
        # the per-email budget (5/5min) would trip first on a shared email.
        for i in range(10):
            resp = client.post(
                "/auth/login", json={"email": f"rl{i}@example.com", "password": "whatever"}
            )
            assert resp.status_code == 401
        resp = client.post(
            "/auth/login", json={"email": "rl-overflow@example.com", "password": "whatever"}
        )
        assert resp.status_code == 429
        assert resp.json()["detail"] == "rate_limited"
    finally:
        app.dependency_overrides.clear()


def test_login_rate_limited_per_email_before_per_ip(service: AuthService) -> None:
    try:
        client = _client(service)
        for _ in range(5):
            resp = client.post(
                "/auth/login", json={"email": "same@example.com", "password": "whatever"}
            )
            assert resp.status_code == 401
        resp = client.post(
            "/auth/login", json={"email": "same@example.com", "password": "whatever"}
        )
        assert resp.status_code == 429
    finally:
        app.dependency_overrides.clear()


def test_login_rate_limit_key_is_case_insensitive(service: AuthService) -> None:
    """Бюджет по email не обходится чередованием регистра (T-0101, пункт 7).

    EmailStr нормализует только домен, локальная часть доезжает как есть —
    без `.lower()` в ключе лимита `a@x.com` и `A@x.com` получали бы по
    отдельному бюджету, и перебор пароля масштабировался бы регистром.
    """
    try:
        client = _client(service)
        variants = [
            "Same@example.com",
            "same@example.com",
            "SAME@example.com",
            "sAmE@example.com",
            "SaMe@example.com",
        ]
        for email in variants:
            resp = client.post("/auth/login", json={"email": email, "password": "whatever"})
            assert resp.status_code == 401, email
        resp = client.post(
            "/auth/login", json={"email": "sAME@example.com", "password": "whatever"}
        )
        assert resp.status_code == 429
    finally:
        app.dependency_overrides.clear()


def test_session_cookie_is_secure_when_configured(
    service: AuthService, monkeypatch: pytest.MonkeyPatch
) -> None:
    """NEUROLEGAL_COOKIE_SECURE доезжает до флага Secure (T-0101, пункт 7)."""
    monkeypatch.setattr(settings, "cookie_secure", True)
    try:
        client = _client(service)
        resp = client.post(
            "/auth/register", json={"email": "sec@example.com", "password": "password123"}
        )
        assert resp.status_code == 200
        assert "secure" in _cookie_attrs(resp.headers["set-cookie"])
    finally:
        app.dependency_overrides.clear()


def test_session_cookie_is_not_secure_over_plain_http_dev(service: AuthService) -> None:
    """Дефолт (локальный http) — без Secure, иначе кука не долетит в дев."""
    try:
        client = _client(service)
        resp = client.post(
            "/auth/register", json={"email": "insec@example.com", "password": "password123"}
        )
        assert resp.status_code == 200
        assert "secure" not in _cookie_attrs(resp.headers["set-cookie"])
    finally:
        app.dependency_overrides.clear()


def test_profile_patch_requires_auth(service: AuthService) -> None:
    try:
        client = _client(service)
        resp = client.patch("/profile", json={"first_name": "Ася"})
        assert resp.status_code == 401
    finally:
        app.dependency_overrides.clear()


def test_me_returns_empty_profile_for_fresh_user(service: AuthService) -> None:
    try:
        client = _client(service)
        client.post(
            "/auth/register", json={"email": "fresh@example.com", "password": "password123"}
        )
        body = client.get("/auth/me").json()
        assert body["first_name"] is None
        assert body["last_name"] is None
        assert body["avatar_preset"] is None
        assert body["usage_kind"] is None
        assert body["role"] is None
        assert body["tasks"] is None
        assert body["onboarded_at"] is None
    finally:
        app.dependency_overrides.clear()


def test_profile_patch_partial_update_roundtrips_to_me(service: AuthService) -> None:
    try:
        client = _client(service)
        client.post("/auth/register", json={"email": "p@example.com", "password": "password123"})

        resp = client.patch(
            "/profile",
            json={
                "first_name": "Ася",
                "avatar_preset": 3,
                "usage_kind": "business",
                "role": "lawyer",
                "tasks": ["law_questions", "files"],
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["first_name"] == "Ася"
        assert body["avatar_preset"] == 3
        assert body["usage_kind"] == "business"
        assert body["role"] == "lawyer"
        assert body["tasks"] == ["law_questions", "files"]
        assert body["onboarded_at"] is None  # onboarded не передавали

        # частичный апдейт не сбрасывает ранее заполненное
        resp = client.patch("/profile", json={"last_name": "Иванова"})
        assert resp.status_code == 200
        body = client.get("/auth/me").json()
        assert body["first_name"] == "Ася"
        assert body["last_name"] == "Иванова"
        assert body["tasks"] == ["law_questions", "files"]
    finally:
        app.dependency_overrides.clear()


def test_profile_patch_onboarded_is_idempotent(service: AuthService) -> None:
    try:
        client = _client(service)
        client.post("/auth/register", json={"email": "o@example.com", "password": "password123"})

        first = client.patch("/profile", json={"onboarded": True}).json()
        assert first["onboarded_at"] is not None

        second = client.patch("/profile", json={"onboarded": True}).json()
        assert second["onboarded_at"] == first["onboarded_at"]
    finally:
        app.dependency_overrides.clear()


def test_profile_patch_tour_completed_is_idempotent(service: AuthService) -> None:
    """T-0132: флаг tour_completed ставит tour_completed_at один раз;
    onboarded_at при этом не трогается."""
    try:
        client = _client(service)
        client.post("/auth/register", json={"email": "tc@example.com", "password": "password123"})

        first = client.patch("/profile", json={"tour_completed": True}).json()
        assert first["tour_completed_at"] is not None
        assert first["onboarded_at"] is None

        second = client.patch("/profile", json={"tour_completed": True}).json()
        assert second["tour_completed_at"] == first["tour_completed_at"]
    finally:
        app.dependency_overrides.clear()


def test_me_reports_questions_asked(service: AuthService) -> None:
    """T-0132: /auth/me отдаёт суммарное число user-сообщений по всем
    беседам — фронт по нему скрывает пилюлю тура после трёх вопросов."""
    import asyncio

    from neurolegal.agent.store.conversation_store import ConversationStore

    try:
        client = _client(service)
        resp = client.post(
            "/auth/register", json={"email": "qa@example.com", "password": "password123"}
        )
        uid = resp.json()["id"]
        assert client.get("/auth/me").json()["questions_asked"] == 0

        async def seed() -> None:
            convs = ConversationStore(service._store._session)
            c1 = await convs.create_conversation(uid)
            c2 = await convs.create_conversation(uid)
            await convs.append_message(c1, uid, "user", "вопрос 1")
            await convs.append_message(c1, uid, "assistant", "ответ")
            await convs.append_message(c2, uid, "user", "вопрос 2")
            await convs.append_message(c2, uid, "user", "вопрос 3")
            await convs.commit()

        asyncio.get_event_loop_policy().new_event_loop().run_until_complete(seed())

        assert client.get("/auth/me").json()["questions_asked"] == 3
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize(
    "payload",
    [
        {"usage_kind": "corporate"},
        {"role": "ceo"},
        {"tasks": ["hacking"]},
        {"first_name": "и" * 101},
        {"last_name": "и" * 101},
        {"avatar_preset": 6},
        {"avatar_preset": -1},
    ],
)
def test_profile_patch_validation_returns_422(
    service: AuthService, payload: dict[str, object]
) -> None:
    try:
        client = _client(service)
        client.post("/auth/register", json={"email": "v@example.com", "password": "password123"})
        resp = client.patch("/profile", json=payload)
        assert resp.status_code == 422, payload
    finally:
        app.dependency_overrides.clear()


def test_register_rate_limited_per_ip(service: AuthService) -> None:
    try:
        client = _client(service)
        for i in range(5):
            resp = client.post(
                "/auth/register", json={"email": f"u{i}@example.com", "password": "password123"}
            )
            assert resp.status_code == 200
        resp = client.post(
            "/auth/register", json={"email": "overflow@example.com", "password": "password123"}
        )
        assert resp.status_code == 429
    finally:
        app.dependency_overrides.clear()
