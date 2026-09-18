"""ReviewEngine: the five-stage playbook-driven contract review pipeline.

Stages 1-2: map playbook rules onto document sections, then assess each
mapped rule against its section text (or, when a rule has no matching
section, emit a "missing clause" risk without an LLM call). Stages 3-4
ground each risk in retrieved statutes (`RagClient.search`) and run a judge
pass that picks citations by index (never inventing a statute) and can
downgrade the verdict to `not_a_risk`, dropping the risk entirely. Stage 5
is just the accumulation of risks/coverage into `ReviewReportData`, done in
`run()`.
"""

import asyncio
import logging
import re
import time
from collections.abc import AsyncIterator
from typing import Literal, cast

from pydantic import BaseModel, ValidationError

from neurolegal.agent.chat.events import AgentEvent, ReviewProgressEvent, ReviewReportEvent
from neurolegal.agent.llm.client import ChatLLM
from neurolegal.agent.llm.types import ChatMessage, TextChunk, ToolCallRequest, ToolSpec
from neurolegal.agent.review.playbook import Playbook, PlaybookRule
from neurolegal.agent.tools.rag_client import RagClient, RagClientError
from neurolegal.contracts import (
    Citation,
    CoverageStatus,
    ReviewCoverageItem,
    ReviewReportData,
    ReviewRisk,
    RiskLevel,
    SearchedArticle,
    Verdict,
)

logger = logging.getLogger(__name__)

DISCLAIMER = (
    "Черновая проверка. Выводы требуют подтверждения юриста; "
    "цитаты норм — только из найденных статей корпуса."
)

# Max chars of section text sent to the model at the assessment stage.
# Contracts can be long; truncate with an explicit marker instead of failing
# the LLM call outright.
ASSESS_TEXT_LIMIT = 12000

# T-0011: служебные id секций из neurolegal.documents processing/sections.py
# («preamble», «trailing», «pN» для не-нумерованных блоков). Это внутренние
# ключи mapping-стадии, но не номера секций договора — в отчёт им нельзя.
_SENTINEL_SECTION_ID = re.compile(r"^(preamble|trailing|p\d+)$")


def _public_section_number(number: str | None) -> str | None:
    """Номер секции для отчёта: сентинел-id пайплайна прячем (None)."""
    if number is None or _SENTINEL_SECTION_ID.match(number):
        return None
    return number


# Preview length for each section's text in the mapping-stage table of contents.
TOC_PREVIEW_CHARS = 200

MAP_TOOL = ToolSpec(
    name="map_rules",
    description=("Сопоставление правил проверки договора с номерами секций документа."),
    parameters={
        "type": "object",
        "properties": {
            "mapping": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "rule_id": {"type": "string"},
                        "section_numbers": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                    },
                    "required": ["rule_id", "section_numbers"],
                },
            }
        },
        "required": ["mapping"],
    },
)

ASSESS_TOOL = ToolSpec(
    name="assess_rule",
    description="Оценка одного правила проверки договора по тексту его секций.",
    parameters={
        "type": "object",
        "properties": {
            "status": {
                "type": "string",
                "enum": ["ok", "risk", "missing", "not_applicable"],
            },
            "risk_level": {"type": "string", "enum": ["high", "medium", "low"]},
            "quote": {"type": "string"},
            "explanation": {"type": "string"},
            "recommendation": {"type": "string"},
        },
        "required": ["status", "explanation"],
    },
)

JUDGE_TOOL = ToolSpec(
    name="judge_risk",
    description=(
        "Проверка найденного риска по нормам права: подтвердить, смягчить или "
        "отклонить вердикт и выбрать подтверждающие статьи по номеру из списка."
    ),
    parameters={
        "type": "object",
        "properties": {
            "verdict": {
                "type": "string",
                "enum": ["confirmed", "overstated", "not_a_risk"],
            },
            "citation_indexes": {
                "type": "array",
                "items": {"type": "integer"},
            },
            "note": {"type": "string"},
        },
        "required": ["verdict", "citation_indexes"],
    },
)

# Grounding caps: at most this many rag_queries per rule, and at most this
# many unique articles (by article_id) accumulated across all of them.
GROUNDING_MAX_QUERIES = 2
GROUNDING_MAX_ARTICLES = 6
# Preview length for each candidate article's full_text in the judge listing.
JUDGE_ARTICLE_PREVIEW_CHARS = 300

MAP_SYSTEM = (
    "Ты сопоставляешь правила проверки договора с секциями документа. "
    "Для каждого правила укажи номера релевантных секций (пустой список, если таких нет). "
    "Отвечай только вызовом инструмента map_rules."
)
ASSESS_SYSTEM = (
    "Ты проверяешь договор по одному правилу. Оцени только по приведённому тексту секций. "
    "quote — дословная цитата из договора. Отвечай только вызовом инструмента assess_rule."
)
JUDGE_SYSTEM = (
    "Ты проверяешь найденный риск по нормам права. Тебе дан пронумерованный список "
    "статей, найденных поиском по корпусу — цитировать можно только их номера в "
    "citation_indexes, придумывать новые статьи нельзя. Если ни одна статья не "
    "относится к риску, оставь citation_indexes пустым. verdict: confirmed — риск "
    "подтверждён нормой; overstated — риск преувеличен, но не снят; not_a_risk — "
    "риска на самом деле нет. Отвечай только вызовом инструмента judge_risk."
)

_RETRY_REMINDER = "Ответь только вызовом инструмента {name}."

# T-0047: резюме отчёта — один текстовый LLM-вызов в конце пайплайна.
SUMMARY_SYSTEM = (
    "Ты подводишь итог проверки договора по чек-листу рисков. "
    "Напиши итог строго не длиннее трёх предложений: первое — вывод по "
    "существу (в чью пользу перекошен договор или что он в целом рабочий), "
    "дальше — какие один-два конкретных момента согласовать в первую "
    "очередь и почему. Называй предмет риска прямо (что именно не "
    "ограничено, чего нет), а не категорию. Запрещены пустые обороты: "
    "«содержит значительные риски», «требует внимания», «следует "
    "проанализировать», «важно рассмотреть». "
    "Не пересказывай все риски — подробности уже показаны списком ниже. "
    "Если указана позиция стороны — пиши с её точки зрения. "
    "Деловой русский; без приветствий, списков и markdown. "
    "Образец тона: «Договор в целом рабочий, но перекошен в пользу "
    "поставщика: неустойка для вас не ограничена по сумме, а поставщик "
    "может отказаться от договора без компенсации. Перед подписанием "
    "стоит согласовать правки по двум высоким рискам ниже.»"
)
# Промпт резюме держим коротким: только главные риски (по убыванию уровня)
# и усечённые объяснения — счётчиков и названий правил достаточно для итога.
SUMMARY_TOP_RISKS = 5
SUMMARY_EXPLANATION_CHARS = 200

# Документы сервиса (E10): нейтральные варианты — «документ» вместо «договор»,
# итог про соответствие обязательным требованиям, не про «перекос договора».
MAP_SYSTEM_SERVICE = (
    "Ты сопоставляешь правила проверки документа с секциями документа. "
    "Для каждого правила укажи номера релевантных секций (пустой список, если таких нет). "
    "Отвечай только вызовом инструмента map_rules."
)
ASSESS_SYSTEM_SERVICE = (
    "Ты проверяешь документ по одному правилу. Оцени только по приведённому тексту секций. "
    "quote — дословная цитата из документа. Отвечай только вызовом инструмента assess_rule."
)
SUMMARY_SYSTEM_SERVICE = (
    "Ты подводишь итог проверки документа сервиса (политики конфиденциальности, "
    "пользовательского соглашения или согласия на обработку ПДн) на соответствие "
    "обязательным требованиям законодательства. Напиши итог строго не длиннее трёх "
    "предложений: первое — вывод по существу (документ в целом соответствует или "
    "есть существенные пробелы), дальше — какие один-два конкретных пробела устранить "
    "в первую очередь и почему. Называй пробел прямо (какого обязательного сведения "
    "или условия нет), а не категорию. Запрещены пустые обороты: «содержит значительные "
    "риски», «требует внимания», «следует проанализировать», «важно рассмотреть». "
    "Не пересказывай все находки — подробности уже показаны списком ниже. "
    "Деловой русский; без приветствий, списков и markdown. "
    "Образец тона: «Политика в целом соответствует требованиям, но не указаны правовые "
    "основания обработки и порядок отзыва согласия — эти сведения обязательны по ст. 18.1 "
    "152-ФЗ, их стоит добавить в первую очередь.»"
)

MAP_SYSTEM_BY_KIND = {"contract": MAP_SYSTEM, "service_doc": MAP_SYSTEM_SERVICE}
ASSESS_SYSTEM_BY_KIND = {"contract": ASSESS_SYSTEM, "service_doc": ASSESS_SYSTEM_SERVICE}
SUMMARY_SYSTEM_BY_KIND = {"contract": SUMMARY_SYSTEM, "service_doc": SUMMARY_SYSTEM_SERVICE}
_RISK_NOUN_BY_KIND = {"contract": "Рисков", "service_doc": "Замечаний"}

# Родительный падеж существительного «документ/договор» — для user-текста
# промптов assess/judge ("Текст секций {noun}:", "Цитата из {noun}:").
_DOC_NOUN_GEN_BY_KIND = {"contract": "договора", "service_doc": "документа"}

# F1: нейтральные дефолты для «клауза не найдена» — этот путь (_missing_without_llm)
# самый частый в service_doc-отчётах (все правила таких плейбуков задают
# risk_if_missing), так что слово «договор» туда просачивалось на каждый пробел.
_MISSING_EXPLANATION_BY_KIND = {
    "contract": "Клауза не найдена в договоре",
    "service_doc": "Обязательное условие не отражено в документе",
}
_MISSING_RECOMMENDATION_TEMPLATE_BY_KIND = {
    "contract": "Добавить в договор клаузу «{title}» ({question}).",
    "service_doc": "Добавить в документ положение «{title}» ({question}).",
}

# F3: tool-описания стадий map/assess идут в LLM для любого doc_kind — тоже
# нейтрализуем «договора»→«документа». Схема параметров повторяет контрактную
# версию без изменений — меняется только текст description.
MAP_TOOL_SERVICE = ToolSpec(
    name="map_rules",
    description=("Сопоставление правил проверки документа с номерами секций документа."),
    parameters=MAP_TOOL.parameters,
)
ASSESS_TOOL_SERVICE = ToolSpec(
    name="assess_rule",
    description="Оценка одного правила проверки документа по тексту его секций.",
    parameters=ASSESS_TOOL.parameters,
)
MAP_TOOL_BY_KIND = {"contract": MAP_TOOL, "service_doc": MAP_TOOL_SERVICE}
ASSESS_TOOL_BY_KIND = {"contract": ASSESS_TOOL, "service_doc": ASSESS_TOOL_SERVICE}

_LEVEL_RU = {"high": "высокий", "medium": "средний", "low": "низкий"}

# T-0046: user-facing prompt prefix when the caller pins a party role (e.g.
# "Заказчик" for services_ru). Applied to ASSESS and JUDGE user content only —
# never to MAP, and never when role is None/empty (prompts stay byte-for-byte
# unchanged in that case).
_ROLE_PREFIX_TEMPLATE = (
    "Вы оцениваете договор с позиции стороны: {role}. Ищите риски именно для этой стороны."
)


def _with_role_prefix(user: str, role: str | None) -> str:
    if not role:
        return user
    return f"{_ROLE_PREFIX_TEMPLATE.format(role=role)}\n\n{user}"


class _MapRuleEntry(BaseModel):
    rule_id: str
    section_numbers: list[str]


class _MapRulesArgs(BaseModel):
    mapping: list[_MapRuleEntry]


class _AssessRuleArgs(BaseModel):
    status: Literal["ok", "risk", "missing", "not_applicable"]
    risk_level: RiskLevel | None = None
    quote: str = ""
    explanation: str
    recommendation: str = ""


class _JudgeArgs(BaseModel):
    verdict: Verdict
    citation_indexes: list[int]
    note: str = ""


# Ключ — имя инструмента; используется для валидации аргументов tool-call в
# `_structured`.
_ARG_MODELS: dict[str, type[BaseModel]] = {
    "map_rules": _MapRulesArgs,
    "assess_rule": _AssessRuleArgs,
    "judge_risk": _JudgeArgs,
}


class ReviewEngineError(Exception):
    pass


class ReviewEngine:
    def __init__(
        self,
        llm: ChatLLM,
        rag_client: RagClient,
        acts: list[str] | None = None,
        judge_enabled: bool = True,
        concurrency: int = 4,
    ) -> None:
        self._llm = llm
        self._rag = rag_client
        self._acts = acts
        self._judge_enabled = judge_enabled
        self._concurrency = concurrency

    async def run(
        self,
        playbook: Playbook,
        document_id: str,
        sections: list[dict[str, object]],
        role: str | None = None,
    ) -> AsyncIterator[AgentEvent]:
        started = time.monotonic()
        mapping = await self._map(playbook, sections)  # стадия 1 — одиночный вызов
        total = len(playbook.rules)
        results: dict[str, tuple[ReviewRisk | None, CoverageStatus]] = {}
        # Очередь событий от воркеров: ("running", rule, None) при старте
        # правила, ("done", rule, cov_status) по завершении, ("failed", rule,
        # exc) при ошибке — драйнер ниже превращает их в ReviewProgressEvent
        # (или пробрасывает исключение).
        queue: asyncio.Queue[tuple[Literal["running", "done", "failed"], PlaybookRule, object]] = (
            asyncio.Queue()
        )
        sem = asyncio.Semaphore(self._concurrency)

        async def check_rule(rule: PlaybookRule) -> None:
            try:
                async with sem:
                    await queue.put(("running", rule, None))
                    risk, cov_status = await self._assess(
                        rule, mapping.get(rule.id, []), sections, role, playbook.doc_kind
                    )
                    if risk is not None and self._judge_enabled:
                        # stages 3-4
                        judged = await self._ground_and_judge(rule, risk, role, playbook.doc_kind)
                        if judged is None:
                            cov_status = "ok"
                        risk = judged
                    results[rule.id] = (risk, cov_status)
                    await queue.put(("done", rule, cov_status))
            except Exception as exc:
                await queue.put(("failed", rule, exc))

        tasks = [asyncio.create_task(check_rule(rule)) for rule in playbook.rules]
        finished = 0
        started_rules = 0
        try:
            while finished < total:
                kind, rule, payload = await queue.get()
                if kind == "running":
                    started_rules += 1
                    yield ReviewProgressEvent(
                        rule_id=rule.id,
                        title=rule.title,
                        index=started_rules,
                        total=total,
                        status="running",
                    )
                elif kind == "done":
                    finished += 1
                    yield ReviewProgressEvent(
                        rule_id=rule.id,
                        title=rule.title,
                        index=finished,
                        total=total,
                        status=cast(CoverageStatus, payload),
                    )
                else:  # "failed" — драйнер гасит остальных воркеров и пробрасывает
                    raise cast(BaseException, payload)
        finally:
            for t in tasks:
                t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

        # Пересборка risks/coverage в порядке правил плейбука — не в порядке
        # завершения воркеров (тот произволен под конкурентным выполнением).
        risks = [risk for r in playbook.rules if (risk := results[r.id][0]) is not None]
        coverage = [
            ReviewCoverageItem(rule_id=r.id, title=r.title, status=results[r.id][1])
            for r in playbook.rules
        ]
        summary = await self._summarize(playbook, role, risks, coverage)
        logger.info(
            "review_run_done",
            extra={"rules": total, "elapsed_s": round(time.monotonic() - started, 1)},
        )
        yield ReviewReportEvent(
            report=ReviewReportData(
                playbook_id=playbook.id,
                playbook_name=playbook.name,
                document_id=document_id,
                risks=risks,
                coverage=coverage,
                disclaimer=DISCLAIMER,
                role=role,
                summary=summary,
            )
        )

    # -- стадия 1: маппинг правил на секции ---------------------------------

    async def _map(
        self, playbook: Playbook, sections: list[dict[str, object]]
    ) -> dict[str, list[str]]:
        toc_lines = [
            f"{s.get('number', '')}. {s.get('title') or ''} — "
            f"{str(s.get('text', ''))[:TOC_PREVIEW_CHARS]}"
            for s in sections
        ]
        rule_lines = []
        for rule in playbook.rules:
            line = f"{rule.id}: {rule.title} — {rule.question}"
            if rule.anchors:
                line += f" (подсказки: {', '.join(rule.anchors)})"
            rule_lines.append(line)
        user = (
            "Оглавление документа:\n"
            + "\n".join(toc_lines)
            + "\n\nПравила проверки:\n"
            + "\n".join(rule_lines)
        )
        raw = await self._structured(
            MAP_SYSTEM_BY_KIND[playbook.doc_kind], user, MAP_TOOL_BY_KIND[playbook.doc_kind]
        )
        parsed = _MapRulesArgs.model_validate(raw)
        return {entry.rule_id: entry.section_numbers for entry in parsed.mapping}

    # -- стадия 2: оценка одного правила -------------------------------------

    async def _assess(
        self,
        rule: PlaybookRule,
        section_numbers: list[str],
        sections: list[dict[str, object]],
        role: str | None = None,
        doc_kind: str = "contract",
    ) -> tuple[ReviewRisk | None, CoverageStatus]:
        if not section_numbers:
            return self._missing_without_llm(rule, section_number=None, quote="", doc_kind=doc_kind)

        matched = self._expand_section_numbers(section_numbers, sections)
        text = self._section_text(matched)
        noun = _DOC_NOUN_GEN_BY_KIND[doc_kind]
        user = _with_role_prefix(f"Вопрос: {rule.question}\n\nТекст секций {noun}:\n{text}", role)
        raw = await self._structured(
            ASSESS_SYSTEM_BY_KIND[doc_kind], user, ASSESS_TOOL_BY_KIND[doc_kind]
        )
        parsed = _AssessRuleArgs.model_validate(raw)
        section_number = _public_section_number(section_numbers[0])

        if parsed.status == "risk":
            level = parsed.risk_level or "medium"
            risk = ReviewRisk(
                rule_id=rule.id,
                title=rule.title,
                level=level,
                verdict="confirmed",
                section_number=section_number,
                contract_quote=parsed.quote,
                explanation=parsed.explanation,
                recommendation=parsed.recommendation,
            )
            return risk, "risk"
        if parsed.status == "missing":
            return self._missing_without_llm(
                rule,
                section_number=section_number,
                quote=parsed.quote,
                explanation=parsed.explanation,
                recommendation=parsed.recommendation,
                doc_kind=doc_kind,
            )
        if parsed.status == "ok":
            return None, "ok"
        return None, "not_applicable"

    def _missing_without_llm(
        self,
        rule: PlaybookRule,
        *,
        section_number: str | None,
        quote: str,
        explanation: str = "",
        recommendation: str = "",
        doc_kind: str = "contract",
    ) -> tuple[ReviewRisk | None, CoverageStatus]:
        if rule.risk_if_missing is None:
            return None, "not_applicable"
        risk = ReviewRisk(
            rule_id=rule.id,
            title=rule.title,
            level=rule.risk_if_missing,
            verdict="confirmed",
            section_number=section_number,
            contract_quote=quote,
            explanation=explanation or _MISSING_EXPLANATION_BY_KIND[doc_kind],
            recommendation=recommendation
            or _MISSING_RECOMMENDATION_TEMPLATE_BY_KIND[doc_kind].format(
                title=rule.title, question=rule.question
            ),
        )
        return risk, "missing"

    @staticmethod
    def _expand_section_numbers(
        numbers: list[str], sections: list[dict[str, object]]
    ) -> list[dict[str, object]]:
        """Expand mapped section numbers to include their child sections.

        Parsing often puts a section's actual content in dotted children
        ("2.1", "2.2") while the parent ("2") holds only a heading line. The
        map stage frequently returns just the parent, so assessment must pull
        in every section whose number is `numbers` itself or starts with one
        of them plus a literal dot (any depth: "2" -> "2.1", "2.1.3", but
        never "20"). Preserves document order and drops duplicates.
        """
        number_set = set(numbers)
        prefixes = tuple(f"{n}." for n in numbers)
        result: list[dict[str, object]] = []
        seen: set[str] = set()
        for s in sections:
            num = str(s.get("number", ""))
            if num in seen:
                continue
            if num in number_set or num.startswith(prefixes):
                result.append(s)
                seen.add(num)
        return result

    def _section_text(self, sections: list[dict[str, object]]) -> str:
        # T-0011: текст секции уже начинается строкой-заголовком документа
        # («1. Предмет договора»), синтезированный префикс «{number}. {title}»
        # давал ту же строку дважды — и LLM дословно цитировал дубль в отчёте.
        parts = [str(s.get("text", "")) for s in sections]
        joined = "\n\n".join(parts)
        if len(joined) > ASSESS_TEXT_LIMIT:
            joined = joined[:ASSESS_TEXT_LIMIT] + "\n[текст обрезан]"
        return joined

    # -- T-0047: резюме отчёта ----------------------------------------------

    async def _summarize(
        self,
        playbook: Playbook,
        role: str | None,
        risks: list[ReviewRisk],
        coverage: list[ReviewCoverageItem],
    ) -> str | None:
        """Одно текстовое резюме («что в целом по договору») в конце пайплайна.

        Любой сбой вызова (или пустой ответ) не валит отчёт — summary = None,
        панель показывает отчёт без резюме.
        """
        messages: list[ChatMessage] = [
            ChatMessage(role="system", content=SUMMARY_SYSTEM_BY_KIND[playbook.doc_kind]),
            ChatMessage(role="user", content=self._summary_user(playbook, role, risks, coverage)),
        ]
        parts: list[str] = []
        try:
            async for event in self._llm.stream(messages, []):
                if isinstance(event, TextChunk):
                    parts.append(event.text)
        except Exception:
            logger.warning("review_summary_failed", extra={"playbook_id": playbook.id})
            return None
        return "".join(parts).strip() or None

    @staticmethod
    def _summary_user(
        playbook: Playbook,
        role: str | None,
        risks: list[ReviewRisk],
        coverage: list[ReviewCoverageItem],
    ) -> str:
        counts = {level: sum(1 for r in risks if r.level == level) for level in _LEVEL_RU}
        lines = [f"Проверка: {playbook.name}."]
        if role:
            lines.append(f"Позиция стороны: {role}.")
        lines.append(
            f"Проверено правил: {len(coverage)}. {_RISK_NOUN_BY_KIND[playbook.doc_kind]}: "
            f"высокий {counts['high']} · средний {counts['medium']} · низкий {counts['low']}."
        )
        top = [r for level in _LEVEL_RU for r in risks if r.level == level][:SUMMARY_TOP_RISKS]
        if top:
            lines.append("Главные риски:")
            lines.extend(
                f"— {_LEVEL_RU[r.level]}: {r.title}. {r.explanation[:SUMMARY_EXPLANATION_CHARS]}"
                for r in top
            )
        else:
            lines.append(f"{_RISK_NOUN_BY_KIND[playbook.doc_kind]} не найдено.")
        return "\n".join(lines)

    # -- stages 3-4: grounding + judge ---------------------------------------

    async def _ground_and_judge(
        self,
        rule: PlaybookRule,
        risk: ReviewRisk,
        role: str | None = None,
        doc_kind: str = "contract",
    ) -> ReviewRisk | None:
        """Ground `risk` in retrieved statutes, then have the model judge it.

        A rule with no `rag_queries` has nothing to ground against — the risk
        is returned flagged `no_basis=True` (no LLM call), so an ungrounded
        `confirmed` verdict never masquerades as statute-backed. Otherwise: run
        the rule's
        grounding searches (outages degrade to an empty article list rather
        than aborting the rule), then always call the judge so it can still
        downgrade the verdict to `not_a_risk` even without supporting
        citations. `verdict=="not_a_risk"` drops the risk (caller flips
        coverage to "ok"). A judge call that never returns valid arguments
        keeps the risk as assessed, flagged `no_basis=True`, and does not
        fail the rule.
        """
        if not rule.rag_queries:
            return risk.model_copy(update={"no_basis": True})
        articles = await self._ground(rule)
        try:
            judged = await self._judge(rule, risk, articles, role, doc_kind)
        except ReviewEngineError:
            logger.warning("review_judge_call_failed", extra={"rule_id": rule.id})
            return risk.model_copy(update={"no_basis": True})
        if judged.verdict == "not_a_risk":
            return None
        citations = [
            self._article_citation(articles[i - 1])
            for i in judged.citation_indexes
            if 1 <= i <= len(articles)
        ]
        return risk.model_copy(
            update={"verdict": judged.verdict, "citations": citations, "no_basis": not citations}
        )

    async def _ground(self, rule: PlaybookRule) -> list[SearchedArticle]:
        """Run up to `GROUNDING_MAX_QUERIES` rag_queries, deduping by article_id.

        A per-query `RagClientError` degrades to "no articles from this
        query" (logged) rather than aborting the rule — a RAG outage must
        not drop an otherwise-confirmed risk.
        """
        seen: dict[str, SearchedArticle] = {}
        for query in rule.rag_queries[:GROUNDING_MAX_QUERIES]:
            if len(seen) >= GROUNDING_MAX_ARTICLES:
                break
            try:
                found = await self._rag.search(query, acts=self._acts)
            except RagClientError:
                logger.warning(
                    "review_grounding_search_failed", extra={"rule_id": rule.id, "query": query}
                )
                continue
            for article in found:
                if len(seen) >= GROUNDING_MAX_ARTICLES:
                    break
                seen.setdefault(str(article.article_id), article)
        return list(seen.values())

    async def _judge(
        self,
        rule: PlaybookRule,
        risk: ReviewRisk,
        articles: list[SearchedArticle],
        role: str | None = None,
        doc_kind: str = "contract",
    ) -> _JudgeArgs:
        listing = "\n".join(
            f"[{i}] ст. {a.number} {a.act_short_name} — {a.title or ''} — "
            f"{a.full_text[:JUDGE_ARTICLE_PREVIEW_CHARS]}"
            for i, a in enumerate(articles, start=1)
        )
        noun = _DOC_NOUN_GEN_BY_KIND[doc_kind]
        user = _with_role_prefix(
            f"Правило: {rule.title} — {rule.question}\n\n"
            f"Найденный риск:\nЦитата из {noun}: {risk.contract_quote}\n"
            f"Обоснование: {risk.explanation}\n\n"
            f"Найденные статьи:\n{listing or '(ничего не найдено)'}",
            role,
        )
        raw = await self._structured(JUDGE_SYSTEM, user, JUDGE_TOOL)
        return _JudgeArgs.model_validate(raw)

    @staticmethod
    def _article_citation(article: SearchedArticle) -> Citation:
        return Citation(
            act_short_name=article.act_short_name,
            kind=article.act_kind,
            number=article.number,
            title=article.title,
            full_text=article.full_text,
            score=article.score,
        )

    # -- structured tool-call helper -----------------------------------------

    async def _structured(self, system: str, user: str, tool: ToolSpec) -> dict[str, object]:
        messages: list[ChatMessage] = [
            ChatMessage(role="system", content=system),
            ChatMessage(role="user", content=user),
        ]
        for _attempt in range(2):
            call = await self._collect_tool_call(messages, tool)
            args = self._validate_args(tool.name, call.arguments) if call is not None else None
            if args is not None:
                return args
            logger.warning("review_structured_retry", extra={"tool": tool.name})
            messages = [
                *messages,
                ChatMessage(role="user", content=_RETRY_REMINDER.format(name=tool.name)),
            ]
        raise ReviewEngineError(f"{tool.name}: model did not return a valid tool call")

    async def _collect_tool_call(
        self, messages: list[ChatMessage], tool: ToolSpec
    ) -> ToolCallRequest | None:
        result: ToolCallRequest | None = None
        async for event in self._llm.stream(messages, [tool]):
            if isinstance(event, ToolCallRequest):
                result = event
        return result

    def _validate_args(
        self, tool_name: str, arguments: dict[str, object]
    ) -> dict[str, object] | None:
        model_cls = _ARG_MODELS.get(tool_name)
        if model_cls is None:
            return arguments
        try:
            validated = model_cls.model_validate(arguments)
        except ValidationError:
            return None
        return validated.model_dump()
