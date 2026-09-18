"""Per-turn intent router for the agent.

Four buckets, decided by cheap keyword rules:

* ``LEGAL``: any question about RF law. The agent MUST ground its answer in
  ``rag_search`` results and refuse from general knowledge.
* ``TEXT_TASK``: rewrite / translate / summarise / proofread arbitrary text
  the user pasted. The agent may answer without retrieval and must not emit
  legal citations.
* ``SMALLTALK``: greetings, capability questions, meta. Same as TEXT_TASK
  for retrieval rules, but kept as a separate label so the system prompt can
  be tuned independently in future.
* ``TEMPLATE`` (E20): просьба составить/оформить документ — ход получает
  тулзы шаблонов + ask_user, без rag_search и цитат.

The default is ``LEGAL`` — if we are unsure, we err on the side of the
RAG-grounded rule. This is a safety choice, not a routing accuracy choice.

The implementation is deliberately rule-based for v1. The function signature
is the seam: a future LLM-backed classifier can swap in without touching the
agent loop."""

import re
from enum import StrEnum

_TEXT_TASK_TRIGGERS = (
    "перефраз",
    "перепиш",
    "сократи",
    "сокращ",
    "переведи",
    "перевод",
    "резюм",
    "сформулируй",
    "исправь",
    "испрвь",  # common typo
    "грамматик",
    "опечат",
    "корректур",
    "вычитай",
)

# classify_intent() lowercases input before matching, but the IGNORECASE
# flag is kept so the regex is correct if called directly (e.g. from a test
# or a future LLM-backed router that wants to reuse the pattern).
_SMALLTALK_RE = re.compile(
    r"^\s*(привет|здравствуй|здорово|добрый\s+(день|вечер|утро)|"
    r"как\s+(тебя\s+зовут|дела)|"
    r"спасибо|благодарю|"
    r"что\s+ты\s+умеешь|кто\s+ты|"
    r"тест)\s*[!?.…]*\s*$",
    re.IGNORECASE,
)

# Quoted blocks are material the user wants transformed, not a question
# about law — legal markers inside them must not flip a text task to LEGAL.
_QUOTED_RE = re.compile(r"«[^»]*»|\"[^\"]*\"|“[^”]*”")

# Legal-domain markers. We use a single \b-anchored regex so that short
# tokens like "гк", "ук", "нк", "иск", "право" don't fire inside "банк",
# "наука", "направо", "поиск" etc. Long markers ("статья", "кодекс", …)
# behave the same as a substring match because they're rarely a substring
# of an unrelated word.
_LEGAL_RE = re.compile(
    r"\b("
    r"стать[яею]|ст\.|закон|норм[аеуы]|кодекс|"
    r"гк|ук|коап|нк|тк|вк|"
    r"прав[ао]|обязанност[ьи]|ответственност[ьи]|"
    r"договор|иск|пошлин|штраф|налог|"
    r"потребител|наслед|арбитраж|"
    r"152-фз|44-фз|223-фз"
    r")\b"
)

# E20: просьба СОСТАВИТЬ документ — императив составления + документ-объект.
# Строго императивные словоформы под \b-границами: инфинитивы («составлять»,
# «оформить») в русском живут в обсуждениях и вопросах («Обязательно ли
# составлять…»), не в прямой просьбе, поэтому не триггерят (ревью T-0135,
# два прохода). Модальные «нужен/нужно/хочу» — тем более. «напиши резюме
# письма» (нет документа) остаётся TEXT_TASK.
_TEMPLATE_VERB_RE = re.compile(r"\b(составь(те)?|оформи(те)?|подготовь(те)?|создай(те)?)\b")
_TEMPLATE_DOCS = (
    "договор",
    "доверенност",
    "расписк",
    "заявлени",
    "соглашени",
    "контракт",
)

# Вопросительные конструкции гасят шаблонный интент целиком: «Как оформить
# доверенность?» и «Что такое шаблон договора?» — вопросы про право, им
# нужен rag_search, не диалог заполнения. «ли» одним альтернативом покрывает
# всё семейство «можно/нужно/обязательно/должен ли»; «как…» — маска по корню,
# включая косвенные падежи («какую», «каком», «каких»).
_TEMPLATE_QUESTION_RE = re.compile(
    r"\b(ли|как|почему|зачем|что такое|что будет|что если|"
    r"как(ой|ая|ое|ие|ого|ому|ом|ую|их|ими|им))\b"
)


class Intent(StrEnum):
    LEGAL = "legal"
    TEXT_TASK = "text_task"
    SMALLTALK = "smalltalk"
    TEMPLATE = "template"


def classify_intent(message: str) -> Intent:
    text = message.lower().strip()
    if not text:
        return Intent.LEGAL  # safer default

    if _SMALLTALK_RE.match(text):
        return Intent.SMALLTALK

    # TEMPLATE до text-task и legal: «составь договор аренды» содержит
    # legal-маркер «договор», но это просьба составить документ, не вопрос
    # про право. Маркеры внутри кавычек — вставленный материал, не считаются;
    # вопросительные конструкции полностью гасят ветку (unsure → LEGAL).
    unquoted_for_template = _QUOTED_RE.sub(" ", text)
    if not _TEMPLATE_QUESTION_RE.search(unquoted_for_template):
        if "шаблон" in unquoted_for_template:
            return Intent.TEMPLATE
        if _TEMPLATE_VERB_RE.search(unquoted_for_template) and any(
            doc in unquoted_for_template for doc in _TEMPLATE_DOCS
        ):
            return Intent.TEMPLATE

    if any(trigger in text for trigger in _TEXT_TASK_TRIGGERS):
        # A text-task verb can still carry a legal question («переведи на
        # простой язык ст. 10 ГК РФ»). Legal markers OUTSIDE quoted blocks
        # win — per the unsure→LEGAL safety bias; markers inside «...»
        # belong to pasted material and keep the turn a text task.
        unquoted = _QUOTED_RE.sub(" ", text)
        if _LEGAL_RE.search(unquoted):
            return Intent.LEGAL
        return Intent.TEXT_TASK

    return Intent.LEGAL  # unknown → legal (safer)
