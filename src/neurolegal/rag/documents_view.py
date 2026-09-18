"""Merge manifest entries, DB stats and the active job into the admin view.

Pure assembly — no I/O besides stat() on the docx files — so the status
matrix is unit-testable with tmp_path.
"""

from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from neurolegal.contracts.admin import AdminDocument, DocumentStatus
from neurolegal.core.domain import LegalActKind
from neurolegal.rag.acquisition.corpus_store import ObjectInfo
from neurolegal.rag.acquisition.manifest import Manifest
from neurolegal.rag.store.admin import ActDbStats


def build_documents(
    manifest: Manifest,
    stats: list[ActDbStats],
    active_job_code_id: str | None,
    base_dir: Path = Path(),
    s3_objects: dict[str, ObjectInfo] | None = None,
) -> list[AdminDocument]:
    by_sid = {s.source_doc_id: s for s in stats}
    docs: list[AdminDocument] = []

    for entry in manifest.entries.values():
        db = by_sid.pop(entry.source_doc_id, None)
        size: int | None = None
        mtime: datetime | None = None
        file_path: str | None = None
        exists = False

        if entry.docx_s3_key is not None:
            # The `s3:` marker is the same convention PUT
            # /admin/documents/{id}/manifest parses back. The admin form
            # prefills from file_path and posts it as docx_path — a bare key
            # would round-trip as a (non-existent) local path and silently
            # detach the entry from S3.
            file_path = f"s3:{entry.docx_s3_key}"
            info = (s3_objects or {}).get(entry.docx_s3_key)
            exists = info is not None
            if info is not None:
                size = info.size
                mtime = info.last_modified
        elif entry.docx_path is not None:
            path = base_dir / entry.docx_path
            file_path = str(entry.docx_path)
            exists = path.is_file()
            if exists:
                st = path.stat()
                size = st.st_size
                mtime = datetime.fromtimestamp(st.st_mtime, tz=UTC)

        status: DocumentStatus
        if entry.code_id == active_job_code_id:
            status = "ingesting"
        elif db is None:
            status = "not_ingested"
        elif mtime is not None and mtime > db.ingested_at:
            status = "stale"
        else:
            status = "ingested"

        docs.append(
            AdminDocument(
                code_id=entry.code_id,
                source_doc_id=entry.source_doc_id,
                short_name=entry.short_name,
                full_name=entry.full_name,
                kind=entry.kind,
                status=status,
                file_path=file_path,
                file_exists=exists,
                file_size=size,
                file_mtime=mtime,
                articles_count=db.articles_count if db else None,
                chunks_count=db.chunks_count if db else None,
                ingested_at=db.ingested_at if db else None,
            )
        )

    # Rows present in the DB but absent from the manifest.
    for db in by_sid.values():
        docs.append(
            AdminDocument(
                code_id=None,
                source_doc_id=db.source_doc_id,
                short_name=db.short_name,
                full_name=db.full_name,
                kind=cast(LegalActKind, db.kind),
                status="orphaned",
                file_exists=False,
                articles_count=db.articles_count,
                chunks_count=db.chunks_count,
                ingested_at=db.ingested_at,
            )
        )
    return docs
