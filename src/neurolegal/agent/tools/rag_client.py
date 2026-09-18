"""HTTP client for the RAG service.

The agent talks to RAG **only** through this client — never by importing
``neurolegal.rag.*`` modules directly. Retries here mirror the embedder's tenacity
pattern: RAG runs behind the same flaky network as OpenRouter.
"""

from collections.abc import Sequence

import httpx

from neurolegal.contracts import (
    ActsResponse,
    ActSummary,
    SearchedArticle,
    SearchResponse,
    SourceArticleDetail,
    SourceArticlesResponse,
    SourcesResponse,
)
from neurolegal.core.http import make_http_retry


class RagClientError(RuntimeError):
    pass


class RagClient:
    """Thin wrapper over the RAG FastAPI app (``neurolegal.rag.api.app:app``)."""

    def __init__(self, base_url: str = "http://127.0.0.1:8001", timeout: float = 30.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    async def search(
        self,
        query: str,
        *,
        acts: Sequence[str] | None = None,
        limit: int = 8,
        min_score: float | None = None,
    ) -> list[SearchedArticle]:
        params: list[tuple[str, str | int | float | bool | None]] = [
            ("q", query),
            ("limit", limit),
        ]
        # When None, omit the param so the server applies its own
        # settings.rag_min_score. An explicit value (including 0.0) is sent.
        if min_score is not None:
            params.append(("min_score", min_score))
        for act in acts or []:
            params.append(("acts", act))
        try:
            async for attempt in make_http_retry():
                with attempt:
                    async with httpx.AsyncClient(timeout=self._timeout) as client:
                        response = await client.get(f"{self._base_url}/search", params=params)
                        response.raise_for_status()
                        payload = response.json()
                    return SearchResponse.model_validate(payload).articles
        # ValueError covers json.JSONDecodeError and pydantic.ValidationError:
        # a 200 with a non-JSON or schema-drifted body must degrade into
        # RagClientError, not crash the agent turn.
        except (httpx.HTTPError, ValueError) as exc:
            raise RagClientError(f"RAG search failed: {exc}") from exc
        raise RagClientError("unreachable")

    async def fetch_article(self, act: str, number: str) -> list[SearchedArticle]:
        params: list[tuple[str, str | int | float | bool | None]] = [
            ("act", act),
            ("number", number),
        ]
        try:
            async for attempt in make_http_retry():
                with attempt:
                    async with httpx.AsyncClient(timeout=self._timeout) as client:
                        response = await client.get(f"{self._base_url}/article", params=params)
                        response.raise_for_status()
                        payload = response.json()
                    return SearchResponse.model_validate(payload).articles
        except (httpx.HTTPError, ValueError) as exc:
            raise RagClientError(f"RAG article failed: {exc}") from exc
        raise RagClientError("unreachable")

    async def list_acts(self) -> list[ActSummary]:
        try:
            async for attempt in make_http_retry():
                with attempt:
                    async with httpx.AsyncClient(timeout=self._timeout) as client:
                        response = await client.get(f"{self._base_url}/acts")
                        response.raise_for_status()
                        payload = response.json()
                    return ActsResponse.model_validate(payload).acts
        except (httpx.HTTPError, ValueError) as exc:
            raise RagClientError(f"RAG acts failed: {exc}") from exc
        raise RagClientError("unreachable")

    async def list_sources(self) -> SourcesResponse:
        try:
            async for attempt in make_http_retry():
                with attempt:
                    async with httpx.AsyncClient(timeout=self._timeout) as client:
                        response = await client.get(f"{self._base_url}/sources")
                        response.raise_for_status()
                        payload = response.json()
                    return SourcesResponse.model_validate(payload)
        except (httpx.HTTPError, ValueError) as exc:
            raise RagClientError(f"RAG sources failed: {exc}") from exc
        raise RagClientError("unreachable")

    async def source_articles(self, source_doc_id: str) -> SourceArticlesResponse:
        try:
            async for attempt in make_http_retry():
                with attempt:
                    async with httpx.AsyncClient(timeout=self._timeout) as client:
                        response = await client.get(
                            f"{self._base_url}/sources/{source_doc_id}/articles"
                        )
                        response.raise_for_status()
                        payload = response.json()
                    return SourceArticlesResponse.model_validate(payload)
        except (httpx.HTTPError, ValueError) as exc:
            raise RagClientError(f"RAG source articles failed: {exc}") from exc
        raise RagClientError("unreachable")

    async def article_detail(self, article_id: str) -> SourceArticleDetail:
        try:
            async for attempt in make_http_retry():
                with attempt:
                    async with httpx.AsyncClient(timeout=self._timeout) as client:
                        response = await client.get(
                            f"{self._base_url}/sources/articles/{article_id}"
                        )
                        response.raise_for_status()
                        payload = response.json()
                    return SourceArticleDetail.model_validate(payload)
        except (httpx.HTTPError, ValueError) as exc:
            raise RagClientError(f"RAG article detail failed: {exc}") from exc
        raise RagClientError("unreachable")
