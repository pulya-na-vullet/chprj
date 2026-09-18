from typing import Any, ClassVar

import pytest

from neurolegal.documents.config import settings
from neurolegal.documents.processing.docx import ExtractionError
from neurolegal.documents.processing.pdf import _default_parser_factory, extract_pdf


class _FakePage:
    pass


class _FakeResult:
    text: ClassVar[str] = "1. Предмет\nТекст пункта"
    pages: ClassVar[list] = [_FakePage(), _FakePage()]


class _FakeParser:
    def parse(self, data: bytes) -> _FakeResult:
        return _FakeResult()


def test_extract_pdf_splits_lines_and_counts_pages():
    out = extract_pdf(b"%PDF-1.4 fake", parser_factory=lambda: _FakeParser())
    assert out.paragraphs[0] == "1. Предмет"
    assert out.page_count == 2


class _BoomParser:
    def parse(self, data: bytes):
        raise ValueError("bad pdf")


def test_parser_failure_becomes_extraction_error():
    with pytest.raises(ExtractionError):
        extract_pdf(b"junk", parser_factory=lambda: _BoomParser())


def test_default_parser_factory_wires_tessdata_path(monkeypatch):
    """The default (production) factory must pass the preflighted tessdata
    path to liteparse — otherwise OCR ignores NEUROLEGAL_TESSDATA_PATH and
    can network-download rus.traineddata."""
    captured: dict[str, Any] = {}

    class _FakeLiteParse:
        def __init__(self, **kwargs: Any) -> None:
            captured.update(kwargs)

    import liteparse

    monkeypatch.setattr(liteparse, "LiteParse", _FakeLiteParse)

    _default_parser_factory("rus")()

    assert captured["ocr_language"] == "rus"
    assert captured["tessdata_path"] == str(settings.tessdata_path)
