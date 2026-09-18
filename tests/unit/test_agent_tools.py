"""Тесты `rag_search` — БОЕВОГО пути (T-0102, пункт 2).

Раньше файл целиком адресовал `run_rag_search`, которую прод не вызывал:
реестр вызывает `handle_rag_search`, и сломать этот хендлер наглухо можно
было, не уронив ни одного из 52 тестов группы. Legacy-функция и её
реэкспорт удалены, тесты перенацелены на реальный хендлер.
"""

from typing import cast
from uuid import uuid4

import pytest

from neurolegal.agent.chat.tools import RAG_SEARCH_TOOL, handle_rag_search
from neurolegal.agent.chat.tools.base import ToolContext
from neurolegal.agent.tools.rag_client import RagClient, RagClientError
from neurolegal.contracts import (
    SEARCH_QUERY_MAX_CHARS,
    RagSearchSettings,
    SearchedArticle,
    ToolsSettings,
)


def _article(number: str) -> SearchedArticle:
    return SearchedArticle(
        article_id=uuid4(),
        act_short_name="ВК РФ",
        act_kind="codex",
        number=number,
        title="Заголовок",
        full_text="полный текст статьи",
        matched_chunks=[],
        score=0.04,
    )


class _FakeRag:
    def __init__(self, articles: list[SearchedArticle], fail: bool = False) -> None:
        self._articles = articles
        self._fail = fail
        self.calls: list[dict[str, object]] = []
        self.last_query: str | None = None
        self.last_acts: list[str] | None = None

    async def search(self, query, *, acts=None, limit=8, min_score=None):  # type: ignore[no-untyped-def]
        self.calls.append({"query": query, "acts": acts, "limit": limit, "min_score": min_score})
        if self._fail:
            raise RagClientError("down")
        self.last_query = query
        self.last_acts = acts
        return self._articles


def _ctx(
    rag: _FakeRag,
    *,
    acts: list[str] | None = None,
    limit: int = 8,
    min_score: float = 0.0,
) -> ToolContext:
    return ToolContext(
        rag_client=cast(RagClient, rag),
        acts=acts,
        tools=ToolsSettings(rag_search=RagSearchSettings(limit=limit, min_score=min_score)),
    )


def test_tool_schema_shape() -> None:
    assert RAG_SEARCH_TOOL.name == "rag_search"
    params = RAG_SEARCH_TOOL.parameters
    assert params["required"] == ["query"]
    assert set(params["properties"]) == {"query"}  # acts removed — user controls scope


@pytest.mark.asyncio
async def test_applies_caller_acts() -> None:
    rag = _FakeRag([_article("3"), _article("5")])
    outcome = await handle_rag_search({"query": "налог"}, _ctx(rag, acts=["ГК РФ"]))

    assert [a.number for a in outcome.articles] == ["3", "5"]
    assert outcome.unavailable is False
    assert rag.last_query == "налог"
    assert rag.last_acts == ["ГК РФ"]


@pytest.mark.asyncio
async def test_ignores_acts_in_arguments() -> None:
    """Область поиска задаёт пользователь, не модель.

    Схема тулзы не объявляет `acts`, но модель может их выдумать. Если
    хендлер начнёт их читать (`arguments.get("acts") or ctx.acts`), ответ
    уедет за пределы выбранных пользователем источников.
    """
    rag = _FakeRag([_article("3")])
    await handle_rag_search({"query": "налог", "acts": ["КоАП РФ"]}, _ctx(rag, acts=["ГК РФ"]))
    assert rag.last_acts == ["ГК РФ"]


@pytest.mark.asyncio
async def test_no_acts_means_no_filter() -> None:
    rag = _FakeRag([_article("3")])
    await handle_rag_search({"query": "налог"}, _ctx(rag, acts=None))
    assert rag.last_acts is None


@pytest.mark.asyncio
async def test_empty_query_never_reaches_rag() -> None:
    rag = _FakeRag([])
    outcome = await handle_rag_search({"query": "   "}, _ctx(rag))
    assert outcome.articles == []
    assert "empty query" in outcome.tool_result
    assert rag.calls == []


@pytest.mark.asyncio
async def test_rag_failure_is_reported_as_unavailable() -> None:
    """`unavailable=True` — то, по чему агент отличает «поиск лёг» от
    «норм не нашлось»; на нём висит выбор ноты в ответе пользователю."""
    rag = _FakeRag([], fail=True)
    outcome = await handle_rag_search({"query": "налог"}, _ctx(rag))
    assert outcome.articles == []
    assert outcome.unavailable is True
    assert "search unavailable" in outcome.tool_result


@pytest.mark.asyncio
async def test_clamps_oversize_query() -> None:
    """An over-limit LLM query must be clamped, not 422 on the RAG side."""
    rag = _FakeRag([_article("3")])
    await handle_rag_search({"query": "ы" * (SEARCH_QUERY_MAX_CHARS + 200)}, _ctx(rag))
    assert rag.last_query is not None
    assert len(rag.last_query) == SEARCH_QUERY_MAX_CHARS


@pytest.mark.asyncio
async def test_rejects_non_string_query() -> None:
    rag = _FakeRag([_article("3")])
    outcome = await handle_rag_search({"query": None}, _ctx(rag))
    assert outcome.articles == []
    assert "empty query" in outcome.tool_result
    assert rag.calls == []  # RAG был не вызван


@pytest.mark.asyncio
async def test_forwards_limit_and_min_score_from_settings() -> None:
    rag = _FakeRag([])
    await handle_rag_search({"query": "тест"}, _ctx(rag, limit=5, min_score=0.2))
    assert rag.calls[0]["limit"] == 5
    assert rag.calls[0]["min_score"] == 0.2


@pytest.mark.asyncio
async def test_zero_min_score_is_passed_as_none() -> None:
    """0.0 — «фильтр выключен»; передавать это значение как есть значит
    просить RAG отфильтровать по нулевому порогу вместо отказа от фильтра."""
    rag = _FakeRag([])
    await handle_rag_search({"query": "тест"}, _ctx(rag, min_score=0.0))
    assert rag.calls[0]["min_score"] is None
