"""Intent router separates legal questions from text tasks and small talk.

The classifier is intentionally crude: a deterministic keyword/heuristic pass
that is cheap, predictable, and unit-testable. A later iteration may switch
the implementation to an LLM call behind the same `classify_intent` seam —
the contract must not change."""

import pytest

from neurolegal.agent.chat.intent import Intent, classify_intent


@pytest.mark.parametrize(
    "msg",
    [
        "Что говорит ГК РФ о свободе договора?",
        "приведи нормы по защите прав потребителей",
        "Какая статья УК РФ применяется к мошенничеству?",
        "ответственность по 152-ФЗ",
        "Что такое исковая давность?",
        "налоговый вычет",
        "Можно ли расторгнуть договор в одностороннем порядке по ГК?",
    ],
)
def test_legal_questions_are_legal(msg: str) -> None:
    assert classify_intent(msg) == Intent.LEGAL


@pytest.mark.parametrize(
    "msg",
    [
        "Перефразируй этот абзац: «...»",
        "Сократи текст до трёх предложений.",
        "Переведи это на английский.",
        "Напиши краткое резюме следующего письма: ...",
        "Исправь грамматику: ...",
    ],
)
def test_text_tasks_are_text_task(msg: str) -> None:
    assert classify_intent(msg) == Intent.TEXT_TASK


@pytest.mark.parametrize(
    "msg",
    [
        "Привет",
        "Как тебя зовут?",
        "Спасибо!",
        "Что ты умеешь?",
    ],
)
def test_smalltalk_is_smalltalk(msg: str) -> None:
    assert classify_intent(msg) == Intent.SMALLTALK


def test_text_task_with_legal_quote_stays_text_task() -> None:
    # The user wants reformulation, not retrieval, even if the body mentions law.
    msg = "Перефразируй: «Согласно ст. 1 ГК РФ, гражданское законодательство...»"
    assert classify_intent(msg) == Intent.TEXT_TASK


@pytest.mark.parametrize(
    "msg",
    [
        "Составь договор аренды квартиры",
        "составь мне договор оказания услуг",
        "Оформи расписку о займе",
        "Подготовь соглашение о неразглашении",
        "Сделай документ по шаблону",
        "Заполним шаблон доверенности",
    ],
)
def test_compose_requests_are_template(msg: str) -> None:
    assert classify_intent(msg) == Intent.TEMPLATE


@pytest.mark.parametrize(
    "msg",
    [
        # вопрос про право, не просьба составить — глагола составления нет
        "Как расторгнуть договор аренды?",
        "Что должно быть в договоре подряда?",
        # текст-задача без документа-объекта
        "Напиши краткое резюме следующего письма: ...",
        # модальные «нужен/нужно/хочу» — не индикатор составления (ревью T-0135)
        "Мне нужно расторгнуть договор аренды, как это сделать?",
        "Нужен номер статьи про договор",
        "Хочу оспорить договор аренды в суде",
        "Нужна ли доверенность, чтобы получить посылку за другого человека?",
        "Какое заявление нужно подать в суд, чтобы взыскать долг?",
        # вопросительная конструкция гасит шаблонную ветку целиком
        "Как оформить доверенность?",
        "Что такое шаблон договора?",
        # инфинитив — не императив; «ли» и косвенные падежи «какой»
        # (второй проход ревью T-0135)
        "Обязательно ли составлять письменный договор аренды?",
        "Какую доверенность нужно оформить для получения пенсии?",
        "Должен ли я подготовить соглашение заранее?",
        "В каком договоре нужен пункт о неустойке?",
    ],
)
def test_template_triggers_do_not_leak(msg: str) -> None:
    assert classify_intent(msg) != Intent.TEMPLATE


@pytest.mark.parametrize(
    "msg",
    [
        "Мне нужно расторгнуть договор аренды, как это сделать?",
        "Нужен номер статьи про договор",
        "Нужна ли доверенность, чтобы получить посылку за другого человека?",
        "Как оформить доверенность?",
        "Обязательно ли составлять письменный договор аренды?",
        "Какую доверенность нужно оформить для получения пенсии?",
    ],
)
def test_modal_legal_questions_stay_legal(msg: str) -> None:
    assert classify_intent(msg) == Intent.LEGAL


def test_text_task_with_straight_quoted_legal_text_stays_text_task() -> None:
    msg = 'Сократи текст: "Согласно ст. 1 ГК РФ, гражданское законодательство..."'
    assert classify_intent(msg) == Intent.TEXT_TASK


@pytest.mark.parametrize(
    "msg",
    [
        "Переведи на простой язык ст. 10 ГК РФ",
        "Сформулируй, какой штраф предусмотрен за парковку на газоне",
        "Перепиши понятнее: что такое исковая давность по ГК?",
    ],
)
def test_legal_question_with_text_task_verb_is_legal(msg: str) -> None:
    """Legal markers outside quotes outrank text-task triggers — the
    unsure→LEGAL safety bias applies to mixed phrasings real users type."""
    assert classify_intent(msg) == Intent.LEGAL


def test_unknown_falls_back_to_legal() -> None:
    # When in doubt, treat as legal — the RAG hard rule is the safer default.
    assert classify_intent("???") == Intent.LEGAL


@pytest.mark.parametrize("msg", ["", "   ", "\t\n"])
def test_empty_or_whitespace_falls_back_to_legal(msg: str) -> None:
    assert classify_intent(msg) == Intent.LEGAL


def test_typo_trigger_ispvr() -> None:
    assert classify_intent("Испрвь опечатки в тексте") == Intent.TEXT_TASK


@pytest.mark.parametrize(
    "phrase",
    [
        "банк",  # contains "нк"
        "направо",  # contains "право"
        "наука",  # contains "ук"
        "поиск",  # contains "иск"
    ],
)
def test_short_codes_no_longer_match_inside_words(phrase: str) -> None:
    """\b boundaries: "нк" must not fire inside "банк", etc. Direct check
    against the compiled regex — guards against substring-style regression."""
    from neurolegal.agent.chat.intent import _LEGAL_RE

    assert _LEGAL_RE.search(phrase) is None
