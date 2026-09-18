"""OpenRouter-backed streaming chat client with tool calling.

Tenacity retries cover connection setup only — once bytes are streaming we
cannot rewind, so a mid-stream failure surfaces to the caller. Same backoff
shape as ``OpenRouterEmbedder``.
"""

import json
import logging
from collections.abc import AsyncIterator
from typing import Any, Protocol

import httpx

from neurolegal.agent.llm.types import (
    ChatMessage,
    LLMEvent,
    ReasoningChunk,
    TextChunk,
    ToolCallRequest,
    ToolSpec,
)
from neurolegal.contracts import GenerationSettings
from neurolegal.core.config import settings
from neurolegal.core.http import (
    OPENROUTER_ATTRIBUTION_HEADERS,
    OPENROUTER_BASE_URL,
    make_http_retry,
)

logger = logging.getLogger(__name__)


class LLMError(RuntimeError):
    pass


class ChatLLM(Protocol):
    def stream(
        self, messages: list[ChatMessage], tools: list[ToolSpec]
    ) -> AsyncIterator[LLMEvent]: ...


class OpenRouterChatClient:
    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str = OPENROUTER_BASE_URL,
        timeout: float = 120.0,
        generation: GenerationSettings | None = None,
        tool_choice: str | None = None,
    ) -> None:
        self._api_key = api_key if api_key is not None else settings.openrouter_api_key
        self._model = model or settings.llm_model
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._generation = generation or GenerationSettings()
        self._tool_choice = tool_choice

    def _build_payload(
        self, messages: list[ChatMessage], tools: list[ToolSpec]
    ) -> dict[str, object]:
        payload: dict[str, object] = {
            "model": self._model,
            "messages": [m.to_openrouter() for m in messages],
            "stream": True,
        }
        g = self._generation
        for key, value in (
            ("temperature", g.temperature),
            ("top_p", g.top_p),
            ("max_tokens", g.max_tokens),
            ("seed", g.seed),
            ("reasoning_effort", g.reasoning_effort),
            ("top_k", g.top_k),
            ("frequency_penalty", g.frequency_penalty),
            ("presence_penalty", g.presence_penalty),
        ):
            if value is not None:
                payload[key] = value
        if tools:
            payload["tools"] = [t.to_openrouter() for t in tools]
            if self._tool_choice is not None:
                payload["tool_choice"] = self._tool_choice
        return payload

    async def stream(
        self, messages: list[ChatMessage], tools: list[ToolSpec]
    ) -> AsyncIterator[LLMEvent]:
        if not self._api_key:
            raise LLMError("OPENROUTER_API_KEY is not set")

        payload = self._build_payload(messages, tools)
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            **OPENROUTER_ATTRIBUTION_HEADERS,
        }

        client = httpx.AsyncClient(timeout=self._timeout)
        try:
            response = await self._open_stream(client, payload, headers)
            try:
                async for event in self._parse_stream(response):
                    yield event
            finally:
                await response.aclose()
        finally:
            await client.aclose()

    async def _open_stream(
        self,
        client: httpx.AsyncClient,
        payload: dict[str, object],
        headers: dict[str, str],
    ) -> httpx.Response:
        async for attempt in make_http_retry():
            with attempt:
                request = client.build_request(
                    "POST",
                    f"{self._base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                )
                response = await client.send(request, stream=True)
                try:
                    response.raise_for_status()
                except httpx.HTTPStatusError:
                    # Drain + close the failed stream so the connection is
                    # released between attempts, and keep the error body —
                    # it carries OpenRouter's actual rejection reason.
                    body = (await response.aread()).decode(errors="replace")
                    await response.aclose()
                    logger.warning(
                        "llm_open_stream_http_error",
                        extra={"status": response.status_code, "body": body[:500]},
                    )
                    raise
                return response
        raise LLMError("unreachable")

    async def _parse_stream(self, response: httpx.Response) -> AsyncIterator[LLMEvent]:
        # tool-call fragments are streamed incrementally, keyed by `index`;
        # accumulate them and emit one ToolCallRequest each once the stream ends.
        fragments: dict[int, dict[str, str]] = {}
        async for raw in response.aiter_lines():
            line = raw.strip()
            if not line or not line.startswith("data:"):
                continue
            data = line[len("data:") :].strip()
            if data == "[DONE]":
                break
            try:
                chunk: dict[str, Any] = json.loads(data)
            except json.JSONDecodeError:
                logger.warning("llm_sse_bad_json", extra={"raw": data})
                continue
            choices = chunk.get("choices") or []
            if not choices:
                continue
            delta = choices[0].get("delta") or {}
            # OpenRouter normalises thinking traces to `reasoning`; some
            # providers pass through the native `reasoning_content`.
            reasoning = delta.get("reasoning") or delta.get("reasoning_content")
            if reasoning:
                yield ReasoningChunk(text=reasoning)
            content = delta.get("content")
            if content:
                yield TextChunk(text=content)
            for tc in delta.get("tool_calls") or []:
                idx = tc.get("index", 0)
                frag = fragments.setdefault(idx, {"id": "", "name": "", "arguments": ""})
                if tc.get("id"):
                    frag["id"] = tc["id"]
                fn = tc.get("function") or {}
                if fn.get("name"):
                    frag["name"] = fn["name"]
                if fn.get("arguments"):
                    frag["arguments"] += fn["arguments"]

        for frag in fragments.values():
            if not frag["name"]:
                continue
            try:
                args = json.loads(frag["arguments"]) if frag["arguments"] else {}
            except json.JSONDecodeError:
                logger.warning("llm_tool_call_bad_json", extra={"raw": frag["arguments"]})
                args = {}
            yield ToolCallRequest(id=frag["id"], name=frag["name"], arguments=args)
