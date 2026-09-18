"""Unit tests for the fetch_article tool handler."""

from uuid import uuid4

import pytest

from neurolegal.agent.chat.tools.base import ToolContext
from neurolegal.agent.chat.tools.fetch_article import FETCH_ARTICLE_TOOL, handle
from neurolegal.agent.tools.rag_client import RagClientError
from neurolegal.contracts import SearchedArticle, ToolsSettings


def _article(number: str, act: str = "ГК РФ") -> SearchedArticle:
    return SearchedArticle(
        article_id=uuid4(),
        act_short_name=act,
        act_kind="codex",
        number=number,
        title="Товарные знаки",
        full_text="полный текст статьи",
        matched_chunks=[],
        score=0.9,
    )


class _FakeRag:
    def __init__(
        self,
        articles: list[SearchedArticle] | None = None,
        fail: bool = False,
    ) -> None:
        self._articles = articles or []
        self._fail = fail
        self.called: bool = False

    async def search(self, query, *, acts=None, limit=8, min_score=None):  # type: ignore[no-untyped-def]
        raise NotImplementedError("not used in fetch_article tests")

    async def fetch_article(self, act: str, number: str) -> list[SearchedArticle]:
        self.called = True
        if self._fail:
            raise RagClientError("RAG down")
        return self._articles


def _ctx(acts: list[str] | None = None, fake: _FakeRag | None = None) -> ToolContext:
    return ToolContext(
        rag_client=fake or _FakeRag(),  # type: ignore[arg-type]
        acts=acts,
        tools=ToolsSettings(),
    )


@pytest.mark.asyncio
async def test_tool_spec_shape() -> None:
    assert FETCH_ARTICLE_TOOL.name == "fetch_article"
    props = FETCH_ARTICLE_TOOL.parameters["properties"]
    assert "act" in props
    assert "number" in props
    assert FETCH_ARTICLE_TOOL.parameters["required"] == ["act", "number"]


@pytest.mark.asyncio
async def test_returns_articles() -> None:
    art = _article("1477")
    fake = _FakeRag(articles=[art])
    ctx = _ctx(fake=fake)

    out = await handle({"act": "ГК РФ", "number": "1477"}, ctx)

    assert out.articles != []
    assert "1477" in out.tool_result


@pytest.mark.asyncio
async def test_missing_act_arg() -> None:
    fake = _FakeRag(articles=[_article("1")])
    ctx = _ctx(fake=fake)

    out = await handle({"act": "", "number": "1"}, ctx)

    assert out.articles == []
    assert "error" in out.tool_result
    assert not fake.called


@pytest.mark.asyncio
async def test_missing_number_arg() -> None:
    fake = _FakeRag(articles=[_article("1")])
    ctx = _ctx(fake=fake)

    out = await handle({"act": "ГК РФ", "number": ""}, ctx)

    assert out.articles == []
    assert "error" in out.tool_result
    assert not fake.called


@pytest.mark.asyncio
async def test_act_not_in_filter() -> None:
    """When ctx.acts is set, requesting an act outside the filter must be refused
    without calling the RAG client."""
    fake = _FakeRag(articles=[_article("1", act="ГК РФ")])
    ctx = _ctx(acts=["ВК РФ"], fake=fake)

    out = await handle({"act": "ГК РФ", "number": "1"}, ctx)

    assert not fake.called
    assert out.articles == []
    assert "error" in out.tool_result


@pytest.mark.asyncio
async def test_act_in_filter_allowed() -> None:
    """When ctx.acts contains the requested act, the call goes through."""
    art = _article("1477", act="ГК РФ")
    fake = _FakeRag(articles=[art])
    ctx = _ctx(acts=["ГК РФ", "ВК РФ"], fake=fake)

    out = await handle({"act": "ГК РФ", "number": "1477"}, ctx)

    assert fake.called
    assert out.articles != []


@pytest.mark.asyncio
async def test_no_filter_means_all_acts_allowed() -> None:
    """ctx.acts = None means no filter — all acts are reachable."""
    art = _article("42", act="КоАП РФ")
    fake = _FakeRag(articles=[art])
    ctx = _ctx(acts=None, fake=fake)

    out = await handle({"act": "КоАП РФ", "number": "42"}, ctx)

    assert fake.called
    assert out.articles != []


@pytest.mark.asyncio
async def test_unavailable() -> None:
    fake = _FakeRag(fail=True)
    ctx = _ctx(fake=fake)

    out = await handle({"act": "ГК РФ", "number": "1477"}, ctx)

    assert out.unavailable is True
    assert out.articles == []


@pytest.mark.asyncio
async def test_empty_result_from_client() -> None:
    fake = _FakeRag(articles=[])
    ctx = _ctx(fake=fake)

    out = await handle({"act": "ГК РФ", "number": "9999"}, ctx)

    assert out.articles == []
    assert "articles" in out.tool_result
    assert out.unavailable is False
