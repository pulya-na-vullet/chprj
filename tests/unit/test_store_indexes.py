"""Guards against drift between bulk-load index DDL and the alembic migration."""

from pathlib import Path

from neurolegal.rag.store import indexes


def test_create_sql_matches_migration_0002() -> None:
    """The CREATE INDEX statements in store/indexes.py must mirror the ones
    in alembic/versions/0002_search_vector_indexes.py. If you change one,
    update the other.
    """
    mig = Path(__file__).parents[2] / "alembic" / "versions" / "0002_search_vector_indexes.py"
    src = mig.read_text(encoding="utf-8")

    # Whitespace-normalised substring checks for the two CREATE INDEX bodies.
    expected_hnsw_core = (
        "CREATE INDEX chunks_embedding_hnsw "
        "ON chunks USING hnsw (embedding vector_cosine_ops) "
        "WITH (m = 16, ef_construction = 64)"
    )
    assert "".join(expected_hnsw_core.split()) in "".join(indexes._CREATE_HNSW.split())
    assert "".join(expected_hnsw_core.split()) in "".join(src.split())

    expected_gin_core = "CREATE INDEX chunks_search_vector_gin ON chunks USING gin (search_vector)"
    assert "".join(expected_gin_core.split()) in "".join(indexes._CREATE_GIN.split())
    assert "".join(expected_gin_core.split()) in "".join(src.split())
