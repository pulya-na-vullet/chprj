"""PDF text extraction via liteparse (local Rust core + bundled Tesseract).

liteparse decides per page whether OCR is needed (native text vs scanned
image). We inject the parser factory so tests can run without a real PDF or
tessdata. tessdata is provisioned + preflighted at service startup (see
processing.preflight); this module wires both the OCR language and the
preflighted tessdata path into liteparse so OCR never falls back to a
network download of `rus.traineddata`. The injected test factory bypasses
tessdata entirely.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from neurolegal.documents.processing.docx import ExtractionError


class _LiteParseLike(Protocol):
    def parse(self, data: bytes) -> object: ...


@dataclass
class PdfExtract:
    paragraphs: list[str]
    page_count: int


def _default_parser_factory(ocr_language: str) -> Callable[[], _LiteParseLike]:
    def factory() -> _LiteParseLike:
        from liteparse import LiteParse

        from neurolegal.documents.config import settings

        return LiteParse(ocr_language=ocr_language, tessdata_path=str(settings.tessdata_path))

    return factory


def extract_pdf(
    data: bytes,
    *,
    parser_factory: Callable[[], _LiteParseLike] | None = None,
    ocr_language: str = "rus",
) -> PdfExtract:
    factory = parser_factory or _default_parser_factory(ocr_language)
    try:
        result = factory().parse(data)
        text: str = getattr(result, "text", "")
        pages = getattr(result, "pages", [])
    except Exception as exc:  # liteparse raises its own types; one exit
        raise ExtractionError(f"Не удалось извлечь текст из PDF: {exc}") from exc
    return PdfExtract(paragraphs=text.splitlines(), page_count=len(pages))
