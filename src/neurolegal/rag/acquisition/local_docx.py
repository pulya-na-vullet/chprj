from datetime import UTC, datetime
from pathlib import Path

from neurolegal.core.domain import RawDocument
from neurolegal.rag.acquisition.manifest import Manifest, get_entry

DOCX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


class LocalDocxAcquirer:
    def __init__(self, manifest: Manifest, root: Path = Path(".")) -> None:
        self._manifest = manifest
        self._root = root

    async def fetch(self, code_id: str) -> RawDocument:
        entry = get_entry(code_id, self._manifest)
        if entry.docx_path is None:
            raise FileNotFoundError(f"{code_id}: no docx_path in manifest")
        path = entry.docx_path
        if not path.is_absolute():
            path = (self._root / path).resolve()
        body = path.read_bytes()
        return RawDocument(
            source="local-docx",
            source_doc_id=entry.source_doc_id,
            fetched_at=datetime.now(UTC),
            content_type=DOCX_CONTENT_TYPE,
            body_bytes=body,
        )
