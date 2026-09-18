"""Tests for ReviewEngine stages 1-5: mapping, assessment, grounding, judge, report."""

import asyncio
from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import pytest

from neurolegal.agent.chat.events import ReviewProgressEvent, ReviewReportEvent
from neurolegal.agent.llm.types import ChatMessage, LLMEvent, TextChunk, ToolCallRequest, ToolSpec
from neurolegal.agent.review.engine import (
    ASSESS_SYSTEM,
    ASSESS_SYSTEM_BY_KIND,
    MAP_SYSTEM,
    MAP_SYSTEM_BY_KIND,
    SUMMARY_SYSTEM,
    SUMMARY_SYSTEM_BY_KIND,
    ReviewEngine,
    ReviewEngineError,
)
from neurolegal.agent.review.playbook import Playbook, PlaybookRule
from neurolegal.agent.tools.rag_client import RagClientError
from neurolegal.contracts import SearchedArticle

PB = Playbook.model_validate(
    {
        "id": "t",
        "name": "Т",
        "rules": [
            {
                "id": "pay",
                "title": "Оплата",
                "question": "Срок оплаты?",
                "rag_queries": ["оплата"],
            },
            {
                "id": "ip",
                "title": "ИС",
                "question": "Права на РИД?",
                "risk_if_missing": "medium",
            },
        ],
    }
)
SECTIONS: list[dict[str, object]] = [
    {
        "number": "1",
        "title": "Оплата",
        "text": "1. Оплата в течение 90 дней после продажи третьим лицам.",
        "level": 1,
        "start": 0,
        "end": 50,
    },
]


class FakeLLM:
    """Очередь заранее заданных ответов; каждый ответ — список LLMEvent."""

    def __init__(self, scripted: list[list[LLMEvent]]) -> None:
        self._scripted = list(scripted)
        self.calls: list[tuple[list[ChatMessage], list[ToolSpec]]] = []

    async def stream(
        self, messages: list[ChatMessage], tools: list[ToolSpec]
    ) -> AsyncIterator[LLMEvent]:
        self.calls.append((messages, tools))
        for ev in self._scripted.pop(0):
            yield ev


def _tc(name: str, args: dict[str, object]) -> ToolCallRequest:
    return ToolCallRequest(id="x", name=name, arguments=args)


async def _collect(
    engine: ReviewEngine, playbook: Playbook, sections: list[dict[str, object]]
) -> list[object]:
    return [ev async for ev in engine.run(playbook, "doc1", sections)]


class FakeRag:
    """Duck-types `RagClient.search(query, *, acts=None, limit=8, min_score=None)`."""

    def __init__(self, articles: list[SearchedArticle]) -> None:
        self._articles = articles
        self.queries: list[str] = []

    async def search(
        self,
        query: str,
        *,
        acts: list[str] | None = None,
        limit: int = 8,
        min_score: float | None = None,
    ) -> list[SearchedArticle]:
        self.queries.append(query)
        return self._articles


def _article(
    number: str = "781", act: str = "ГК РФ", article_id: UUID | None = None
) -> SearchedArticle:
    return SearchedArticle(
        article_id=article_id or uuid4(),
        act_short_name=act,
        act_kind="codex",
        number=number,
        title="Оплата услуг",
        full_text="Заказчик обязан оплатить услуги в установленный договором срок.",
        matched_chunks=[],
        score=0.9,
    )


async def test_missing_rule_becomes_risk_without_llm() -> None:
    llm = FakeLLM(
        [
            [
                _tc(
                    "map_rules",
                    {
                        "mapping": [
                            {"rule_id": "pay", "section_numbers": ["1"]},
                            {"rule_id": "ip", "section_numbers": []},
                        ]
                    },
                )
            ],
            [
                _tc(
                    "assess_rule",
                    {
                        "status": "risk",
                        "risk_level": "high",
                        "quote": "в течение 90 дней после продажи",
                        "explanation": "Оплата зависит от третьих лиц",
                        "recommendation": "Фиксированный срок",
                    },
                )
            ],
            # judge-вызовы появятся в Task 10; здесь judge отключён параметром
        ]
    )
    engine = ReviewEngine(llm=llm, rag_client=None, judge_enabled=False)  # type: ignore[arg-type]
    events = await _collect(engine, PB, SECTIONS)
    report = next(e for e in events if isinstance(e, ReviewReportEvent)).report
    assert {r.rule_id for r in report.risks} == {"pay", "ip"}
    ip_risk = next(r for r in report.risks if r.rule_id == "ip")
    assert ip_risk.level == "medium" and "не найдена" in ip_risk.explanation
    assert ip_risk.section_number is None
    assert ip_risk.verdict == "confirmed"
    pay_risk = next(r for r in report.risks if r.rule_id == "pay")
    assert pay_risk.level == "high" and pay_risk.section_number == "1"
    coverage = {c.rule_id: c.status for c in report.coverage}
    assert coverage == {"pay": "risk", "ip": "missing"}
    progress = [e for e in events if isinstance(e, ReviewProgressEvent)]
    assert progress and progress[-1].total == 2
    # each rule fires a "running" progress event followed by its final status
    assert [p.status for p in progress] == ["running", "risk", "running", "missing"]


async def test_structured_retry_then_error() -> None:
    llm = FakeLLM([[TextChunk(text="болтовня")], [TextChunk(text="опять")]])
    engine = ReviewEngine(llm=llm, rag_client=None, judge_enabled=False)  # type: ignore[arg-type]
    with pytest.raises(ReviewEngineError):
        await _collect(engine, PB, SECTIONS)
    assert len(llm.calls) == 2


async def test_rule_without_match_and_without_risk_if_missing_is_not_applicable() -> None:
    pb = Playbook.model_validate(
        {
            "id": "t2",
            "name": "Т2",
            "rules": [
                {"id": "misc", "title": "Прочее", "question": "Есть ли пункт X?"},
            ],
        }
    )
    llm = FakeLLM(
        [
            [_tc("map_rules", {"mapping": [{"rule_id": "misc", "section_numbers": []}]})],
        ]
    )
    engine = ReviewEngine(llm=llm, rag_client=None, judge_enabled=False)  # type: ignore[arg-type]
    events = await _collect(engine, pb, SECTIONS)
    report = next(e for e in events if isinstance(e, ReviewReportEvent)).report
    assert report.risks == []
    assert {c.rule_id: c.status for c in report.coverage} == {"misc": "not_applicable"}


async def test_assess_status_ok_produces_no_risk() -> None:
    pb = Playbook.model_validate(
        {
            "id": "t3",
            "name": "Т3",
            "rules": [
                {"id": "pay", "title": "Оплата", "question": "Срок оплаты?"},
            ],
        }
    )
    llm = FakeLLM(
        [
            [_tc("map_rules", {"mapping": [{"rule_id": "pay", "section_numbers": ["1"]}]})],
            [
                _tc(
                    "assess_rule",
                    {"status": "ok", "explanation": "Срок закреплён и не зависит от третьих лиц"},
                )
            ],
        ]
    )
    engine = ReviewEngine(llm=llm, rag_client=None, judge_enabled=False)  # type: ignore[arg-type]
    events = await _collect(engine, pb, SECTIONS)
    report = next(e for e in events if isinstance(e, ReviewReportEvent)).report
    assert report.risks == []
    assert {c.rule_id: c.status for c in report.coverage} == {"pay": "ok"}


async def test_invalid_tool_arguments_trigger_retry_then_error() -> None:
    # missing required "rule_id" key inside mapping entries -> Pydantic
    # validation fails, counted as a failed attempt just like no tool-call.
    llm = FakeLLM(
        [
            [_tc("map_rules", {"mapping": [{"section_numbers": ["1"]}]})],
            [_tc("map_rules", {"mapping": [{"section_numbers": ["1"]}]})],
        ]
    )
    engine = ReviewEngine(llm=llm, rag_client=None, judge_enabled=False)  # type: ignore[arg-type]
    with pytest.raises(ReviewEngineError):
        await _collect(engine, PB, SECTIONS)
    assert len(llm.calls) == 2


async def test_judge_selects_citations_by_index() -> None:
    llm = FakeLLM(
        [
            [
                _tc(
                    "map_rules",
                    {
                        "mapping": [
                            {"rule_id": "pay", "section_numbers": ["1"]},
                            {"rule_id": "ip", "section_numbers": []},
                        ]
                    },
                )
            ],
            [
                _tc(
                    "assess_rule",
                    {
                        "status": "risk",
                        "risk_level": "high",
                        "quote": "90 дней",
                        "explanation": "зависимость от третьих лиц",
                        "recommendation": "фикс. срок",
                    },
                )
            ],
            [
                _tc("judge_risk", {"verdict": "confirmed", "citation_indexes": [1, 99]})
            ],  # 99 — вне диапазона
        ]
    )
    rag = FakeRag([_article()])
    engine = ReviewEngine(llm=llm, rag_client=rag)  # judge включён по умолчанию
    events = await _collect(engine, PB, SECTIONS)
    report = next(e for e in events if isinstance(e, ReviewReportEvent)).report
    pay = next(r for r in report.risks if r.rule_id == "pay")
    assert [c.number for c in pay.citations] == ["781"]  # 99 отброшен валидатором
    assert pay.no_basis is False
    assert rag.queries == ["оплата"]


def _three_articles() -> list[SearchedArticle]:
    """Три статьи — минимум, на котором привязка индекс→статья проверяема.

    Прежние фикстуры судьи содержали ровно одну статью, поэтому мутация
    `articles[i - 1]` → `articles[0]` не роняла ничего.
    """
    return [_article("781"), _article("314"), _article("395")]


def _map_and_assess_script() -> list[list[LLMEvent]]:
    """Скрипт LLM до стадии judge: map_rules + assess_rule для правила pay."""
    return [
        [
            _tc(
                "map_rules",
                {
                    "mapping": [
                        {"rule_id": "pay", "section_numbers": ["1"]},
                        {"rule_id": "ip", "section_numbers": []},
                    ]
                },
            )
        ],
        [
            _tc(
                "assess_rule",
                {
                    "status": "risk",
                    "risk_level": "high",
                    "quote": "90 дней",
                    "explanation": "зависимость от третьих лиц",
                    "recommendation": "фикс. срок",
                },
            )
        ],
    ]


async def test_judge_binds_citation_to_the_indexed_article() -> None:
    """Индекс из вердикта обязан указывать на СВОЮ статью (T-0102, пункт 1)."""
    llm = FakeLLM(
        [
            *_map_and_assess_script(),
            [_tc("judge_risk", {"verdict": "confirmed", "citation_indexes": [2]})],
        ]
    )
    engine = ReviewEngine(llm=llm, rag_client=FakeRag(_three_articles()))
    events = await _collect(engine, PB, SECTIONS)
    report = next(e for e in events if isinstance(e, ReviewReportEvent)).report
    pay = next(r for r in report.risks if r.rule_id == "pay")
    assert [c.number for c in pay.citations] == ["314"]


async def test_judge_drops_out_of_range_indexes_on_both_ends() -> None:
    """0 и отрицательные — тоже вне диапазона.

    Без нижней границы индекс 0 превращается в `articles[-1]`, то есть риск
    получает цитату на ПОСЛЕДНЮЮ найденную статью — вместо отброшенной.
    """
    llm = FakeLLM(
        [
            *_map_and_assess_script(),
            [_tc("judge_risk", {"verdict": "confirmed", "citation_indexes": [0, -1, 3, 99]})],
        ]
    )
    engine = ReviewEngine(llm=llm, rag_client=FakeRag(_three_articles()))
    events = await _collect(engine, PB, SECTIONS)
    report = next(e for e in events if isinstance(e, ReviewReportEvent)).report
    pay = next(r for r in report.risks if r.rule_id == "pay")
    assert [c.number for c in pay.citations] == ["395"]  # уцелел только индекс 3


async def test_overstated_verdict_keeps_the_risk() -> None:
    """overstated — «риск преувеличен, но не снят», это не not_a_risk.

    Уравнять их значит молча потерять риск из отчёта и переключить покрытие
    правила в «ok» — пользователь увидит договор чище, чем он есть.
    """
    llm = FakeLLM(
        [
            *_map_and_assess_script(),
            [_tc("judge_risk", {"verdict": "overstated", "citation_indexes": [1]})],
        ]
    )
    engine = ReviewEngine(llm=llm, rag_client=FakeRag(_three_articles()))
    events = await _collect(engine, PB, SECTIONS)
    report = next(e for e in events if isinstance(e, ReviewReportEvent)).report
    pay = next(r for r in report.risks if r.rule_id == "pay")
    assert pay.verdict == "overstated"
    assert [c.number for c in pay.citations] == ["781"]
    assert {c.rule_id: c.status for c in report.coverage}["pay"] != "ok"


async def test_judge_failure_keeps_the_risk_flagged_no_basis() -> None:
    """Отказ судьи не имеет права стирать подтверждённый риск (T-0102, п.1).

    Это самая дорогая из найденных мутаций: `return None` в обработке сбоя
    убирает high-риск из отчёта, переключает покрытие правила в «ok» и
    отдаёт отчёт как успешный — «рисков нет» вместо «не смог проверить».
    Докстринг `_ground_and_judge` обещает ровно обратное.

    Судья не возвращает валидный tool call дважды подряд (`_structured`
    делает две попытки) — это и есть ReviewEngineError на живом пути.
    """
    llm = FakeLLM(
        [
            *_map_and_assess_script(),
            [TextChunk(text="не могу разобрать")],  # попытка 1: нет tool call
            [TextChunk(text="и снова не могу")],  # попытка 2 — после неё ReviewEngineError
            [TextChunk(text="Резюме")],  # стадия резюме продолжает работать
        ]
    )
    engine = ReviewEngine(llm=llm, rag_client=FakeRag(_three_articles()))
    events = await _collect(engine, PB, SECTIONS)
    report = next(e for e in events if isinstance(e, ReviewReportEvent)).report

    pay = next((r for r in report.risks if r.rule_id == "pay"), None)
    assert pay is not None, "риск не имеет права исчезнуть из-за сбоя судьи"
    assert pay.no_basis is True
    assert pay.citations == []
    assert pay.level == "high"  # оценка стадии assess сохранена как есть
    assert {c.rule_id: c.status for c in report.coverage}["pay"] != "ok"


async def test_not_a_risk_flips_coverage_to_ok() -> None:
    llm = FakeLLM(
        [
            [
                _tc(
                    "map_rules",
                    {
                        "mapping": [
                            {"rule_id": "pay", "section_numbers": ["1"]},
                            {"rule_id": "ip", "section_numbers": []},
                        ]
                    },
                )
            ],
            [
                _tc(
                    "assess_rule",
                    {
                        "status": "risk",
                        "risk_level": "low",
                        "quote": "х",
                        "explanation": "спорно",
                        "recommendation": "",
                    },
                )
            ],
            [_tc("judge_risk", {"verdict": "not_a_risk", "citation_indexes": []})],
        ]
    )
    engine = ReviewEngine(llm=llm, rag_client=FakeRag([]))
    events = await _collect(engine, PB, SECTIONS)
    report = next(e for e in events if isinstance(e, ReviewReportEvent)).report
    assert all(r.rule_id != "pay" for r in report.risks)
    coverage = {c.rule_id: c.status for c in report.coverage}
    assert coverage["pay"] == "ok"


async def test_rule_without_rag_queries_marks_risk_no_basis_and_skips_judge() -> None:
    """A risk from a rule with no rag_queries cannot be grounded — it must be
    flagged no_basis=True and the judge must never be called."""
    pb = Playbook.model_validate(
        {
            "id": "nq",
            "name": "НБ",
            "rules": [
                {"id": "pay", "title": "Оплата", "question": "Срок оплаты?"},  # no rag_queries
            ],
        }
    )
    llm = FakeLLM(
        [
            [_tc("map_rules", {"mapping": [{"rule_id": "pay", "section_numbers": ["1"]}]})],
            [
                _tc(
                    "assess_rule",
                    {
                        "status": "risk",
                        "risk_level": "high",
                        "quote": "90 дней",
                        "explanation": "зависимость от третьих лиц",
                        "recommendation": "фикс. срок",
                    },
                )
            ],
            # no judge_risk script entry: if the judge is called, pop(0) raises
        ]
    )
    engine = ReviewEngine(llm=llm, rag_client=FakeRag([_article()]))  # judge enabled by default
    events = await _collect(engine, pb, SECTIONS)
    report = next(e for e in events if isinstance(e, ReviewReportEvent)).report
    pay = next(r for r in report.risks if r.rule_id == "pay")
    assert pay.no_basis is True
    assert pay.citations == []
    # map + assess + резюме (T-0047, без инструментов); judge не вызывался
    assert len(llm.calls) == 3
    assert llm.calls[-1][1] == []


async def test_assess_expands_mapped_parent_section_to_child_sections() -> None:
    """Map often returns only the parent section number ("2"), whose text is
    just a heading — the actual clause content lives in child sections
    ("2.1", "2.2"). Assessment must expand "2" to its children, while a
    sibling like "20" (which merely shares the leading digit, not a
    dotted-prefix relationship) must not be pulled in."""
    sections: list[dict[str, object]] = [
        {
            "number": "2",
            "title": "Цена и порядок оплаты",
            "text": "2. Цена и порядок оплаты",
            "level": 1,
            "start": 0,
            "end": 24,
        },
        {
            "number": "2.1",
            "title": "",
            "text": "2.1. Цена договора составляет 100 000 рублей.",
            "level": 2,
            "start": 24,
            "end": 70,
        },
        {
            "number": "2.2",
            "title": "",
            "text": "2.2. Оплата производится в течение 90 дней после продажи третьим лицам.",
            "level": 2,
            "start": 70,
            "end": 140,
        },
        {
            "number": "20",
            "title": "Прочие условия",
            "text": "20. Прочие условия — форс-мажор и подсудность.",
            "level": 1,
            "start": 140,
            "end": 190,
        },
    ]
    llm = FakeLLM(
        [
            [
                _tc(
                    "map_rules",
                    {
                        "mapping": [
                            {"rule_id": "pay", "section_numbers": ["2"]},
                            {"rule_id": "ip", "section_numbers": []},
                        ]
                    },
                )
            ],
            [
                _tc(
                    "assess_rule",
                    {
                        "status": "risk",
                        "risk_level": "high",
                        "quote": "в течение 90 дней после продажи",
                        "explanation": "Оплата зависит от третьих лиц",
                        "recommendation": "Фиксированный срок",
                    },
                )
            ],
        ]
    )
    engine = ReviewEngine(llm=llm, rag_client=None, judge_enabled=False)  # type: ignore[arg-type]
    await _collect(engine, PB, sections)
    assess_user = llm.calls[1][0][-1].content
    assert "2.1" in assess_user
    assert "100 000 рублей" in assess_user
    assert "2.2" in assess_user
    assert "в течение 90 дней после продажи" in assess_user
    assert "форс-мажор и подсудность" not in assess_user  # "20" is not a child of "2"


async def test_rag_outage_keeps_risk_with_no_basis() -> None:
    class DownRag:
        async def search(
            self,
            query: str,
            *,
            acts: list[str] | None = None,
            limit: int = 8,
            min_score: float | None = None,
        ) -> list[SearchedArticle]:
            raise RagClientError("down")

    llm = FakeLLM(
        [
            [
                _tc(
                    "map_rules",
                    {
                        "mapping": [
                            {"rule_id": "pay", "section_numbers": ["1"]},
                            {"rule_id": "ip", "section_numbers": []},
                        ]
                    },
                )
            ],
            [
                _tc(
                    "assess_rule",
                    {
                        "status": "risk",
                        "risk_level": "high",
                        "quote": "90 дней",
                        "explanation": "…",
                        "recommendation": "…",
                    },
                )
            ],
            [_tc("judge_risk", {"verdict": "confirmed", "citation_indexes": []})],
        ]
    )
    engine = ReviewEngine(llm=llm, rag_client=DownRag())
    events = await _collect(engine, PB, SECTIONS)
    report = next(e for e in events if isinstance(e, ReviewReportEvent)).report
    pay = next(r for r in report.risks if r.rule_id == "pay")
    assert pay.no_basis is True and pay.citations == []


async def test_assess_prompt_does_not_duplicate_section_heading() -> None:
    """T-0011: текст секции уже начинается строкой-заголовком («1. Оплата…»),
    движок не должен приклеивать сверху синтезированный «{number}. {title}» —
    иначе LLM видит строку дважды и дословно цитирует дубль в отчёте."""
    pb = Playbook.model_validate(
        {
            "id": "t",
            "name": "Т",
            "rules": [{"id": "pay", "title": "Оплата", "question": "Срок оплаты?"}],
        }
    )
    sections: list[dict[str, object]] = [
        {
            "number": "1",
            "title": "Предмет договора",
            "text": "1. Предмет договора\nПоставщик обязуется поставить товар.",
            "level": 1,
            "start": 0,
            "end": 50,
        },
    ]
    llm = FakeLLM(
        [
            [_tc("map_rules", {"mapping": [{"rule_id": "pay", "section_numbers": ["1"]}]})],
            [_tc("assess_rule", {"status": "ok", "explanation": "ок"})],
        ]
    )
    engine = ReviewEngine(llm=llm, rag_client=None, judge_enabled=False)  # type: ignore[arg-type]
    await _collect(engine, pb, sections)

    assess_user = llm.calls[1][0][-1].content or ""
    assert assess_user.count("1. Предмет договора") == 1


async def test_sentinel_section_ids_do_not_leak_into_report() -> None:
    """T-0011: служебные id секций пайплайна («preamble», «trailing», «pN») —
    внутренние ключи mapping, но не номера секций договора; в отчёте
    section_number должен быть None (UI прячет пустую ссылку)."""
    pb = Playbook.model_validate(
        {
            "id": "t",
            "name": "Т",
            "rules": [
                {"id": "req", "title": "Реквизиты", "question": "Есть реквизиты?"},
                {"id": "pay", "title": "Оплата", "question": "Срок оплаты?"},
            ],
        }
    )
    sections: list[dict[str, object]] = [
        {
            "number": "trailing",
            "title": "Адреса и реквизиты сторон",
            "text": "Адреса и реквизиты сторон\nПоставщик: ООО Ромашка",
            "level": 0,
            "start": 0,
            "end": 50,
        },
        {
            "number": "2",
            "title": "Оплата",
            "text": "2. Оплата\nОплата в течение 10 дней.",
            "level": 1,
            "start": 51,
            "end": 90,
        },
    ]
    llm = FakeLLM(
        [
            [
                _tc(
                    "map_rules",
                    {
                        "mapping": [
                            {"rule_id": "req", "section_numbers": ["trailing"]},
                            {"rule_id": "pay", "section_numbers": ["2"]},
                        ]
                    },
                )
            ],
            [
                _tc(
                    "assess_rule",
                    {
                        "status": "risk",
                        "risk_level": "low",
                        "quote": "Поставщик: ООО Ромашка",
                        "explanation": "…",
                        "recommendation": "…",
                    },
                )
            ],
            [
                _tc(
                    "assess_rule",
                    {
                        "status": "risk",
                        "risk_level": "low",
                        "quote": "10 дней",
                        "explanation": "…",
                        "recommendation": "…",
                    },
                )
            ],
        ]
    )
    engine = ReviewEngine(llm=llm, rag_client=None, judge_enabled=False)  # type: ignore[arg-type]
    events = await _collect(engine, pb, sections)
    report = next(e for e in events if isinstance(e, ReviewReportEvent)).report

    by_rule = {r.rule_id: r for r in report.risks}
    assert by_rule["req"].section_number is None  # сентинел не утёк
    assert by_rule["pay"].section_number == "2"  # настоящий номер остался


# -- T-0042: параллельная оценка правил -------------------------------------


class _SlowLLM:
    """ChatLLM-фейк: после задержки отвечает валидным вызовом инструмента,
    считая число одновременных вызовов (`inflight`/`max_inflight`).

    `rule_ids` предзаполняет ответ стадии map_rules так, чтобы каждое
    правило получило секцию "1" — без этого `_assess` уходил бы в
    `_missing_without_llm` без единого обращения к LLM (все тестовые правила
    ниже заданы через `risk_if_missing`), и параллелизм было бы нечем измерить.
    """

    def __init__(self, rule_ids: list[str], delay: float = 0.02) -> None:
        self.rule_ids = rule_ids
        self.delay = delay
        self.inflight = 0
        self.max_inflight = 0

    async def stream(
        self, messages: list[ChatMessage], tools: list[ToolSpec]
    ) -> AsyncIterator[LLMEvent]:
        self.inflight += 1
        self.max_inflight = max(self.max_inflight, self.inflight)
        try:
            await asyncio.sleep(self.delay)
            tool = tools[0]
            args: dict[str, object]
            if tool.name == "map_rules":
                args = {
                    "mapping": [{"rule_id": rid, "section_numbers": ["1"]} for rid in self.rule_ids]
                }
            elif tool.name == "assess_rule":
                args = {
                    "status": "risk",
                    "risk_level": "high",
                    "quote": "q",
                    "explanation": "e",
                    "recommendation": "r",
                }
            else:  # judge_risk
                args = {"verdict": "confirmed", "citation_indexes": [], "note": ""}
            yield ToolCallRequest(id="1", name=tool.name, arguments=args)
        finally:
            self.inflight -= 1


def _playbook(n: int) -> Playbook:
    return Playbook(
        id="pb",
        name="ПБ",
        rules=[
            PlaybookRule(id=f"r{i}", title=f"Правило {i}", question="?", risk_if_missing="high")
            for i in range(n)
        ],
    )


def _section() -> dict[str, object]:
    return {"number": "1", "title": "t", "text": "x"}


async def test_parallel_respects_concurrency_cap() -> None:
    pb = _playbook(9)
    llm = _SlowLLM(rule_ids=[r.id for r in pb.rules])
    engine = ReviewEngine(llm=llm, rag_client=FakeRag([]), judge_enabled=False, concurrency=3)
    _ = [e async for e in engine.run(pb, "doc", [_section()])]
    assert llm.max_inflight <= 3
    assert llm.max_inflight >= 2  # параллелизм реально был


async def test_parallel_coverage_keeps_playbook_order() -> None:
    pb = _playbook(6)
    llm = _SlowLLM(rule_ids=[r.id for r in pb.rules])
    engine = ReviewEngine(llm=llm, rag_client=FakeRag([]), judge_enabled=False, concurrency=4)
    events = [e async for e in engine.run(pb, "doc", [_section()])]
    report = next(e.report for e in events if isinstance(e, ReviewReportEvent))
    assert [c.rule_id for c in report.coverage] == [f"r{i}" for i in range(6)]


async def test_parallel_finished_progress_monotonic() -> None:
    pb = _playbook(5)
    llm = _SlowLLM(rule_ids=[r.id for r in pb.rules])
    engine = ReviewEngine(llm=llm, rag_client=FakeRag([]), judge_enabled=False, concurrency=4)
    events = [e async for e in engine.run(pb, "doc", [_section()])]
    finished = [e for e in events if isinstance(e, ReviewProgressEvent) and e.status != "running"]
    assert [e.index for e in finished] == [1, 2, 3, 4, 5]
    assert all(e.total == 5 for e in finished)


async def test_role_prefixes_assess_and_judge_user_content_and_sets_report_role() -> None:
    llm = FakeLLM(
        [
            [
                _tc(
                    "map_rules",
                    {
                        "mapping": [
                            {"rule_id": "pay", "section_numbers": ["1"]},
                            {"rule_id": "ip", "section_numbers": []},
                        ]
                    },
                )
            ],
            [
                _tc(
                    "assess_rule",
                    {
                        "status": "risk",
                        "risk_level": "high",
                        "quote": "90 дней",
                        "explanation": "зависимость от третьих лиц",
                        "recommendation": "фикс. срок",
                    },
                )
            ],
            [_tc("judge_risk", {"verdict": "confirmed", "citation_indexes": [1]})],
        ]
    )
    rag = FakeRag([_article()])
    engine = ReviewEngine(llm=llm, rag_client=rag)
    events = [ev async for ev in engine.run(PB, "doc1", SECTIONS, role="Заказчик")]
    report = next(e for e in events if isinstance(e, ReviewReportEvent)).report
    assert report.role == "Заказчик"

    assess_user = llm.calls[1][0][-1].content or ""
    judge_user = llm.calls[2][0][-1].content or ""
    prefix = (
        "Вы оцениваете договор с позиции стороны: Заказчик. Ищите риски именно для этой стороны."
    )
    assert assess_user.startswith(prefix)
    assert judge_user.startswith(prefix)


async def test_no_role_leaves_assess_and_judge_prompts_byte_for_byte() -> None:
    llm = FakeLLM(
        [
            [
                _tc(
                    "map_rules",
                    {
                        "mapping": [
                            {"rule_id": "pay", "section_numbers": ["1"]},
                            {"rule_id": "ip", "section_numbers": []},
                        ]
                    },
                )
            ],
            [
                _tc(
                    "assess_rule",
                    {
                        "status": "risk",
                        "risk_level": "high",
                        "quote": "90 дней",
                        "explanation": "зависимость от третьих лиц",
                        "recommendation": "фикс. срок",
                    },
                )
            ],
            [_tc("judge_risk", {"verdict": "confirmed", "citation_indexes": [1]})],
        ]
    )
    rag = FakeRag([_article()])
    engine = ReviewEngine(llm=llm, rag_client=rag)
    events = [ev async for ev in engine.run(PB, "doc1", SECTIONS)]
    report = next(e for e in events if isinstance(e, ReviewReportEvent)).report
    assert report.role is None

    assess_user = llm.calls[1][0][-1].content or ""
    judge_user = llm.calls[2][0][-1].content or ""
    assert "позиции стороны" not in assess_user
    assert "позиции стороны" not in judge_user
    assert assess_user == (
        "Вопрос: Срок оплаты?\n\n"
        "Текст секций договора:\n"
        "1. Оплата в течение 90 дней после продажи третьим лицам."
    )
    assert judge_user == (
        "Правило: Оплата — Срок оплаты?\n\n"
        "Найденный риск:\n"
        "Цитата из договора: 90 дней\n"
        "Обоснование: зависимость от третьих лиц\n\n"
        "Найденные статьи:\n"
        "[1] ст. 781 ГК РФ — Оплата услуг — "
        "Заказчик обязан оплатить услуги в установленный договором срок."
    )


# -- T-0047: резюме отчёта ---------------------------------------------------


async def test_summary_call_fills_report_summary() -> None:
    """Движок делает финальный текстовый LLM-вызов (не tool-call): роль,
    счётчики уровней и топ-риски на входе — короткое резюме в report.summary
    на выходе."""
    llm = FakeLLM(
        [
            [
                _tc(
                    "map_rules",
                    {
                        "mapping": [
                            {"rule_id": "pay", "section_numbers": ["1"]},
                            {"rule_id": "ip", "section_numbers": []},
                        ]
                    },
                )
            ],
            [
                _tc(
                    "assess_rule",
                    {
                        "status": "risk",
                        "risk_level": "high",
                        "quote": "90 дней",
                        "explanation": "зависимость от третьих лиц",
                        "recommendation": "фикс. срок",
                    },
                )
            ],
            [_tc("judge_risk", {"verdict": "confirmed", "citation_indexes": [1]})],
            [TextChunk(text="Договор в целом рабочий. "), TextChunk(text="Сначала — оплата.")],
        ]
    )
    engine = ReviewEngine(llm=llm, rag_client=FakeRag([_article()]))
    events = [ev async for ev in engine.run(PB, "doc1", SECTIONS, role="Заказчик")]
    report = next(e for e in events if isinstance(e, ReviewReportEvent)).report
    assert report.summary == "Договор в целом рабочий. Сначала — оплата."

    summary_messages, summary_tools = llm.calls[-1]
    assert summary_tools == []  # обычный текстовый вызов, не tool-call
    user = summary_messages[-1].content or ""
    assert "Заказчик" in user
    assert "высокий 1" in user
    assert "средний 1" in user
    assert "Проверено правил: 2" in user
    assert "Оплата" in user  # топ-риск попал в промпт


async def test_summary_llm_failure_leaves_summary_none() -> None:
    """Сбой резюме-вызова не валит отчёт: summary = None, отчёт живёт."""

    class _SummaryDownLLM(FakeLLM):
        async def stream(
            self, messages: list[ChatMessage], tools: list[ToolSpec]
        ) -> AsyncIterator[LLMEvent]:
            if not tools:
                raise RuntimeError("summary down")
            async for ev in super().stream(messages, tools):
                yield ev

    llm = _SummaryDownLLM(
        [
            [_tc("map_rules", {"mapping": [{"rule_id": "pay", "section_numbers": ["1"]}]})],
            [_tc("assess_rule", {"status": "ok", "explanation": "ок"})],
        ]
    )
    pb = Playbook.model_validate(
        {"id": "t", "name": "Т", "rules": [{"id": "pay", "title": "Оплата", "question": "?"}]}
    )
    engine = ReviewEngine(llm=llm, rag_client=None, judge_enabled=False)  # type: ignore[arg-type]
    events = await _collect(engine, pb, SECTIONS)
    report = next(e for e in events if isinstance(e, ReviewReportEvent)).report
    assert report.summary is None
    assert {c.rule_id: c.status for c in report.coverage} == {"pay": "ok"}


async def test_summary_blank_text_is_none() -> None:
    """Пустой/пробельный ответ резюме — то же, что сбой: summary = None."""
    llm = FakeLLM(
        [
            [_tc("map_rules", {"mapping": [{"rule_id": "pay", "section_numbers": ["1"]}]})],
            [_tc("assess_rule", {"status": "ok", "explanation": "ок"})],
            [TextChunk(text="  \n")],
        ]
    )
    pb = Playbook.model_validate(
        {"id": "t", "name": "Т", "rules": [{"id": "pay", "title": "Оплата", "question": "?"}]}
    )
    engine = ReviewEngine(llm=llm, rag_client=None, judge_enabled=False)  # type: ignore[arg-type]
    events = await _collect(engine, pb, SECTIONS)
    report = next(e for e in events if isinstance(e, ReviewReportEvent)).report
    assert report.summary is None


async def test_parallel_worker_error_aborts_run() -> None:
    class _BoomLLM(_SlowLLM):
        async def stream(
            self, messages: list[ChatMessage], tools: list[ToolSpec]
        ) -> AsyncIterator[LLMEvent]:
            if tools[0].name == "assess_rule":
                raise RuntimeError("boom")
            async for ev in super().stream(messages, tools):
                yield ev

    pb = _playbook(3)
    llm = _BoomLLM(rule_ids=[r.id for r in pb.rules])
    engine = ReviewEngine(llm=llm, rag_client=FakeRag([]), judge_enabled=False, concurrency=4)
    with pytest.raises(RuntimeError):
        _ = [e async for e in engine.run(pb, "doc", [_section()])]


# -- E10: prompt sets by doc_kind --------------------------------------------


def test_contract_prompts_unchanged() -> None:
    assert MAP_SYSTEM_BY_KIND["contract"] is MAP_SYSTEM
    assert ASSESS_SYSTEM_BY_KIND["contract"] is ASSESS_SYSTEM
    assert SUMMARY_SYSTEM_BY_KIND["contract"] is SUMMARY_SYSTEM


def test_service_doc_prompts_are_neutral() -> None:
    for text in (
        MAP_SYSTEM_BY_KIND["service_doc"],
        ASSESS_SYSTEM_BY_KIND["service_doc"],
        SUMMARY_SYSTEM_BY_KIND["service_doc"],
    ):
        assert "договор" not in text.lower()


async def test_run_uses_service_doc_prompts() -> None:
    pb = Playbook.model_validate(
        {
            "id": "sd",
            "name": "Политика",
            "doc_kind": "service_doc",
            "rules": [{"id": "goal", "title": "Цели", "question": "Указаны ли цели?"}],
        }
    )
    llm = FakeLLM(
        [
            [_tc("map_rules", {"mapping": [{"rule_id": "goal", "section_numbers": ["1"]}]})],
            [_tc("assess_rule", {"status": "ok", "explanation": ""})],
            [TextChunk(text="Документ в целом соответствует требованиям.")],
        ]
    )
    engine = ReviewEngine(llm, FakeRag([]), judge_enabled=False)
    events = [ev async for ev in engine.run(pb, "doc1", SECTIONS)]
    # все системные промпты стадий — service-варианты
    assert llm.calls[0][0][0].content == MAP_SYSTEM_BY_KIND["service_doc"]  # MAP
    assert llm.calls[1][0][0].content == ASSESS_SYSTEM_BY_KIND["service_doc"]  # ASSESS
    assert llm.calls[2][0][0].content == SUMMARY_SYSTEM_BY_KIND["service_doc"]  # SUMMARY
    assert any(isinstance(ev, ReviewReportEvent) for ev in events)


async def test_missing_rule_in_service_doc_report_has_no_contract_wording() -> None:
    """F1: `_missing_without_llm` — самый частый путь service_doc-отчёта (все
    правила плейбука сервисных документов задают risk_if_missing). Слово
    «договор» не должно попадать ни в explanation, ни в recommendation."""
    pb = Playbook.model_validate(
        {
            "id": "sd2",
            "name": "Политика",
            "doc_kind": "service_doc",
            "rules": [
                {
                    "id": "legal_basis",
                    "title": "Правовые основания обработки",
                    "question": "Указаны ли правовые основания обработки ПДн?",
                    "risk_if_missing": "high",
                }
            ],
        }
    )
    llm = FakeLLM(
        [
            [_tc("map_rules", {"mapping": [{"rule_id": "legal_basis", "section_numbers": []}]})],
            [TextChunk(text="Итог.")],  # резюме
        ]
    )
    engine = ReviewEngine(llm, FakeRag([]), judge_enabled=False)
    events = [ev async for ev in engine.run(pb, "doc1", SECTIONS)]
    report = next(e for e in events if isinstance(e, ReviewReportEvent)).report
    risk = report.risks[0]
    assert "договор" not in risk.explanation.lower()
    assert "договор" not in risk.recommendation.lower()
