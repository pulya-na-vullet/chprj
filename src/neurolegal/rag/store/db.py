"""Re-export of the shared DB engine factory.

The engine/sessionmaker live in ``neurolegal.core.db`` so ``agent/`` can use
Postgres without importing ``neurolegal.rag.*``. This module keeps the historical
``neurolegal.rag.store.db`` import path working for the rest of ``rag/``.
"""

from neurolegal.core.db import get_engine, get_sessionmaker, session_dependency

__all__ = ["get_engine", "get_sessionmaker", "session_dependency"]
