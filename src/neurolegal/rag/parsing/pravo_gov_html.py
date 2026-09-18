from neurolegal.core.domain import RawDocument, StructuredDoc
from neurolegal.rag.acquisition.manifest import Manifest


class PravoGovHTMLParser:
    """Stub. Real HTML parsing is deferred."""

    def __init__(self, manifest: Manifest) -> None:
        self._manifest = manifest

    def parse(self, raw: RawDocument) -> StructuredDoc:
        raise NotImplementedError(
            "PravoGovHTMLParser is not implemented; use --source=docx for now."
        )
