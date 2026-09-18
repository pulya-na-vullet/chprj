import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context
from neurolegal.agent.store.models import Base as AgentBase
from neurolegal.core.config import settings, to_asyncpg_url
from neurolegal.core.db import asyncpg_connect_args
from neurolegal.documents.store.models import Base as DocumentsBase
from neurolegal.rag.store.models import Base as RagBase
from neurolegal.templates.store.models import Base as TemplatesBase

config = context.config
# set_main_option кладёт значение в configparser, который трактует "%" как
# начало интерполяции. Пароль в DATABASE_URL приходит процентно-кодированным
# (%3B, %29 и подобное), поэтому "%" нужно удвоить — иначе alembic падает:
# "ValueError: invalid interpolation syntax". SQLAlchemy декодирует URL сам.
config.set_main_option("sqlalchemy.url", to_asyncpg_url(settings.database_url).replace("%", "%%"))

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Alembic accepts a list of MetaData; rag, agent, the documents hub and the
# templates service own disjoint tables. Missing metadata here makes
# `alembic revision --autogenerate` propose DROPping the tables it doesn't
# know about.
target_metadata = [
    RagBase.metadata,
    AgentBase.metadata,
    DocumentsBase.metadata,
    TemplatesBase.metadata,
]


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        connect_args=asyncpg_connect_args(),
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
