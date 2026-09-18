from typing import Any
from unittest.mock import patch

import httpx
import pytest

from neurolegal.documents.processing import summary as summary_mod


def _resp(content: str) -> dict[str, Any]:
    return {"choices": [{"message": {"content": content}}]}


@pytest.mark.asyncio
async def test_summarize_payload_and_result(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(summary_mod.settings, "openrouter_api_key", "sk-fake")
    monkeypatch.setattr(summary_mod.settings, "summary_model", "openai/gpt-4o-mini")
    captured: dict[str, Any] = {}

    async def _fake_post(self: httpx.AsyncClient, url: str, **kwargs: Any) -> httpx.Response:
        captured["url"] = url
        captured.update(kwargs["json"])
        return httpx.Response(
            200, json=_resp("Поставка; оплата 10 дней"), request=httpx.Request("POST", url)
        )

    with patch("httpx.AsyncClient.post", new=_fake_post):
        out = await summary_mod.summarize("x" * 10_000)

    assert out == "Поставка; оплата 10 дней"
    assert captured["url"].endswith("/chat/completions")
    assert captured["model"] == "openai/gpt-4o-mini"
    assert captured["provider"] == {"sort": "latency"}  # урок T-0013
    assert len(captured["messages"][1]["content"]) == summary_mod.SUMMARY_INPUT_CHARS


@pytest.mark.asyncio
async def test_summarize_first_line_and_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(summary_mod.settings, "openrouter_api_key", "sk-fake")

    async def _fake_post(self: httpx.AsyncClient, url: str, **kwargs: Any) -> httpx.Response:
        return httpx.Response(
            200, json=_resp("А" * 300 + "\nвторая строка"), request=httpx.Request("POST", url)
        )

    with patch("httpx.AsyncClient.post", new=_fake_post):
        out = await summary_mod.summarize("текст")
    assert out is not None
    assert len(out) == summary_mod.SUMMARY_MAX_CHARS
    assert "вторая" not in out


@pytest.mark.asyncio
async def test_summarize_empty_answer_is_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(summary_mod.settings, "openrouter_api_key", "sk-fake")

    async def _fake_post(self: httpx.AsyncClient, url: str, **kwargs: Any) -> httpx.Response:
        return httpx.Response(200, json=_resp("  \n"), request=httpx.Request("POST", url))

    with patch("httpx.AsyncClient.post", new=_fake_post):
        assert await summary_mod.summarize("текст") is None


@pytest.mark.asyncio
async def test_summarize_without_key_returns_none() -> None:
    with patch.object(summary_mod.settings, "openrouter_api_key", None):
        assert await summary_mod.summarize("текст") is None
        assert summary_mod.summary_enabled() is False


def test_prompt_asks_for_one_short_phrase() -> None:
    prompt = summary_mod.SYSTEM_PROMPT
    assert "точку с запятой" not in prompt
    assert "90" in prompt
    # промпт требует назначение документа, а не перечень условий  # noqa: RUF003
    assert "оплата" not in prompt.lower()


@pytest.mark.asyncio
async def test_summary_is_capped_at_90_chars(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(summary_mod.settings, "openrouter_api_key", "sk-fake")
    monkeypatch.setattr(summary_mod.settings, "summary_model", "openai/gpt-4o-mini")
    long_line = "Договор аренды " + "очень " * 40 + "длинный"

    async def _fake_post(self: httpx.AsyncClient, url: str, **kwargs: Any) -> httpx.Response:
        return httpx.Response(200, json=_resp(long_line), request=httpx.Request("POST", url))

    with patch("httpx.AsyncClient.post", new=_fake_post):
        out = await summary_mod.summarize("текст документа")

    assert out is not None
    assert len(out) <= 90
    # Minor 15 (финальное ревью): срез не должен резать слово пополам — кап
    # обрезает по последнему пробелу и добавляет многоточие.
    assert out.endswith("…")
    body = out[:-1].rstrip()
    assert long_line.startswith(body)
    assert long_line[len(body)] == " "
