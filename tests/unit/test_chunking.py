from uuid import uuid4

from neurolegal.core.domain import Article, ArticlePoint
from neurolegal.rag.chunking import ChunkStrategy, chunk_article


def make_article(text: str) -> Article:
    return Article(
        id=uuid4(),
        act_id=uuid4(),
        parent_node_id=None,
        number="421",
        title="Свобода договора",
        full_text=text,
        ordinal=421,
    )


def test_chunk_per_point_splits_numbered_paragraphs() -> None:
    art = make_article(
        "1. Граждане свободны. 2. Стороны могут заключить. 3. Можно смешанный. 4. Условия."
    )
    chunks = chunk_article(art, strategy=ChunkStrategy.PER_POINT, act_short_name="ГК РФ")
    assert len(chunks) == 4
    assert chunks[0].part_number == "1"
    assert chunks[3].part_number == "4"
    assert "Граждане" in chunks[0].text
    assert chunks[0].path.startswith("ст. 421")


def test_chunk_sliding_for_long_point() -> None:
    long_text = "1. " + ("слово " * 300)
    art = make_article(long_text)
    chunks = chunk_article(
        art, strategy=ChunkStrategy.SLIDING, max_chars=400, overlap=100, act_short_name="ГК РФ"
    )
    assert len(chunks) >= 2
    assert all(len(c.text) <= 500 for c in chunks)


def test_chunk_assigns_ordinal_starting_from_1() -> None:
    art = make_article("1. Один. 2. Два.")
    chunks = chunk_article(art, act_short_name="ГК РФ")
    assert [c.ordinal for c in chunks] == [1, 2]


def test_chunk_structure_path_carries_article_number() -> None:
    art = make_article("1. Один.")
    chunks = chunk_article(art, act_short_name="ГК РФ")
    assert chunks[0].structure_path == {"article": "421"}


def test_chunk_uses_article_points_when_present() -> None:
    art = Article(
        id=uuid4(),
        act_id=uuid4(),
        number="1",
        full_text="ignored when points are set",
        ordinal=1,
        points=[
            ArticlePoint(number="1", text="первый пункт"),
            ArticlePoint(number="2", text="второй пункт"),
            ArticlePoint(number="2.1", text="подпункт второго"),
        ],
    )
    chunks = chunk_article(art, act_short_name="ГК РФ")
    assert len(chunks) == 3
    assert [c.part_number for c in chunks] == ["1", "2", "2.1"]
    assert chunks[0].text == "первый пункт"


def test_chunk_falls_back_to_regex_when_no_points() -> None:
    art = Article(
        id=uuid4(),
        act_id=uuid4(),
        number="2",
        full_text="1. foo bar baz. 2. quux",
        ordinal=1,
        points=None,
    )
    chunks = chunk_article(art, act_short_name="ГК РФ")
    assert len(chunks) >= 2
