"""Format dispatch: bytes + filename -> ExtractionResult.

Adding a new format (.doc, later) means adding a branch here — the seam is
the suffix dispatch.
"""

from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path

from neurolegal.documents.processing.docx import ExtractionError, extract_docx_paragraphs
from neurolegal.documents.processing.pdf import extract_pdf
from neurolegal.documents.processing.sections import build_sections


class UnsupportedFormatError(ExtractionError):
    pass


@dataclass
class ExtractionResult:
    full_text: str
    sections: list[dict[str, object]]
    page_count: int | None
    parser: str


def extract(
    data: bytes,
    filename: str,
    *,
    pdf_parser_factory: Callable[[], object] | None = None,
) -> ExtractionResult:
    suffix = Path(filename).suffix.lower()
    page_count: int | None = None
    if suffix == ".docx":
        paragraphs = extract_docx_paragraphs(data)
        parser = "docx"
    elif suffix == ".pdf":
        pdf = extract_pdf(data, parser_factory=pdf_parser_factory)  # type: ignore[arg-type]
        paragraphs = pdf.paragraphs
        page_count = pdf.page_count
        parser = "pdf"
    else:
        raise UnsupportedFormatError(f"Формат {suffix or '?'} пока не поддерживается")

    sections, full_text = build_sections(paragraphs)
    if not full_text.strip():
        raise ExtractionError("Документ пуст или текст не извлечён")
    return ExtractionResult(
        full_text=full_text,
        sections=[asdict(s) for s in sections],
        page_count=page_count,
        parser=parser,
    )
