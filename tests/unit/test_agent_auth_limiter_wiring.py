"""Боевая сборка рейт-лимитера логина/регистрации (T-0101, пункт 1).

Остальные тесты `/auth/*` подменяют лимитер через `dependency_overrides`,
поэтому снятие декоратора `@lru_cache(maxsize=1)` не роняло ни одного из
них: в проде каждый запрос получал бы свежий `RateLimiter`, то есть
лимита не было бы вовсе (перебор паролей, массовая регистрация).
Здесь лимитер не подменяется — проверяется ровно то, что собирает
приложение.

Лимитер процессный, поэтому бюджет чистится и до, и после каждого теста:
иначе израсходованный здесь бюджет утёк бы в соседние тесты (и наоборот).
"""

from collections.abc import AsyncIterator, Iterator

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from neurolegal.agent.api.app import app
from neurolegal.agent.auth.deps import get_auth_service, get_rate_limiter
from neurolegal.agent.auth.limiter import RateLimiter
from neurolegal.agent.auth.service import AuthService
from neurolegal.agent.auth.store import AuthStore
from neurolegal.agent.store.models import Base


def _reset_prod_limiter() -> None:
    get_rate_limiter.cache_clear()


@pytest_asyncio.fixture
async def service() -> AsyncIterator[AuthService]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = async_sessionmaker(engine, expire_on_commit=False)
    async with sm() as session:
        yield AuthService(store=AuthStore(session))
    await engine.dispose()


@pytest.fixture
def prod_limiter_client(service: AuthService) -> Iterator[TestClient]:
    """Клиент на БОЕВОМ лимитере — подменяется только AuthService."""
    _reset_prod_limiter()
    app.dependency_overrides[get_auth_service] = lambda: service
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
        _reset_prod_limiter()


def test_get_rate_limiter_is_a_process_wide_singleton() -> None:
    _reset_prod_limiter()
    try:
        first = get_rate_limiter()
        second = get_rate_limiter()
        assert isinstance(first, RateLimiter)
        assert first is second, (
            "get_rate_limiter обязан отдавать один и тот же объект на весь "
            "процесс: свежий RateLimiter на каждый запрос — это отсутствие лимита"
        )
    finally:
        _reset_prod_limiter()


def test_login_hits_429_on_the_real_limiter(prod_limiter_client: TestClient) -> None:
    # Разные email — тратится только бюджет по IP (10 за 5 мин); бюджет по
    # email (5) на общем адресе сработал бы раньше и проверял бы не то.
    for i in range(10):
        resp = prod_limiter_client.post(
            "/auth/login", json={"email": f"prod{i}@example.com", "password": "whatever"}
        )
        assert resp.status_code == 401
    resp = prod_limiter_client.post(
        "/auth/login", json={"email": "prod-overflow@example.com", "password": "whatever"}
    )
    assert resp.status_code == 429
    assert resp.json()["detail"] == "rate_limited"


def test_register_hits_429_on_the_real_limiter(prod_limiter_client: TestClient) -> None:
    for i in range(5):
        resp = prod_limiter_client.post(
            "/auth/register",
            json={"email": f"prodreg{i}@example.com", "password": "password123"},
        )
        assert resp.status_code == 200
    resp = prod_limiter_client.post(
        "/auth/register",
        json={"email": "prodreg-overflow@example.com", "password": "password123"},
    )
    assert resp.status_code == 429
