"""Unit checks for the hybrid-search SQL without a live database.

Guards two invariants from real incidents:
- the query vector CAST stays tied to EMBEDDING_DIM (no frozen 1024 literal);
- ``hnsw.ef_search`` is widened transaction-locally BEFORE the dense scan,
  otherwise an act filter starves the HNSW leg (post-filter starvation).
"""

from typing import Any
from unittest.mock import MagicMock

import pytest

from neurolegal.core.config import settings
from neurolegal.core.domain import EMBEDDING_DIM
from neurolegal.rag.store.search import HYBRID_SEARCH_SQL, hybrid_search


def test_qvec_cast_uses_embedding_dim() -> None:
    assert f"vector({EMBEDDING_DIM})" in HYBRID_SEARCH_SQL


class _FakeSession:
    def __init__(self) -> None:
        self.statements: list[str] = []

    async def execute(self, statement: Any, params: Any = None) -> Any:
        self.statements.append(str(statement))
        result = MagicMock()
        result.mappings.return_value.all.return_value = []
        return result


@pytest.mark.asyncio
async def test_hybrid_search_sets_ef_search_before_query() -> None:
    session = _FakeSession()
    articles = await hybrid_search(
        session,  # type: ignore[arg-type]
        query_vector=[0.0] * EMBEDDING_DIM,
        query_text="налог",
        acts=["ГК РФ"],
        limit=8,
    )

    assert articles == []
    assert len(session.statements) == 2
    assert session.statements[0] == f"SET LOCAL hnsw.ef_search = {settings.hnsw_ef_search}"
    assert "WITH params AS" in session.statements[1]
