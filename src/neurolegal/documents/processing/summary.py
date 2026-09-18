"""Однострочная LLM-выжимка «Суть» документа (T-0017).

Мини-клиент OpenRouter chat/completions (базовый модуль neurolegal.core.http) —
документный центр не импортирует neurolegal.agent.*, поэтому LLM-вызов локален.
Дешёвая быстрая модель (NEUROLEGAL_SUMMARY_MODEL), вход обрезается до
SUMMARY_INPUT_CHARS.
"""

import httpx

from neurolegal.core.http import (
    OPENROUTER_ATTRIBUTION_HEADERS,
    OPENROUTER_BASE_URL,
    make_http_retry,
)
from neurolegal.documents.config import settings

SUMMARY_INPUT_CHARS = 6000
SUMMARY_MAX_CHARS = 90
_TIMEOUT = 20.0

SYSTEM_PROMPT = (
    "Ты подписываешь юридический документ одной короткой фразой для реестра файлов. "
    "Ответь на вопрос «что это за документ»: тип документа и один опознавательный "
    "признак — стороны, адрес или предмет. До 90 символов, без вводных слов, "
    "без сроков, сумм и номеров, без перечислений. "
    "Примеры: «Аренда квартиры на ул. Лесной, 24»; "
    "«Акт сверки взаиморасчётов с ООО «Вектор»»; «Устав ООО «Ромашка»»."
)


def summary_enabled() -> bool:
    return bool(settings.openrouter_api_key)


def _cap_summary(line: str, limit: int) -> str:
    """Truncate to at most `limit` chars, breaking at the last space and
    appending an ellipsis instead of cutting mid-word (Minor 15 fix, final
    review). Falls back to a hard cut only when the first `limit` chars have
    no space to break on at all.
    """
    if len(line) <= limit:
        return line
    truncated = line[:limit]
    cut = truncated.rfind(" ")
    truncated = truncated[:cut] if cut > 0 else truncated[: limit - 1]
    return truncated.rstrip() + "…"


async def summarize(full_text: str) -> str | None:
    """Строка «Сути» или None (нет ключа / пустой ответ модели).

    Транспортные ошибки и 5xx/429 ретраятся tenacity; исчерпание ретраев
    пробрасывает исключение — решение на вызывающей стороне.
    """
    if not settings.openrouter_api_key:
        return None
    payload: dict[str, object] = {
        "model": settings.summary_model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": full_text[:SUMMARY_INPUT_CHARS]},
        ],
        # T-0013: без preference OpenRouter может отдать запрос провайдеру
        # для минутного ответа; sort=latency держит вызов в секундах.
        "provider": {"sort": "latency"},
    }
    async for attempt in make_http_retry():
        with attempt:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                response = await client.post(
                    f"{OPENROUTER_BASE_URL}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {settings.openrouter_api_key}",
                        "Content-Type": "application/json",
                        **OPENROUTER_ATTRIBUTION_HEADERS,
                    },
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
            text = str(data["choices"][0]["message"]["content"] or "").strip()
            line = text.splitlines()[0].strip() if text else ""
            return (_cap_summary(line, SUMMARY_MAX_CHARS) if line else "") or None
    raise RuntimeError("unreachable")
