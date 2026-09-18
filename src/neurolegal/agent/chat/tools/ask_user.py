"""ask_user (T-0051): терминальная LLM-тулза «задать уточняющий вопрос».

Работает иначе, чем остальные тулзы: она не возвращает результат модели —
валидный вызов перехватывается циклом ChatAgent.run() ДО диспатча по
registry, и ход завершается вопросом-сообщением (AskEvent + DoneEvent),
ответ пользователя приходит следующим обычным ходом. Поэтому здесь только
ToolSpec и санитизация аргументов; обработчика (ToolHandler) нет."""

from neurolegal.agent.llm.types import ToolSpec

MAX_QUESTION_CHARS = 300
MAX_OPTIONS = 5

ASK_USER_TOOL = ToolSpec(
    name="ask_user",
    description=(
        "Задать пользователю ОДИН уточняющий вопрос и завершить ход, когда без "
        "ответа нельзя ответить корректно. options — короткие готовые варианты "
        "ответа (кнопки), пользователь может ответить и свободным текстом."
    ),
    parameters={
        "type": "object",
        "properties": {
            "question": {"type": "string", "description": "Вопрос пользователю"},
            "options": {
                "type": "array",
                "items": {"type": "string"},
                "description": "До 5 коротких вариантов ответа (необязательно)",
            },
        },
        "required": ["question"],
    },
)


def parse_ask_user_args(arguments: dict[str, object]) -> tuple[str, list[str]] | None:
    """Валидация + санитизация аргументов вызова; None — вызов невалиден.

    Вопрос обязателен и непуст (обрезается до MAX_QUESTION_CHARS); options
    чистятся (только строки, трим, без пустых и дублей) и режутся до
    MAX_OPTIONS."""
    question_raw = arguments.get("question")
    if not isinstance(question_raw, str) or not question_raw.strip():
        return None
    question = question_raw.strip()[:MAX_QUESTION_CHARS]

    options: list[str] = []
    options_raw = arguments.get("options")
    if isinstance(options_raw, list):
        for item in options_raw:
            if not isinstance(item, str):
                continue
            text = item.strip()
            if text and text not in options:
                options.append(text)
            if len(options) == MAX_OPTIONS:
                break
    return question, options
