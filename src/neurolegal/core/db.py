from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from neurolegal.core.config import settings, to_asyncpg_url

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def asyncpg_connect_args() -> dict[str, int]:
    """asyncpg connect args shared by the app engine and alembic.

    asyncpg keeps a per-connection prepared-statement cache. That cache becomes
    invalid when transactions land on different backends — which is exactly what
    pgbouncer in transaction-pool mode does (e.g. Neon's `-pooler.` host),
    surfacing as opaque ConnectionDoesNotExistError mid-write. Set
    NEUROLEGAL_DB_STATEMENT_CACHE_SIZE=0 when behind such a pooler; the default of
    100 is right for a direct connection to a non-pooled Postgres.
    """
    return {"statement_cache_size": settings.db_statement_cache_size}


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            to_asyncpg_url(settings.database_url),
            pool_size=settings.db_pool_size,
            max_overflow=5,
            pool_pre_ping=True,
            connect_args=asyncpg_connect_args(),
        )
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    global _sessionmaker
    if _sessionmaker is None:
        _sessionmaker = async_sessionmaker(get_engine(), expire_on_commit=False)
    return _sessionmaker


async def session_dependency() -> AsyncGenerator[AsyncSession, None]:
    async with get_sessionmaker()() as session:
        yield session
