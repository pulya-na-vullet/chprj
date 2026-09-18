from unittest.mock import patch

import pytest

import neurolegal.core.db as core_db
import neurolegal.rag.store.db as rag_db
from neurolegal.core.config import Settings
from neurolegal.core.db import asyncpg_connect_args


def test_connect_args_carry_statement_cache_size(monkeypatch: pytest.MonkeyPatch) -> None:
    from neurolegal.core import db as db_mod

    monkeypatch.setattr(db_mod.settings, "db_statement_cache_size", 0)
    assert asyncpg_connect_args() == {"statement_cache_size": 0}


def test_rag_db_reexports_core_db() -> None:
    # The rag module must expose the same callables as core, so existing
    # imports keep working after the move.
    assert rag_db.get_engine is core_db.get_engine
    assert rag_db.get_sessionmaker is core_db.get_sessionmaker
    assert rag_db.session_dependency is core_db.session_dependency


def test_get_engine_uses_default_statement_cache_size(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without an explicit override, asyncpg's own default (100) reaches connect_args."""
    monkeypatch.delenv("NEUROLEGAL_DB_STATEMENT_CACHE_SIZE", raising=False)
    fresh = Settings(_env_file=None, DATABASE_URL="postgresql://u:p@h/db")
    monkeypatch.setattr(core_db, "settings", fresh)
    monkeypatch.setattr(core_db, "_engine", None)

    sentinel = object()
    with patch.object(core_db, "create_async_engine", return_value=sentinel) as mock:
        engine = core_db.get_engine()

    assert engine is sentinel
    assert mock.call_args.kwargs["connect_args"] == {"statement_cache_size": 100}


def test_get_engine_propagates_statement_cache_size_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """NEUROLEGAL_DB_STATEMENT_CACHE_SIZE=0 is what we set when behind pgbouncer."""
    monkeypatch.setenv("NEUROLEGAL_DB_STATEMENT_CACHE_SIZE", "0")
    fresh = Settings(_env_file=None, DATABASE_URL="postgresql://u:p@h/db")
    monkeypatch.setattr(core_db, "settings", fresh)
    monkeypatch.setattr(core_db, "_engine", None)

    sentinel = object()
    with patch.object(core_db, "create_async_engine", return_value=sentinel) as mock:
        core_db.get_engine()

    assert mock.call_args.kwargs["connect_args"] == {"statement_cache_size": 0}
