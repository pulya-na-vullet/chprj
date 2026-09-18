import io

import pytest
from docx import Document

from neurolegal.documents.processing.docx import ExtractionError, extract_docx_paragraphs


def _docx_bytes(paragraphs: list[str]) -> bytes:
    doc = Document()
    for p in paragraphs:
        doc.add_paragraph(p)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def test_extracts_paragraphs_in_order():
    data = _docx_bytes(["1. Предмет", "Текст"])
    lines = extract_docx_paragraphs(data)
    assert lines[0] == "1. Предмет"
    assert "Текст" in lines


def test_corrupt_docx_raises_extraction_error():
    with pytest.raises(ExtractionError):
        extract_docx_paragraphs(b"not a zip at all")
