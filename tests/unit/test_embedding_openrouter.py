import math
from typing import Any
from unittest.mock import patch

import httpx
import pytest

from neurolegal.rag.embedding.openrouter import OpenRouterEmbedder, _truncate_and_renormalise


def test_truncate_and_renormalise_keeps_target_dim() -> None:
    vec = [float(i) for i in range(4096)]
    out = _truncate_and_renormalise(vec, target_dim=1024)
    assert len(out) == 1024
    norm = math.sqrt(sum(x * x for x in out))
    assert abs(norm - 1.0) < 1e-6


def test_truncate_and_renormalise_handles_zero_vector() -> None:
    out = _truncate_and_renormalise([0.0] * 4096, target_dim=1024)
    assert len(out) == 1024
    assert all(x == 0.0 for x in out)


@pytest.mark.asyncio
async def test_openrouter_embed_truncates_to_1024_and_renormalises() -> None:
    raw_vec = [float(i + 1) for i in range(4096)]
    fake_payload = {"data": [{"embedding": raw_vec}]}

    async def _fake_post(self: httpx.AsyncClient, url: str, **kwargs: Any) -> httpx.Response:
        return httpx.Response(200, json=fake_payload, request=httpx.Request("POST", url))

    with patch("httpx.AsyncClient.post", new=_fake_post):
        emb = OpenRouterEmbedder(api_key="sk-fake", target_dim=1024)
        out = await emb.embed(["тест"])

    assert len(out) == 1
    assert len(out[0]) == 1024
    assert abs(math.sqrt(sum(x * x for x in out[0])) - 1.0) < 1e-6


@pytest.mark.asyncio
async def test_openrouter_embed_batch() -> None:
    raw_vecs = [[float(i + 1) for i in range(4096)], [float(i + 2) for i in range(4096)]]
    fake_payload = {"data": [{"embedding": v} for v in raw_vecs]}

    async def _fake_post(self: httpx.AsyncClient, url: str, **kwargs: Any) -> httpx.Response:
        return httpx.Response(200, json=fake_payload, request=httpx.Request("POST", url))

    with patch("httpx.AsyncClient.post", new=_fake_post):
        emb = OpenRouterEmbedder(api_key="sk-fake")
        out = await emb.embed(["a", "b"])

    assert len(out) == 2
    assert all(len(v) == 1024 for v in out)


@pytest.mark.asyncio
async def test_openrouter_embed_requests_latency_routing() -> None:
    """T-0013: без provider-preference OpenRouter иногда роутит запрос
    медленному провайдеру (наблюдалось: Nebius 21-58 сек, тогда как
    DeepInfra/SiliconFlow: 0,8-3 сек). sort=latency убирает хвост латентности,
    fallbacks остаются включёнными."""
    raw_vec = [float(i + 1) for i in range(4096)]
    fake_payload = {"data": [{"embedding": raw_vec}]}
    captured: dict[str, Any] = {}

    async def _fake_post(self: httpx.AsyncClient, url: str, **kwargs: Any) -> httpx.Response:
        captured.update(kwargs["json"])
        return httpx.Response(200, json=fake_payload, request=httpx.Request("POST", url))

    with patch("httpx.AsyncClient.post", new=_fake_post):
        emb = OpenRouterEmbedder(api_key="sk-fake")
        await emb.embed(["тест"])

    assert captured["provider"] == {"sort": "latency"}


def test_make_embedder_passes_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    """T-0013: поисковый путь строит эмбеддер на коротком таймауте, чтобы
    одно подвисшее соединение не стоило пользователю 60+ секунд (ретрай
    после короткого таймаута обходится в секунды)."""
    from neurolegal.rag.embedding import make_embedder

    monkeypatch.setattr("neurolegal.core.config.settings.embedder", "openrouter")
    emb = make_embedder(timeout=15.0)
    assert isinstance(emb, OpenRouterEmbedder)
    assert emb._timeout == 15.0
    default = make_embedder()
    assert isinstance(default, OpenRouterEmbedder)
    assert default._timeout == 60.0


def test_search_embedder_uses_query_timeout() -> None:
    from neurolegal.rag.api import deps

    deps.get_embedder.cache_clear()
    try:
        emb = deps.get_embedder()
        assert isinstance(emb, OpenRouterEmbedder)
        assert emb._timeout == deps.QUERY_EMBED_TIMEOUT == 15.0
    finally:
        deps.get_embedder.cache_clear()


@pytest.mark.asyncio
async def test_openrouter_no_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    # Override settings so the constructor's fallback also yields None.
    monkeypatch.setattr("neurolegal.rag.embedding.openrouter.settings.openrouter_api_key", None)
    emb = OpenRouterEmbedder(api_key=None)
    # api_key=None still triggers settings fallback in __init__, which we just nulled.
    emb._api_key = None  # belt-and-braces in case future refactor changes init
    with pytest.raises(ValueError, match="OPENROUTER_API_KEY"):
        await emb.embed(["тест"])


@pytest.mark.asyncio
async def test_openrouter_empty_input_returns_empty() -> None:
    emb = OpenRouterEmbedder(api_key="sk-fake")
    assert await emb.embed([]) == []
