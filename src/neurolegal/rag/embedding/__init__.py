from typing import Protocol

from neurolegal.core.config import settings


class Embedder(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]: ...


def make_embedder(timeout: float | None = None) -> Embedder:
    """Build an Embedder based on NEUROLEGAL_EMBEDDER env.

    ``timeout`` (сек) переопределяет HTTP-таймаут эмбеддера: поисковый путь
    задаёт короткий (см. api/deps.QUERY_EMBED_TIMEOUT), инжест живёт на
    дефолте 60 секунд: батчи инжеста по 128 текстов легитимно
    медленнее одиночного запроса.
    """
    choice = settings.embedder.strip().lower()
    if choice == "openrouter":
        from neurolegal.rag.embedding.openrouter import OpenRouterEmbedder

        return OpenRouterEmbedder() if timeout is None else OpenRouterEmbedder(timeout=timeout)
    if choice.startswith(("http://", "https://")):
        from neurolegal.rag.embedding.http_client import HttpEmbedder

        if timeout is None:
            return HttpEmbedder(settings.embedder)
        return HttpEmbedder(settings.embedder, timeout=timeout)
    raise ValueError(f"unknown NEUROLEGAL_EMBEDDER: {settings.embedder!r}")


__all__ = ["Embedder", "make_embedder"]
