import io
from typing import ClassVar

import pytest
from docx import Document

from neurolegal.documents.processing.docx import ExtractionError
from neurolegal.documents.processing.pipeline import (
    UnsupportedFormatError,
    extract,
)


def _docx_bytes(paragraphs: list[str]) -> bytes:
    doc = Document()
    for p in paragraphs:
        doc.add_paragraph(p)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def test_docx_dispatch_produces_sections():
    data = _docx_bytes(["1. Предмет договора", "Текст"])
    result = extract(data, "contract.docx")
    assert result.parser == "docx"
    assert result.page_count is None
    assert any(s["number"] == "1" for s in result.sections)
    assert "Предмет" in result.full_text


class _FakeResult:
    text: ClassVar[str] = "1. Пункт\nтекст"
    pages: ClassVar[list[object]] = [object()]


def test_pdf_dispatch_uses_injected_parser():
    result = extract(
        b"%PDF fake",
        "scan.pdf",
        pdf_parser_factory=lambda: type("P", (), {"parse": lambda self, d: _FakeResult()})(),
    )
    assert result.parser == "pdf"
    assert result.page_count == 1


def test_unsupported_suffix():
    with pytest.raises(UnsupportedFormatError):
        extract(b"x", "old.doc")


def test_empty_document_raises():
    data = _docx_bytes(["   "])
    with pytest.raises(ExtractionError):
        extract(data, "empty.docx")
