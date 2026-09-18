"""DOCX text extraction (python-docx), body order preserved, tables flattened."""

from io import BytesIO

from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph


class ExtractionError(Exception):
    """Any failure to extract text from a document."""


def extract_docx_paragraphs(data: bytes) -> list[str]:
    try:
        doc = Document(BytesIO(data))
        lines: list[str] = []
        for item in doc.iter_inner_content():
            if isinstance(item, Paragraph):
                lines.append(item.text)
            elif isinstance(item, Table):
                for row in item.rows:
                    cells = [c.text.strip() for c in row.cells if c.text.strip()]
                    if cells:
                        lines.append(" | ".join(cells))
        return lines
    except Exception as exc:  # python-docx/lxml raise several types; one exit
        raise ExtractionError(f"Не удалось открыть DOCX: {exc}") from exc
