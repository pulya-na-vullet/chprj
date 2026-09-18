"""parse_ask_user_args (T-0051): санитизация аргументов LLM-тулзы."""

from neurolegal.agent.chat.tools.ask_user import parse_ask_user_args


def test_valid_args_pass_through() -> None:
    assert parse_ask_user_args({"question": "Кто вы?", "options": ["А", "Б"]}) == (
        "Кто вы?",
        ["А", "Б"],
    )


def test_options_sanitized_dedup_и_cap() -> None:
    q, opts = parse_ask_user_args(  # type: ignore[misc]
        {"question": "  Вопрос?  ", "options": [" А ", "", "А", 42, "Б", "В", "Г", "Д", "Е"]}
    )
    assert q == "Вопрос?"
    # строки: трим, пустые/дубли/не-строки выброшены, максимум 5
    assert opts == ["А", "Б", "В", "Г", "Д"]


def test_question_capped_at_300_chars() -> None:
    q, _ = parse_ask_user_args({"question": "х" * 500})  # type: ignore[misc]
    assert len(q) == 300


def test_missing_or_blank_question_is_invalid() -> None:
    assert parse_ask_user_args({}) is None
    assert parse_ask_user_args({"question": "   "}) is None
    assert parse_ask_user_args({"question": 7}) is None


def test_options_optional() -> None:
    assert parse_ask_user_args({"question": "Вопрос?"}) == ("Вопрос?", [])
