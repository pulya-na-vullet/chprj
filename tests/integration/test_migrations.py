"""Миграции реально накатываются на чистую БД (T-0103, пункт 2).

Четырнадцать ревизий — и ни одного теста, который бы их выполнил:
`test_cli_main.py` мокает `subprocess.run`, `test_db_smoke` инспектирует
уже накатанную dev-базу. Сломанная ревизия обнаруживалась бы только при
разворачивании нового окружения, то есть на выкладке.

Прогон идёт на ОТДЕЛЬНОЙ временной базе того же сервера. Dev-база хранит
десятки тысяч чанков и не должна пострадать ни при каком исходе, тогда как
`downgrade base` по определению разрушителен. База создаётся под уникальным
именем и удаляется в `finally`.

Alembic запускается подпроцессом: `alembic/env.py` сам зовёт `asyncio.run()`,
внутри уже работающего цикла событий это невозможно. Подпроцесс заодно
проверяет боевой путь целиком — ровно то, что делает `neurolegal migrate`.
"""

import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

import asyncpg
import pytest

from neurolegal.core.config import settings, to_asyncpg_url

pytestmark = pytest.mark.db_only

REPO_ROOT = Path(__file__).resolve().parents[2]

#: Таблицы, ради которых миграции и существуют: по одной от каждого владельца
#: схемы (rag, agent, документ-сервис) плюс сам журнал alembic.
_EXPECTED_TABLES = {
    "acts",
    "articles",
    "chunks",
    "conversations",
    "messages",
    "users",
    "auth_sessions",
    "hub_documents",
    "hub_document_attachments",
    "tpl_templates",
    "alembic_version",
}


def _swap_database(url: str, database: str) -> str:
    parts = urlsplit(to_asyncpg_url(url))
    return urlunsplit((parts.scheme, parts.netloc, f"/{database}", parts.query, parts.fragment))


def _dsn(url: str) -> str:
    """asyncpg не понимает драйверный префикс SQLAlchemy."""
    return url.replace("postgresql+asyncpg://", "postgresql://", 1)


async def _maintenance(sql: str) -> None:
    conn = await asyncpg.connect(_dsn(_swap_database(settings.database_url, "postgres")))
    try:
        await conn.execute(sql)
    finally:
        await conn.close()


async def _table_names(url: str) -> set[str]:
    conn = await asyncpg.connect(_dsn(url))
    try:
        rows = await conn.fetch(
            "SELECT tablename FROM pg_tables WHERE schemaname = current_schema()"
        )
    finally:
        await conn.close()
    return {r["tablename"] for r in rows}


def _alembic(command: str, revision: str, url: str) -> None:
    """`alembic <command> <revision>` на указанной базе.

    env.py читает URL из настроек, настройки — из окружения (переменные
    окружения приоритетнее .env.local), поэтому подменяем DATABASE_URL.
    """
    result = subprocess.run(
        [sys.executable, "-m", "alembic", command, revision],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        env={**os.environ, "DATABASE_URL": url},
    )
    assert result.returncode == 0, (
        f"alembic {command} {revision} упал:\n{result.stdout}\n{result.stderr}"
    )


async def test_migrations_upgrade_downgrade_upgrade() -> None:
    database = f"neurolegal_migtest_{uuid4().hex[:12]}"
    await _maintenance(f'CREATE DATABASE "{database}"')
    url = _swap_database(settings.database_url, database)
    try:
        _alembic("upgrade", "head", url)
        after_upgrade = await _table_names(url)
        assert after_upgrade >= _EXPECTED_TABLES, sorted(_EXPECTED_TABLES - after_upgrade)

        # downgrade обязан быть полным: остаётся только журнал версий.
        _alembic("downgrade", "base", url)
        after_downgrade = await _table_names(url)
        assert after_downgrade <= {"alembic_version"}, sorted(after_downgrade)

        # Повторный накат на уже «раскатанную» базу — проверка, что downgrade
        # не оставил за собой ни типов, ни индексов, мешающих второму заходу.
        _alembic("upgrade", "head", url)
        assert await _table_names(url) >= _EXPECTED_TABLES
    finally:
        await _maintenance(f'DROP DATABASE IF EXISTS "{database}" WITH (FORCE)')
