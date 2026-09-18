import asyncio
import logging
from datetime import UTC, datetime

import httpx

from neurolegal.core.config import settings
from neurolegal.core.domain import RawDocument
from neurolegal.core.http import make_http_retry
from neurolegal.rag.acquisition.cache import RawCache
from neurolegal.rag.acquisition.manifest import Manifest, get_entry

logger = logging.getLogger(__name__)


class PravoGovAcquirer:
    def __init__(
        self,
        manifest: Manifest,
        cache: RawCache | None = None,
        politeness_seconds: float = 0.5,
    ) -> None:
        self._manifest = manifest
        self._cache = cache or RawCache(settings.raw_cache_dir)
        self._politeness = politeness_seconds
        self._user_agent = "Neurolegal/0.1.0 (+https://example.com/contact)"

    async def fetch(self, code_id: str) -> RawDocument:
        entry = get_entry(code_id, self._manifest)
        if entry.pravo_url is None:
            raise RuntimeError(f"{code_id}: no pravo_url in manifest")

        cached = self._cache.get("pravo.gov.ru", entry.source_doc_id)
        if cached is not None:
            logger.info("acq.cache_hit", extra={"code_id": code_id})
            return cached

        logger.info(
            "acq.cache_miss_fetching",
            extra={"code_id": code_id, "url": entry.pravo_url},
        )
        body, content_type = await self._http_fetch(entry.pravo_url)
        doc = RawDocument(
            source="pravo.gov.ru",
            source_doc_id=entry.source_doc_id,
            fetched_at=datetime.now(UTC),
            content_type=content_type,
            body_bytes=body,
        )
        self._cache.put("pravo.gov.ru", entry.source_doc_id, doc)
        await asyncio.sleep(self._politeness)
        return doc

    async def _http_fetch(self, url: str) -> tuple[bytes, str]:
        async with httpx.AsyncClient(
            timeout=30.0, headers={"User-Agent": self._user_agent}
        ) as client:
            async for attempt in make_http_retry():
                with attempt:
                    response = await client.get(url, follow_redirects=True)
                    response.raise_for_status()
                    return response.content, response.headers.get("content-type", "text/html")
        raise RuntimeError("unreachable")
