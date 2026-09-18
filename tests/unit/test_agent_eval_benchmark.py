from uuid import uuid4

import pytest

from neurolegal.agent.eval.benchmark import (
    BenchmarkCase,
    ExpectedCitation,
    score_case,
    summarize,
)
from neurolegal.contracts import SearchedArticle


def _article(act: str, number: str, score: float = 0.1) -> SearchedArticle:
    return SearchedArticle(
        article_id=str(uuid4()),
        act_short_name=act,
        act_kind="codex",
        number=number,
        title="Заголовок",
        full_text="текст",
        matched_chunks=[],
        score=score,
    )


def test_score_case_counts_exact_citation_recall_and_rank() -> None:
    case = BenchmarkCase(
        id="x",
        question="q",
        expected=(ExpectedCitation("ГК РФ", "128"), ExpectedCitation("ГК РФ", "129")),
    )

    score = score_case(case, [_article("ТК РФ", "57"), _article("ГК РФ", "128")])

    assert score.citation_recall == 0.5
    assert score.act_recall == 1.0
    assert score.reciprocal_rank == 0.5


def test_summarize_averages_scores() -> None:
    first = score_case(
        BenchmarkCase("a", "q1", (ExpectedCitation("ВК РФ", "3"),)),
        [_article("ВК РФ", "3", 0.2)],
    )
    second = score_case(
        BenchmarkCase("b", "q2", (ExpectedCitation("ТК РФ", "57"),)),
        [_article("ГК РФ", "128", 0.4)],
    )

    report = summarize([first, second])

    assert report.citation_recall == 0.5
    assert report.act_recall == 0.5
    assert report.mrr == 0.5
    assert report.top_score_avg == pytest.approx(0.3)
