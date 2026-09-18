from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import patch

import httpx
import pytest

from neurolegal.core.domain import RawDocument
from neurolegal.rag.acquisition.cache import RawCache
from neurolegal.rag.acquisition.manifest import Manifest, ManifestEntry
from neurolegal.rag.acquisition.pravo_gov import PravoGovAcquirer


def _make_manifest() -> Manifest:
    return Manifest(
        entries={
            "ГК-1": ManifestEntry(
                code_id="ГК-1",
                kind="codex",
                short_name="ГК РФ",
                full_name="Гражданский кодекс Российской Федерации (часть первая)",
                pravo_url="https://example.test/gk-1.html",
            )
        }
    )


async def test_fetch_returns_cached(tmp_path: Path) -> None:
    manifest = _make_manifest()
    entry = manifest.entries["ГК-1"]
    cache = RawCache(tmp_path)
    cached_doc = RawDocument(
        source="pravo.gov.ru",
        source_doc_id=entry.source_doc_id,
        fetched_at=datetime.now(UTC),
        content_type="text/html",
        body_bytes=b"<html>cached</html>",
    )
    cache.put("pravo.gov.ru", entry.source_doc_id, cached_doc)

    acquirer = PravoGovAcquirer(manifest, cache=cache, politeness_seconds=0.0)
    out = await acquirer.fetch("ГК-1")
    assert out.body_bytes == b"<html>cached</html>"


async def test_fetch_misses_then_fetches_and_caches(tmp_path: Path) -> None:
    manifest = _make_manifest()
    entry = manifest.entries["ГК-1"]
    cache = RawCache(tmp_path)

    async def _fake_get(self: httpx.AsyncClient, url: str, **kw: Any) -> httpx.Response:
        return httpx.Response(
            200,
            content=b"<html>fresh</html>",
            headers={"content-type": "text/html; charset=utf-8"},
            request=httpx.Request("GET", url),
        )

    with patch("httpx.AsyncClient.get", new=_fake_get):
        acquirer = PravoGovAcquirer(manifest, cache=cache, politeness_seconds=0.0)
        out = await acquirer.fetch("ГК-1")

    assert out.body_bytes == b"<html>fresh</html>"
    again = cache.get("pravo.gov.ru", entry.source_doc_id)
    assert again is not None
    assert again.body_bytes == b"<html>fresh</html>"


async def test_fetch_unknown_code_raises() -> None:
    manifest = _make_manifest()
    acquirer = PravoGovAcquirer(manifest, politeness_seconds=0.0)
    with pytest.raises(KeyError, match="unknown code_id"):
        await acquirer.fetch("DOESNT-EXIST")
