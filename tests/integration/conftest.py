"""Skip integration tests by marker, not by package.

The root project sets a sentinel ``DATABASE_URL`` so pydantic-settings loads
during unit tests; that sentinel does NOT count as a usable connection.
Tests opt in to their requirements via pytest markers:

* ``@pytest.mark.db_only``            — needs DATABASE_URL (real)
* ``@pytest.mark.external_openrouter`` — needs OPENROUTER_API_KEY
* ``@pytest.mark.e2e``                — needs both
* ``@pytest.mark.api_with_mocks``     — needs nothing

Without the right env, only the matching tests skip; the others run.
"""

import os

import pytest

import neurolegal.core.db as core_db

_DB_URL = os.environ.get("DATABASE_URL", "")
_DB_AVAILABLE = bool(_DB_URL) and "_TEST_NO_DB_" not in _DB_URL
_API_KEY_AVAILABLE = bool(os.environ.get("OPENROUTER_API_KEY"))


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    for item in items:
        markers = {m.name for m in item.iter_markers()}
        skip_reasons: list[str] = []
        if ("db_only" in markers or "e2e" in markers) and not _DB_AVAILABLE:
            skip_reasons.append("needs DATABASE_URL")
        if ("external_openrouter" in markers or "e2e" in markers) and not _API_KEY_AVAILABLE:
            skip_reasons.append("needs OPENROUTER_API_KEY")
        if skip_reasons:
            item.add_marker(pytest.mark.skip(reason="; ".join(skip_reasons)))


@pytest.fixture(autouse=True)
def _reset_core_db_engine_cache() -> None:
    """Null the module-level engine cache before every integration test.

    ``neurolegal.core.db`` caches one ``AsyncEngine`` per process. asyncpg binds
    its connections to the event loop that created them — when pytest-asyncio
    closes a test's loop and starts a new one, any pooled connection from
    the old loop becomes unusable, surfacing as ``RuntimeError: Event loop
    is closed`` or ``Future attached to a different loop``. Test files
    mitigate this with ``loop_scope="module"``, but the cache still leaks
    across modules with different loop scopes (in particular,
    ``loop_scope="module"`` files vs default function-scoped ones).

    Resetting the references here forces ``get_engine()`` to build a fresh
    engine on the current test's loop. The dangling connections from the
    previous test are garbage-collected; their backing loop is already
    gone, so there is nothing useful left to dispose anyway.
    """
    core_db._engine = None
    core_db._sessionmaker = None
