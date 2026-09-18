from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from neurolegal.contracts import SearchedArticle, SearchedChunk
from neurolegal.core.domain import (
    EMBEDDING_DIM,
    Article,
    ArticlePoint,
    Chunk,
    LegalAct,
    StructuredDoc,
    StructureNode,
)


def test_legal_act_codex_minimal() -> None:
    act = LegalAct(
        id=uuid4(),
        kind="codex",
        short_name="ГК РФ",
        full_name="Гражданский кодекс Российской Федерации (часть первая)",
        source="local-docx",
        source_doc_id="gk-1",
        ingested_at=datetime.now(UTC),
    )
    assert act.kind == "codex"
    assert act.redaction is None


def test_legal_act_federal_law_minimal() -> None:
    act = LegalAct(
        id=uuid4(),
        kind="federal_law",
        short_name="44-ФЗ",
        full_name="О контрактной системе…",
        source="local-docx",
        source_doc_id="fz-44",
        ingested_at=datetime.now(UTC),
    )
    assert act.kind == "federal_law"


def test_legal_act_invalid_kind() -> None:
    with pytest.raises(ValidationError):
        LegalAct(
            id=uuid4(),
            kind="decree",
            short_name="x",
            full_name="x",
            source="x",
            source_doc_id="x",
            ingested_at=datetime.now(UTC),
        )


def test_structure_node_subsection_allowed() -> None:
    node = StructureNode(
        id=uuid4(),
        act_id=uuid4(),
        parent_id=None,
        type="subsection",
        number="1",
        title="Основные положения",
        ordinal=1,
    )
    assert node.type == "subsection"


def test_article_points_optional_default_none() -> None:
    art = Article(
        id=uuid4(),
        act_id=uuid4(),
        parent_node_id=None,
        number="421",
        title="Свобода договора",
        full_text="…",
        ordinal=1,
    )
    assert art.points is None


def test_article_points_populated() -> None:
    art = Article(
        id=uuid4(),
        act_id=uuid4(),
        parent_node_id=None,
        number="1",
        title=None,
        full_text="1. foo\n\n2. bar",
        ordinal=1,
        points=[
            ArticlePoint(number="1", text="foo"),
            ArticlePoint(number="2", text="bar"),
        ],
    )
    assert art.points is not None
    assert [p.number for p in art.points] == ["1", "2"]


def test_chunk_uses_act_id() -> None:
    aid = uuid4()
    chunk = Chunk(
        id=uuid4(),
        article_id=uuid4(),
        act_id=aid,
        path="ст. 1 ГК РФ",
        text="text",
        ordinal=1,
        embedding=[0.0] * EMBEDDING_DIM,
        structure_path={"article": "1"},
    )
    assert chunk.act_id == aid
    assert chunk.path.endswith("ГК РФ")


def test_chunk_structure_path_requires_article() -> None:
    with pytest.raises(ValidationError):
        Chunk(
            id=uuid4(),
            article_id=uuid4(),
            act_id=uuid4(),
            path="x",
            text="x",
            ordinal=1,
            embedding=[0.0] * EMBEDDING_DIM,
            structure_path={"chapter": "27"},
        )


def test_structured_doc_uses_act() -> None:
    act = LegalAct(
        id=uuid4(),
        kind="codex",
        short_name="x",
        full_name="x",
        source="x",
        source_doc_id="x",
        ingested_at=datetime.now(UTC),
    )
    doc = StructuredDoc(act=act, structure_nodes=[], articles=[])
    assert doc.act.kind == "codex"


def test_searched_article_includes_act_fields() -> None:
    sa = SearchedArticle(
        article_id=uuid4(),
        act_short_name="ГК РФ",
        act_kind="codex",
        number="1",
        title=None,
        full_text="…",
        matched_chunks=[SearchedChunk(chunk_id=uuid4(), path="ст. 1 ГК РФ", text="x", score=0.5)],
        score=0.5,
    )
    assert sa.act_short_name == "ГК РФ"
    assert sa.act_kind == "codex"
