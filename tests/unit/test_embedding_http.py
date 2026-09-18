from typing import Any
from unittest.mock import patch

import httpx
import pytest

from neurolegal.rag.embedding.http_client import HttpEmbedder


@pytest.mark.asyncio
async def test_http_embedder_calls_embed_endpoint() -> None:
    captured: dict[str, Any] = {}

    async def _fake_post(self: httpx.AsyncClient, url: str, **kwargs: Any) -> httpx.Response:
        captured["url"] = url
        captured["json"] = kwargs.get("json")
        return httpx.Response(
            200,
            json={"vectors": [[0.1] * 1024, [0.2] * 1024]},
            request=httpx.Request("POST", url),
        )

    with patch("httpx.AsyncClient.post", new=_fake_post):
        emb = HttpEmbedder("http://embedder:8000")
        out = await emb.embed(["a", "b"])

    assert captured["url"] == "http://embedder:8000/embed"
    assert captured["json"] == {"texts": ["a", "b"]}
    assert len(out) == 2
    assert all(len(v) == 1024 for v in out)


@pytest.mark.asyncio
async def test_http_embedder_empty_returns_empty() -> None:
    emb = HttpEmbedder("http://embedder:8000")
    assert await emb.embed([]) == []
