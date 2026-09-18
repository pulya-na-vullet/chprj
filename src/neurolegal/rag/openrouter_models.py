"""Fetch + cache the OpenRouter model catalog for the agent settings UI.

GET https://openrouter.ai/api/v1/models returns {"data": [...]}. We map each
entry to the contract `OpenRouterModel` and cache the parsed list in memory
with a TTL so the admin UI doesn't hammer OpenRouter on every render.
"""

import time
from typing import Any

import httpx

from neurolegal.contracts import OpenRouterModel
from neurolegal.core.config import settings
from neurolegal.core.http import (
    OPENROUTER_ATTRIBUTION_HEADERS,
    OPENROUTER_BASE_URL,
    make_http_retry,
)

_CACHE_TTL_SECONDS = 600.0
_cache: tuple[float, list[OpenRouterModel]] | None = None


def parse_models_payload(payload: dict[str, Any]) -> list[OpenRouterModel]:
    out: list[OpenRouterModel] = []
    for item in payload.get("data", []):
        pricing = item.get("pricing") or {}
        supported = item.get("supported_parameters") or []
        out.append(
            OpenRouterModel(
                id=item["id"],
                name=item.get("name") or item["id"],
                context_length=item.get("context_length"),
                prompt_price=pricing.get("prompt"),
                completion_price=pricing.get("completion"),
                supports_tools="tools" in supported,
            )
        )
    return out


async def fetch_models(*, now: float | None = None) -> list[OpenRouterModel]:
    global _cache
    current = time.monotonic() if now is None else now
    if _cache is not None and current - _cache[0] < _CACHE_TTL_SECONDS:
        return _cache[1]
    headers = dict(OPENROUTER_ATTRIBUTION_HEADERS)
    if settings.openrouter_api_key:
        headers["Authorization"] = f"Bearer {settings.openrouter_api_key}"
    async for attempt in make_http_retry():
        with attempt:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(f"{OPENROUTER_BASE_URL}/models", headers=headers)
                response.raise_for_status()
                payload = response.json()
            models = parse_models_payload(payload)
            _cache = (current, models)
            return models
    return []  # pragma: no cover - make_http_retry reraises on exhaustion
