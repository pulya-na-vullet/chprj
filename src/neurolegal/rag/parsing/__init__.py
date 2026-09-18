from typing import Protocol

from neurolegal.core.domain import RawDocument, StructuredDoc
from neurolegal.rag.parsing.docx import DocxParser


class Parser(Protocol):
    def parse(self, raw: RawDocument) -> StructuredDoc: ...


__all__ = ["DocxParser", "Parser"]
