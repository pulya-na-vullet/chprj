import json
from typing import Any

import httpx
import pytest

import neurolegal.agent.llm.client as client_module
from neurolegal.agent.llm.client import LLMError, OpenRouterChatClient
from neurolegal.agent.llm.types import (
    ChatMessage,
    ReasoningChunk,
    TextChunk,
    ToolCallRequest,
    ToolSpec,
)


def _sse(*chunks: dict[str, Any]) -> bytes:
    lines: list[str] = []
    for c in chunks:
        lines.append(f"data: {json.dumps(c)}")
        lines.append("")
    lines.append("data: [DONE]")
    lines.append("")
    return "\n".join(lines).encode()


def _patch_transport(monkeypatch: pytest.MonkeyPatch, body: bytes) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=body)

    real_client = httpx.AsyncClient

    def factory(**kwargs: Any) -> httpx.AsyncClient:
        kwargs.setdefault("transport", httpx.MockTransport(handler))
        return real_client(**kwargs)

    monkeypatch.setattr(client_module.httpx, "AsyncClient", factory)


@pytest.mark.asyncio
async def test_stream_yields_text_chunks(monkeypatch: pytest.MonkeyPatch) -> None:
    body = _sse(
        {"choices": [{"delta": {"content": "Привет"}}]},
        {"choices": [{"delta": {"content": ", мир"}}]},
    )
    _patch_transport(monkeypatch, body)
    client = OpenRouterChatClient(api_key="sk-fake")
    events = [e async for e in client.stream([ChatMessage(role="user", content="hi")], [])]
    assert [e.text for e in events if isinstance(e, TextChunk)] == ["Привет", ", мир"]


@pytest.mark.asyncio
async def test_stream_yields_reasoning_chunks(monkeypatch: pytest.MonkeyPatch) -> None:
    # Reasoning models emit `delta.reasoning` (the model's thinking) before
    # `delta.content` (the visible answer). Both must surface, distinctly.
    body = _sse(
        {"choices": [{"delta": {"reasoning": "Это "}}]},
        {"choices": [{"delta": {"reasoning": "приветствие."}}]},
        {"choices": [{"delta": {"content": "Привет!"}}]},
    )
    _patch_transport(monkeypatch, body)
    client = OpenRouterChatClient(api_key="sk-fake")
    events = [e async for e in client.stream([ChatMessage(role="user", content="hi")], [])]
    assert [e.text for e in events if isinstance(e, ReasoningChunk)] == ["Это ", "приветствие."]
    assert [e.text for e in events if isinstance(e, TextChunk)] == ["Привет!"]


@pytest.mark.asyncio
async def test_stream_accumulates_tool_call_fragments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = _sse(
        {
            "choices": [
                {
                    "delta": {
                        "tool_calls": [
                            {
                                "index": 0,
                                "id": "call_1",
                                "function": {
                                    "name": "rag_search",
                                    "arguments": '{"query":',
                                },
                            }
                        ]
                    }
                }
            ]
        },
        {
            "choices": [
                {"delta": {"tool_calls": [{"index": 0, "function": {"arguments": ' "налог"}'}}]}}
            ]
        },
    )
    _patch_transport(monkeypatch, body)
    tool = ToolSpec(name="rag_search", description="d", parameters={"type": "object"})
    client = OpenRouterChatClient(api_key="sk-fake")
    events = [e async for e in client.stream([ChatMessage(role="user", content="hi")], [tool])]
    calls = [e for e in events if isinstance(e, ToolCallRequest)]
    assert len(calls) == 1
    assert calls[0].id == "call_1"
    assert calls[0].name == "rag_search"
    assert calls[0].arguments == {"query": "налог"}


@pytest.mark.asyncio
async def test_stream_without_api_key_raises() -> None:
    client = OpenRouterChatClient(api_key="")
    with pytest.raises(LLMError, match="OPENROUTER_API_KEY"):
        async for _ in client.stream([ChatMessage(role="user", content="hi")], []):
            pass


@pytest.mark.asyncio
async def test_stream_skips_malformed_json_lines(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A malformed data: line must not crash the stream — it is skipped.
    body = (
        b"data: not valid json\n\n"
        b'data: {"choices": [{"delta": {"content": "ok"}}]}\n\n'
        b"data: [DONE]\n\n"
    )
    _patch_transport(monkeypatch, body)
    client = OpenRouterChatClient(api_key="sk-fake")
    events = [e async for e in client.stream([ChatMessage(role="user", content="hi")], [])]
    assert [e.text for e in events if isinstance(e, TextChunk)] == ["ok"]
