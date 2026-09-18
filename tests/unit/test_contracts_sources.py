from uuid import uuid4

from neurolegal.contracts import (
    SourceArticleDetail,
    SourceArticleListItem,
    SourceArticlesResponse,
    SourcesResponse,
    SourceSummary,
)


def test_source_summary_roundtrip() -> None:
    s = SourceSummary(
        source_doc_id="gk-1",
        short_name="ГК РФ",
        full_name="Гражданский кодекс РФ (часть первая)",
        kind="codex",
        branch="Гражданское право",
        redaction=None,
        status="in_corpus",
    )
    assert SourcesResponse(sources=[s]).sources[0].status == "in_corpus"


def test_article_dtos() -> None:
    aid = uuid4()
    item = SourceArticleListItem(article_id=aid, number="1", title="Начала")
    resp = SourceArticlesResponse(source_doc_id="gk-1", short_name="ГК РФ", articles=[item])
    detail = SourceArticleDetail(
        article_id=aid, act_short_name="ГК РФ", number="1", title="Начала", full_text="…"
    )
    assert resp.articles[0].number == "1"
    assert detail.full_text == "…"
