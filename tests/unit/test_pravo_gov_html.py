"""Unit test for the PravoGovHTMLParser stub."""

from datetime import UTC, datetime

import pytest

from neurolegal.core.domain import RawDocument
from neurolegal.rag.acquisition.manifest import Manifest
from neurolegal.rag.parsing.pravo_gov_html import PravoGovHTMLParser


def test_parse_is_not_implemented() -> None:
    parser = PravoGovHTMLParser(Manifest(entries={}))
    raw = RawDocument(
        source="pravo.gov.ru",
        source_doc_id="x",
        fetched_at=datetime.now(UTC),
        content_type="text/html",
        body_bytes=b"<html></html>",
    )
    with pytest.raises(NotImplementedError):
        parser.parse(raw)
