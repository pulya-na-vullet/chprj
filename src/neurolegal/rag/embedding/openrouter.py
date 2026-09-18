"""OpenRouter-backed embedder.

Default model: ``qwen/qwen3-embedding-8b`` (4096-d). The Qwen3 embedding family
is trained MRL-aware, so truncating to a smaller prefix and re-normalising is
the documented way to fit a fixed schema. We truncate to ``embedder_target_dim``
(default 1024) to match the Postgres ``vector(1024)`` column.
"""

import math

import httpx

from neurolegal.core.config import settings
from neurolegal.core.http import (
    OPENROUTER_ATTRIBUTION_HEADERS,
    OPENROUTER_BASE_URL,
    make_http_retry,
)


def _truncate_and_renormalise(vec: list[float], target_dim: int) -> list[float]:
    truncated = vec[:target_dim]
    norm = math.sqrt(sum(x * x for x in truncated))
    if norm == 0.0:
        return truncated
    return [x / norm for x in truncated]


class OpenRouterEmbedder:
    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        target_dim: int | None = None,
        base_url: str = OPENROUTER_BASE_URL,
        timeout: float = 60.0,
    ) -> None:
        self._api_key = api_key if api_key is not None else settings.openrouter_api_key
        self._model = model or settings.embedder_model
        self._target_dim = target_dim or settings.embedder_target_dim
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        if not self._api_key:
            raise ValueError("OPENROUTER_API_KEY is not set")

        async for attempt in make_http_retry():
            with attempt:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    response = await client.post(
                        f"{self._base_url}/embeddings",
                        headers={
                            "Authorization": f"Bearer {self._api_key}",
                            "Content-Type": "application/json",
                            **OPENROUTER_ATTRIBUTION_HEADERS,
                        },
                        json={
                            "model": self._model,
                            "input": texts,
                            # T-0013: без preference OpenRouter иногда роутит
                            # запрос медленному провайдеру (Nebius: 21-58 сек,
                            # тогда как DeepInfra/SiliconFlow: 0,8-3 сек; замер
                            # 2026-07-12). sort=latency держит ответ в единицах
                            # секунд; fallbacks по умолчанию остаются включены.
                            "provider": {"sort": "latency"},
                        },
                    )
                    response.raise_for_status()
                    data = response.json()

                return [
                    _truncate_and_renormalise(item["embedding"], self._target_dim)
                    for item in data["data"]
                ]
        raise RuntimeError("unreachable")
