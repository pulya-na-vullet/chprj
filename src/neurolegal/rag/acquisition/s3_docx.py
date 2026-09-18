from datetime import UTC, datetime

from neurolegal.core.domain import RawDocument
from neurolegal.rag.acquisition.corpus_store import DOCX_CONTENT_TYPE, CorpusStore
from neurolegal.rag.acquisition.manifest import Manifest, get_entry


class S3DocxAcquirer:
    """Fetch a corpus .docx from S3 by the manifest's `docx_s3_key`."""

    def __init__(self, manifest: Manifest, store: CorpusStore) -> None:
        self._manifest = manifest
        self._store = store

    async def fetch(self, code_id: str) -> RawDocument:
        entry = get_entry(code_id, self._manifest)
        if entry.docx_s3_key is None:
            raise FileNotFoundError(f"{code_id}: no docx_s3_key in manifest")
        body = await self._store.get(entry.docx_s3_key)
        return RawDocument(
            source="s3-docx",
            source_doc_id=entry.source_doc_id,
            fetched_at=datetime.now(UTC),
            content_type=DOCX_CONTENT_TYPE,
            body_bytes=body,
        )
