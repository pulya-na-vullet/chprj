from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from neurolegal.core.domain import EMBEDDING_DIM, Article, Chunk, LegalAct
from neurolegal.rag.store.db import get_sessionmaker
from neurolegal.rag.store.search import hybrid_search
from neurolegal.rag.store.upsert import replace_act_content, upsert_act

pytestmark = pytest.mark.db_only


@pytest_asyncio.fixture(loop_scope="module")
async def session() -> AsyncGenerator[AsyncSession, None]:
    async with get_sessionmaker()() as s:
        yield s
        await s.execute(text("DELETE FROM acts WHERE source_doc_id LIKE 'test-search-%'"))
        await s.commit()


@pytest_asyncio.fixture(loop_scope="module")
async def seeded(session: AsyncSession) -> AsyncGenerator[dict[str, Any], None]:
    act = LegalAct(
        id=uuid4(),
        kind="codex",
        short_name="ТКС",
        full_name="Тест-кодекс search",
        source="test",
        source_doc_id="test-search-1",
        redaction=None,
        ingested_at=datetime.now(UTC),
    )
    aid = await upsert_act(session, act)
    art_id = uuid4()
    article = Article(
        id=art_id,
        act_id=uuid4(),
        parent_node_id=None,
        number="1",
        title="Свобода договора",
        full_text="1. Граждане свободны в заключении договора.",
        ordinal=1,
    )
    e0 = [0.0] * EMBEDDING_DIM
    e0[0] = 1.0
    chunks = [
        Chunk(
            id=uuid4(),
            article_id=art_id,
            act_id=uuid4(),
            path="ст. 1 ч. 1",
            text="Граждане свободны в заключении договора",
            ordinal=1,
            embedding=e0,
            structure_path={"article": "1"},
        ),
    ]
    await replace_act_content(session, aid, [], [article], chunks)
    await session.commit()
    yield {"act_id": aid, "article_id": str(art_id), "embedding": e0}


@pytest.mark.asyncio(loop_scope="module")
async def test_hybrid_search_finds_seeded(session: AsyncSession, seeded: dict[str, Any]) -> None:
    # The seeded chunk's text is uniquely "Граждане свободны в заключении
    # договора". Querying with that exact phrase (rather than the more
    # famous "свобода договора" which appears in many real articles) keeps
    # the test deterministic against a populated corpus.
    results = await hybrid_search(
        session,
        query_vector=seeded["embedding"],
        query_text="Граждане свободны в заключении договора",
        acts=None,
        limit=5,
    )
    assert len(results) >= 1
    assert str(results[0].article_id) == seeded["article_id"]
    assert results[0].number == "1"
    assert results[0].act_short_name == "ТКС"
    assert results[0].act_kind == "codex"
    assert len(results[0].matched_chunks) >= 1
    assert results[0].matched_chunks[0].path.startswith("ст. 1")


@pytest.mark.asyncio(loop_scope="module")
async def test_hybrid_search_acts_filter_no_match(
    session: AsyncSession, seeded: dict[str, Any]
) -> None:
    results = await hybrid_search(
        session,
        query_vector=seeded["embedding"],
        query_text="свобода",
        acts=["NONEXISTENT"],
        limit=5,
    )
    assert results == []


def _chunk(article_id: Any, text: str, embedding: list[float]) -> Chunk:
    return Chunk(
        id=uuid4(),
        article_id=article_id,
        act_id=uuid4(),
        path="ст. 1 ч. 1",
        text=text,
        ordinal=1,
        embedding=embedding,
        structure_path={"article": "1"},
    )


async def _seed_act(
    session: AsyncSession, short_name: str, doc_id: str, text: str, embedding: list[float]
) -> str:
    act = LegalAct(
        id=uuid4(),
        kind="codex",
        short_name=short_name,
        full_name=f"Тест-кодекс {short_name}",
        source="test",
        source_doc_id=doc_id,
        redaction=None,
        ingested_at=datetime.now(UTC),
    )
    aid = await upsert_act(session, act)
    art_id = uuid4()
    article = Article(
        id=art_id,
        act_id=uuid4(),
        parent_node_id=None,
        number="1",
        title="Тестовая статья",
        full_text=text,
        ordinal=1,
    )
    await replace_act_content(session, aid, [], [article], [_chunk(art_id, text, embedding)])
    return str(art_id)


@pytest_asyncio.fixture(loop_scope="module")
async def two_legs(session: AsyncSession) -> AsyncGenerator[dict[str, Any], None]:
    """Три акта, разводящие ветви фьюжна (T-0103, пункт 6).

    Прежняя фикстура задавала query_vector, равный эмбеддингу единственного
    чанка, — плотная ветвь в одиночку ставила статью на первое место, и
    удаление всей лексической ветви тест бы не заметил.

    Здесь: BOTH совпадает и лексически (фраза дважды — выше ts_rank), и плотно
    (эмбеддинг равен запросу); LEX совпадает лексически, но ортогонален по
    вектору; DENSE совпадает плотно, но по словам не проходит вовсе. Фильтр
    актов отсекает реальный корпус, поэтому ранги детерминированы.
    """
    e_query = [0.0] * EMBEDDING_DIM
    e_query[0] = 1.0
    e_near = [0.0] * EMBEDDING_DIM
    e_near[0], e_near[2] = 0.99, 0.14  # чуть дальше запроса, чем BOTH
    e_far = [0.0] * EMBEDDING_DIM
    e_far[1] = 1.0  # ортогонален: максимальное косинусное расстояние

    phrase = "Граждане свободны в заключении договора."
    both = await _seed_act(session, "ТКС-ОБА", "test-search-both", f"{phrase} {phrase}", e_query)
    lex = await _seed_act(session, "ТКС-ЛЕКС", "test-search-lex", phrase, e_far)
    dense = await _seed_act(
        session,
        "ТКС-ПЛОТ",
        "test-search-dense",
        "Полёты воздушных судов выполняются по разрешению.",
        e_near,
    )
    await session.commit()
    yield {
        "query_vector": e_query,
        "query_text": "граждане свободны заключении договора",
        "acts": ["ТКС-ОБА", "ТКС-ЛЕКС", "ТКС-ПЛОТ"],
        "both": both,
        "lex": lex,
        "dense": dense,
    }


@pytest.mark.asyncio(loop_scope="module")
async def test_hybrid_search_needs_both_legs(
    session: AsyncSession, two_legs: dict[str, Any]
) -> None:
    """Каждая ветвь обязана вносить вклад — и в состав выдачи, и в порядок.

    Снятие лексической ветви: LEX теряет свой вклад и опускается ниже DENSE.
    Снятие плотной: DENSE выпадает из выдачи целиком (по словам он не
    совпадает). Любая из двух мутаций роняет этот тест.
    """
    results = await hybrid_search(
        session,
        query_vector=two_legs["query_vector"],
        query_text=two_legs["query_text"],
        acts=two_legs["acts"],
        limit=10,
    )
    order = [str(r.article_id) for r in results]

    assert set(order) == {two_legs["both"], two_legs["lex"], two_legs["dense"]}, (
        "в выдаче нет статьи, которую находит ровно одна из ветвей"
    )
    assert order == [two_legs["both"], two_legs["lex"], two_legs["dense"]], (
        "фьюжн обязан ставить совпавшего по обеим ветвям выше совпавшего по одной"
    )


@pytest.mark.asyncio(loop_scope="module")
async def test_min_score_filters_off_corpus_query(session: AsyncSession) -> None:
    # With min_score=1.0, no real RRF score can pass — return must be empty.
    zero_vec = [0.0] * 1024
    articles = await hybrid_search(
        session,
        query_vector=zero_vec,
        query_text="blarghaforfh xyz qqq",
        acts=None,
        limit=8,
        min_score=1.0,
    )
    assert articles == []
