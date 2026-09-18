from datetime import UTC, datetime
from pathlib import Path

from neurolegal.core.domain import RawDocument
from neurolegal.rag.acquisition.cache import RawCache


def make_doc(body: bytes = b"<html/>") -> RawDocument:
    return RawDocument(
        source="pravo.gov.ru",
        source_doc_id="gk-1",
        fetched_at=datetime.now(UTC),
        content_type="text/html",
        body_bytes=body,
    )


def test_cache_roundtrip(tmp_path: Path) -> None:
    cache = RawCache(tmp_path)
    doc = make_doc(b"<html>1</html>")
    cache.put("pravo.gov.ru", "gk-1", doc)
    loaded = cache.get("pravo.gov.ru", "gk-1")
    assert loaded is not None
    assert loaded.body_bytes == b"<html>1</html>"
    assert loaded.source_doc_id == "gk-1"


def test_cache_miss(tmp_path: Path) -> None:
    cache = RawCache(tmp_path)
    assert cache.get("pravo.gov.ru", "missing") is None
