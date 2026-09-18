"""Admin routes: corpus documents (list/edit/delete/upload) + inspection.

The manifest file stays the source of truth for corpus composition; these
routes read and atomically rewrite it (comments are not preserved).
"""

import logging
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from neurolegal.contracts.admin import (
    UPLOAD_MAX_BYTES,
    AdminArticleDetail,
    AdminArticleListItem,
    AdminArticlesResponse,
    AdminChunkOut,
    AdminDocumentsResponse,
    DeleteDocumentRequest,
    ManifestUpdateRequest,
    OkResponse,
    UploadDocumentResponse,
)
from neurolegal.core.config import settings
from neurolegal.core.domain import LegalActKind
from neurolegal.rag.acquisition.corpus_store import (
    CorpusStore,
    ObjectInfo,
    corpus_key,
    normalize_prefix,
)
from neurolegal.rag.acquisition.manifest import (
    ManifestEntry,
    load_manifest,
    save_manifest,
    slugify_code_id,
)
from neurolegal.rag.api.deps import (
    db_session,
    get_corpus_store,
    get_job_manager,
    get_manifest_path,
)
from neurolegal.rag.documents_view import build_documents
from neurolegal.rag.jobs import JobBusyError, JobManager
from neurolegal.rag.store.admin import (
    act_stats,
    article_detail,
    count_chunks,
    db_size_bytes,
    delete_act,
    list_articles,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin")

_DbSession = Annotated[AsyncSession, Depends(db_session)]
_ManifestPath = Annotated[Path, Depends(get_manifest_path)]
_Jobs = Annotated[JobManager, Depends(get_job_manager)]
#: `None` when S3 credentials are absent — read-only routes degrade, the ones
#: that actually touch the bucket answer 503.
_CorpusStore = Annotated[CorpusStore | None, Depends(get_corpus_store)]

_NO_S3 = "S3 corpus storage is not configured (NEUROLEGAL_S3_ACCESS_KEY / _SECRET_KEY)"


def _require_store(store: CorpusStore | None) -> CorpusStore:
    if store is None:
        raise HTTPException(status_code=503, detail=_NO_S3)
    return store


def _safe_docx_path(raw: str, manifest_path: Path) -> Path:
    """Confine a manifest docx path to the documents directory.

    Prevents a crafted docx_path (absolute or ../-escaping) from later being
    read by the acquirer or unlinked by delete_document. Returns the path as
    given (relative kept relative) once validated.
    """
    root = manifest_path.parent.resolve()
    candidate = Path(raw)
    resolved = (candidate if candidate.is_absolute() else root / candidate).resolve()
    if resolved.suffix.lower() != ".docx" or not resolved.is_relative_to(root):
        raise HTTPException(
            status_code=422,
            detail="docx_path must be a .docx file inside the documents directory",
        )
    return candidate


def _safe_docx_s3_key(raw: str) -> str:
    """Confine a manifest S3 key to the corpus prefix of our own bucket.

    The bucket is shared with the documents hub (`owner/<uid>/<doc>/...`), so an
    unvalidated key here would let an operator point a manifest entry at a
    user's file and have DELETE ?drop_file=true erase it.
    """
    prefix = normalize_prefix(settings.corpus_s3_prefix)
    if (
        not raw.startswith(prefix)
        or len(raw) <= len(prefix)
        or not raw.lower().endswith(".docx")
        or ".." in raw
        or raw.startswith("/")
    ):
        raise HTTPException(
            status_code=422,
            detail=f"S3 key must be a .docx under {prefix!r} and contain no '..'",
        )
    return raw


async def _corpus_objects(store: CorpusStore | None) -> dict[str, ObjectInfo]:
    """One LIST for the whole corpus prefix; an S3 outage degrades, not 500s.

    The DB half of the status matrix is still valid without S3, so a listing
    failure only costs file size/mtime (every entry reads as file_exists=False).
    """
    if store is None:
        return {}
    try:
        return await store.list_prefix(normalize_prefix(settings.corpus_s3_prefix))
    except Exception:
        logger.warning("corpus_list_failed", exc_info=True)
        return {}


@router.get("/documents", response_model=AdminDocumentsResponse)
async def documents(
    session: _DbSession, manifest_path: _ManifestPath, jobs: _Jobs, store: _CorpusStore
) -> AdminDocumentsResponse:
    manifest = load_manifest(manifest_path)
    stats = await act_stats(session)
    total = await count_chunks(session)
    size = await db_size_bytes(session)
    active = jobs.active
    s3_objects = await _corpus_objects(store)
    docs = build_documents(
        manifest, stats, active.code_id if active else None, s3_objects=s3_objects
    )
    return AdminDocumentsResponse(documents=docs, total_chunks=total, db_size_bytes=size)


@router.post("/documents", response_model=UploadDocumentResponse, status_code=201)
async def upload_document(
    file: UploadFile,
    code_id: Annotated[str, Form(min_length=1)],
    short_name: Annotated[str, Form(min_length=1)],
    full_name: Annotated[str, Form(min_length=1)],
    kind: Annotated[LegalActKind, Form()],
    manifest_path: _ManifestPath,
    jobs: _Jobs,
    store: _CorpusStore,
    ingest_now: Annotated[bool, Form()] = False,
) -> UploadDocumentResponse:
    bucket = _require_store(store)
    filename = file.filename or ""
    if not filename.lower().endswith(".docx"):
        raise HTTPException(status_code=422, detail="only .docx files are accepted")
    manifest = load_manifest(manifest_path)
    if code_id in manifest.entries:
        raise HTTPException(status_code=422, detail=f"code_id {code_id!r} already exists")

    key = corpus_key(code_id, settings.corpus_s3_prefix)
    if await bucket.head(key) is not None:
        raise HTTPException(
            status_code=422,
            detail=f"an object already exists at {key}; choose a distinct code_id",
        )
    body = bytearray()
    while chunk := await file.read(1024 * 1024):
        body.extend(chunk)
        if len(body) > UPLOAD_MAX_BYTES:
            raise HTTPException(status_code=422, detail="file exceeds 20 MiB limit")
    await bucket.put(key, bytes(body))

    manifest.entries[code_id] = ManifestEntry(
        code_id=code_id,
        kind=kind,
        short_name=short_name,
        full_name=full_name,
        docx_s3_key=key,
    )
    save_manifest(manifest, manifest_path)

    job_id: str | None = None
    if ingest_now:
        try:
            job_id = jobs.start(code_id).id
        except JobBusyError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
    return UploadDocumentResponse(code_id=code_id, job_id=job_id)


@router.put("/documents/{code_id}/manifest", response_model=OkResponse)
async def update_manifest(
    code_id: str, req: ManifestUpdateRequest, manifest_path: _ManifestPath
) -> OkResponse:
    manifest = load_manifest(manifest_path)
    if code_id not in manifest.entries:
        raise HTTPException(status_code=404, detail=f"unknown code_id {code_id!r}")
    raw = req.docx_path
    update: dict[str, object]
    if raw.startswith("s3:"):
        update = {"docx_s3_key": _safe_docx_s3_key(raw.removeprefix("s3:")), "docx_path": None}
    else:
        update = {"docx_path": _safe_docx_path(raw, manifest_path), "docx_s3_key": None}
    old = manifest.entries[code_id]
    manifest.entries[code_id] = old.model_copy(
        update={
            "short_name": req.short_name,
            "full_name": req.full_name,
            "kind": req.kind,
            **update,
        }
    )
    save_manifest(manifest, manifest_path)
    return OkResponse()


@router.delete("/documents/{code_id}", response_model=OkResponse)
async def delete_document(
    code_id: str,
    session: _DbSession,
    manifest_path: _ManifestPath,
    jobs: _Jobs,
    store: _CorpusStore,
    req: DeleteDocumentRequest | None = None,
) -> OkResponse:
    opts = req or DeleteDocumentRequest()
    active = jobs.active
    if active is not None and active.code_id == code_id:
        raise HTTPException(status_code=409, detail="ingest job for this document is running")
    manifest = load_manifest(manifest_path)
    entry = manifest.entries.get(code_id)
    # Orphaned rows are addressed by their source_doc_id (no manifest entry);
    # slugify is idempotent on an already-slugged id.
    sid = entry.source_doc_id if entry is not None else slugify_code_id(code_id)
    # Refuse before touching the DB: a half-done delete (rows gone, object kept)
    # is worse than a plain 503.
    if opts.drop_file and entry is not None and entry.docx_s3_key is not None:
        _require_store(store)
    await delete_act(session, sid)
    if opts.drop_file and entry is not None:
        if entry.docx_s3_key is not None:
            await _require_store(store).delete(entry.docx_s3_key)
        elif entry.docx_path is not None:
            Path(entry.docx_path).unlink(missing_ok=True)
    if opts.drop_manifest and entry is not None:
        del manifest.entries[code_id]
        save_manifest(manifest, manifest_path)
    return OkResponse()


@router.get("/documents/{code_id}/articles", response_model=AdminArticlesResponse)
async def document_articles(
    code_id: str, session: _DbSession, manifest_path: _ManifestPath
) -> AdminArticlesResponse:
    manifest = load_manifest(manifest_path)
    entry = manifest.entries.get(code_id)
    sid = entry.source_doc_id if entry is not None else slugify_code_id(code_id)
    entries = await list_articles(session, sid)
    return AdminArticlesResponse(
        articles=[
            AdminArticleListItem(
                article_id=e.article_id,
                number=e.number,
                title=e.title,
                chunks_count=e.chunks_count,
            )
            for e in entries
        ]
    )


@router.get("/articles/{article_id}", response_model=AdminArticleDetail)
async def article(article_id: str, session: _DbSession) -> AdminArticleDetail:
    detail = await article_detail(session, article_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="article not found")
    return AdminArticleDetail(
        article_id=detail.article_id,
        act_short_name=detail.act_short_name,
        number=detail.number,
        title=detail.title,
        full_text=detail.full_text,
        chunks=[
            AdminChunkOut(chunk_id=c.chunk_id, path=c.path, text=c.text, ordinal=c.ordinal)
            for c in detail.chunks
        ],
    )
