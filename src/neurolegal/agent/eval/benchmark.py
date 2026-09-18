"""Small retrieval benchmark for the legal-research agent.

The benchmark is intentionally modest and transparent: it checks whether the
retrieval layer surfaces expected act/article pairs for common Russian-law
questions. It does not judge the generated prose; it gives us a repeatable
signal before running expensive end-to-end LLM checks.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from neurolegal.contracts import SearchedArticle


@dataclass(frozen=True)
class ExpectedCitation:
    act_short_name: str
    number: str


@dataclass(frozen=True)
class BenchmarkCase:
    id: str
    question: str
    expected: tuple[ExpectedCitation, ...]
    tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class CaseScore:
    case_id: str
    question: str
    expected: tuple[ExpectedCitation, ...]
    found: tuple[ExpectedCitation, ...]
    citation_recall: float
    act_recall: float
    reciprocal_rank: float
    top_score: float | None


@dataclass(frozen=True)
class BenchmarkReport:
    cases: tuple[CaseScore, ...]
    citation_recall: float
    act_recall: float
    mrr: float
    top_score_avg: float | None


DEFAULT_CASES: tuple[BenchmarkCase, ...] = (
    BenchmarkCase(
        id="water-principles",
        question="Какие основные принципы водного законодательства?",
        expected=(ExpectedCitation("ВК РФ", "3"),),
        tags=("environment", "codex"),
    ),
    BenchmarkCase(
        id="admin-liability-age",
        question="С какого возраста наступает административная ответственность?",
        expected=(ExpectedCitation("КоАП РФ", "2.3"),),
        tags=("administrative", "direct"),
    ),
    BenchmarkCase(
        id="civil-rights-objects",
        question="Что относится к объектам гражданских прав?",
        expected=(ExpectedCitation("ГК РФ", "128"),),
        tags=("civil", "direct"),
    ),
    BenchmarkCase(
        id="consumer-return",
        question="Когда потребитель может обменять непродовольственный товар надлежащего качества?",
        expected=(ExpectedCitation("2300-1 «О защите прав потребителей»", "25"),),
        tags=("consumer", "federal_law"),
    ),
    BenchmarkCase(
        id="llc-registration-docs",
        question="Какие документы подаются при государственной регистрации создаваемого юридического лица?",
        expected=(ExpectedCitation("129-ФЗ", "12"),),
        tags=("corporate", "federal_law"),
    ),
    BenchmarkCase(
        id="employment-contract",
        question="Что должно быть включено в трудовой договор?",
        expected=(ExpectedCitation("ТК РФ", "57"),),
        tags=("labor", "direct"),
    ),
)


def citation_key(citation: ExpectedCitation) -> tuple[str, str]:
    return (citation.act_short_name, citation.number)


def article_to_expected(article: SearchedArticle) -> ExpectedCitation:
    return ExpectedCitation(article.act_short_name, article.number)


def _recall(expected: set[tuple[str, str]], found: set[tuple[str, str]]) -> float:
    if not expected:
        return 1.0
    return len(expected & found) / len(expected)


def _act_recall(expected: Iterable[ExpectedCitation], found: Iterable[ExpectedCitation]) -> float:
    expected_acts = {c.act_short_name for c in expected}
    found_acts = {c.act_short_name for c in found}
    if not expected_acts:
        return 1.0
    return len(expected_acts & found_acts) / len(expected_acts)


def score_case(case: BenchmarkCase, articles: Sequence[SearchedArticle]) -> CaseScore:
    found = tuple(article_to_expected(a) for a in articles)
    expected_keys = {citation_key(c) for c in case.expected}
    found_keys = {citation_key(c) for c in found}

    reciprocal_rank = 0.0
    for idx, citation in enumerate(found, start=1):
        if citation_key(citation) in expected_keys:
            reciprocal_rank = 1.0 / idx
            break

    top_score = articles[0].score if articles else None
    return CaseScore(
        case_id=case.id,
        question=case.question,
        expected=case.expected,
        found=found,
        citation_recall=_recall(expected_keys, found_keys),
        act_recall=_act_recall(case.expected, found),
        reciprocal_rank=reciprocal_rank,
        top_score=top_score,
    )


def summarize(scores: Sequence[CaseScore]) -> BenchmarkReport:
    if not scores:
        return BenchmarkReport(
            cases=(), citation_recall=0.0, act_recall=0.0, mrr=0.0, top_score_avg=None
        )

    top_scores = [s.top_score for s in scores if s.top_score is not None]
    return BenchmarkReport(
        cases=tuple(scores),
        citation_recall=sum(s.citation_recall for s in scores) / len(scores),
        act_recall=sum(s.act_recall for s in scores) / len(scores),
        mrr=sum(s.reciprocal_rank for s in scores) / len(scores),
        top_score_avg=(sum(top_scores) / len(top_scores)) if top_scores else None,
    )
