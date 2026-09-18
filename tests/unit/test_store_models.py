from sqlalchemy import Table, inspect

from neurolegal.rag.store.models import ActRow, ArticleRow, ChunkRow, StructureNodeRow


def _table(model: type) -> Table:
    return inspect(model).local_table


def test_chunk_row_has_embedding_column() -> None:
    cols = {c.name for c in _table(ChunkRow).columns}
    assert {
        "id",
        "article_id",
        "act_id",
        "path",
        "text",
        "ordinal",
        "embedding",
        "structure_path",
    } <= cols


def test_chunk_unique_constraint() -> None:
    constraints = _table(ChunkRow).constraints
    unique_names = {c.name for c in constraints if isinstance(c.name, str)}
    # alembic-сгенерированное имя UNIQUE constraint'а  # noqa: RUF003
    assert any("article_id" in n and "ordinal" in n for n in unique_names)


def test_act_unique_source_doc() -> None:
    cols = {c.name for c in _table(ActRow).columns}
    assert {"source", "source_doc_id"} <= cols


def test_act_has_kind_column() -> None:
    cols = {c.name for c in _table(ActRow).columns}
    assert "kind" in cols


def test_structure_node_self_fk() -> None:
    fks = list(_table(StructureNodeRow).foreign_keys)
    self_fks = [fk for fk in fks if fk.column.table.name == "structure_nodes"]
    assert len(self_fks) == 1


def test_article_fk_to_act() -> None:
    fks = list(_table(ArticleRow).foreign_keys)
    fk_targets = {fk.column.table.name for fk in fks}
    assert "acts" in fk_targets
